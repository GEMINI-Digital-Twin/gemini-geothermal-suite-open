"""Doublet hydraulics using GEMINI's reservoir (IPR) and well (DPDT) models.

For a production rate ``Q`` the producer bottomhole pressure follows the
linear inflow model; the pressure the well needs at bottomhole to deliver
``Q`` at the target wellhead pressure follows from walking the well
top-down with ``DPDT`` (same convention as ``gemini_simulator.nodal_solver``).
The ESP supplies the difference at the challenge's 70% hydraulic
efficiency. The injector wellhead pressure is solved with
``gemini_simulator.well_flow.solve_injector_wellhead_pressure_bar``.
Both wells use the challenge brine density and viscosity.
"""

import numpy as np

from gemini_design.challenge import (
    ASSUMPTIONS,
    CELSIUS_TO_KELVIN,
    CHALLENGE,
    GRAVITY,
    productivity_index_m3h_per_bar,
    reservoir_at_depth,
)
from gemini_design.esp import EspPump
from gemini_design.gas_solubility import bubble_point_bar
from gemini_model.reservoir.inflow_performance import IPR
from gemini_simulator.well_flow import (
    _build_dpdt,
    _trajectory_table_to_segments,
    solve_injector_wellhead_pressure_bar,
)


def vertical_trajectory(depth_m, inner_diameter_m):
    """Return a simple vertical MD/TVD/ID trajectory table down to ``depth_m``."""
    stations = [0.0, 500.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 3500.0, 4000.0]
    md = [s for s in stations if s < depth_m] + [depth_m]
    return [{"MD": m, "TVD": m, "ID": inner_diameter_m} for m in md]


class DoubletHydraulics:
    """Producer + injector of one doublet at a given reservoir depth."""

    def __init__(self, depth_m, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
        """Set up both wells from the challenge data at ``depth_m``."""
        self.challenge = challenge
        self.assumptions = assumptions
        self.depth_m = depth_m
        self.reservoir_temperature_c, self.reservoir_pressure_bar = reservoir_at_depth(
            depth_m, challenge
        )
        # Brine temperature entering the producer: the formation temperature
        # less any thermal-breakthrough drop (e.g. from gemini_design.fimbul).
        self.production_temperature_c = self.reservoir_temperature_c - assumptions.get(
            "production_temperature_drop_c", 0.0
        )
        # Steady-state Darcy PI, optionally corrected by reservoir simulation
        # (gemini_design.fimbul): the producer sees ``productivity_ratio`` x PI
        # and the injector, pushing cold viscous brine, ``injectivity_ratio`` x PI.
        self.pi_m3h_per_bar = productivity_index_m3h_per_bar(
            challenge, assumptions
        ) * assumptions.get("productivity_ratio", 1.0)
        self.ii_m3h_per_bar = productivity_index_m3h_per_bar(
            challenge, assumptions
        ) * assumptions.get("injectivity_ratio", 1.0)
        self.trajectory_table = vertical_trajectory(depth_m, assumptions["well_inner_diameter_m"])
        self.pvt = {"RHOL": challenge["brine_density"], "VISL": challenge["brine_viscosity"]}
        self.well_config = {
            "reservoir_pressure_bar": self.reservoir_pressure_bar,
            "productivity_index_m3h_per_bar": self.ii_m3h_per_bar,
            "trajectory_table": self.trajectory_table,
            "pvt": self.pvt,
            "roughness_m": assumptions["well_roughness_m"],
        }
        # Dissolved gas: the ESP intake must stay above the bubble point.
        self.bubble_point_bar = bubble_point_bar(
            self.production_temperature_c, challenge, assumptions
        )["bubble_point_bar"]
        self.esp_intake_min_bar = max(
            assumptions["esp_intake_pressure_min_bar"],
            self.bubble_point_bar + assumptions.get("esp_bubble_point_margin_bar", 0.0),
        )
        self._cache = {}
        self.pump = None  # a sized gemini_design.esp.EspPump; None = ideal pump

    @property
    def flow_range_m3h(self):
        """Flows the sized ESP can run at, or None for the ideal pump."""
        return self.pump.flow_range_m3h() if self.pump is not None else None

    def producer(self, flow_m3h, heat_loss_multiplier=1.0):
        """Return producer results for a flow rate (m3/h).

        With a sized ESP (``self.pump``) the pump's own duty replaces the
        ideal pump power, and the ``esp_*`` keys of
        :meth:`gemini_design.esp.EspPump.operate` are added
        (``esp_in_range`` False marks a flow the pump cannot run at).
        """
        result = self.ideal_producer(flow_m3h, heat_loss_multiplier)
        if self.pump is None:
            return result
        out = dict(result)
        out.update(self.pump.operate(flow_m3h, result["esp_dp_bar"]))
        return out

    def ideal_producer(self, flow_m3h, heat_loss_multiplier=1.0):
        """Return producer results for a flow rate (m3/h) with the ideal pump.

        Keys: ``bottomhole_pressure_bar``, ``wellhead_temperature_c``,
        ``wellhead_pressure_bar``, ``esp_dp_bar``, ``esp_power_w``,
        ``esp_depth_m`` (shallowest setting depth keeping the intake above
        both ``esp_intake_pressure_min_bar`` and the gas bubble point plus
        ``esp_bubble_point_margin_bar``), ``esp_intake_ok`` (False if even a
        pump at the reservoir cannot keep that intake pressure),
        ``bubble_point_bar``, ``gas_breakout_depth_m`` (where the rising
        brine drops below the bubble point), ``drawdown_bar``.

        ``heat_loss_multiplier`` scales the wellbore heat loss of GEMINI's
        steady well model (a fixed U = 10 W/m2K); :mod:`gemini_design.operations`
        uses it for the time-dependent loss after a start.
        """
        key = ("prod", round(flow_m3h, 6), round(heat_loss_multiplier, 6))
        if key in self._cache:
            return self._cache[key]

        q = flow_m3h / 3600.0
        a = self.assumptions
        ipr = IPR()
        ipr.update_parameters(
            {
                "type": "production_reservoir",
                "reservoir_pressure": self.reservoir_pressure_bar * 1e5,
                "productivity_index": self.pi_m3h_per_bar / 3.6e8,
            }
        )
        ipr.calculate_output({"flow": q}, None)
        p_bh_res = ipr.get_output()["bottomhole_pressure"]

        segments = _trajectory_table_to_segments(self.trajectory_table)
        t_res_k = self.production_temperature_c + CELSIUS_TO_KELVIN
        t_ambient_k = 0.5 * (self.challenge["surface_temperature_c"] + self.reservoir_temperature_c)
        t_ambient_k += CELSIUS_TO_KELVIN

        # heat loss on the way up (bottomhole -> wellhead)
        well_up = _build_dpdt(segments, roughness=a["well_roughness_m"], pvt_parameters=self.pvt)
        well_up.calculate_output(
            {
                "pressure": p_bh_res,
                "temperature": t_res_k,
                "temperature_ambient": t_ambient_k,
                "flowrate": q,
                "direction": "up",
            },
            None,
        )
        t_wh_c = well_up.get_output()["temperature_output"] - CELSIUS_TO_KELVIN
        if heat_loss_multiplier != 1.0:
            t_wh_c = self.production_temperature_c - heat_loss_multiplier * (
                self.production_temperature_c - t_wh_c
            )

        # bottomhole pressure needed to deliver q at the target wellhead pressure
        p_wh = a["producer_wellhead_pressure_bar"] * 1e5
        well_down = _build_dpdt(segments, roughness=a["well_roughness_m"], pvt_parameters=self.pvt)
        well_down.calculate_output(
            {
                "pressure": p_wh,
                "temperature": t_wh_c + CELSIUS_TO_KELVIN,
                "temperature_ambient": t_ambient_k,
                "flowrate": q,
                "direction": "down",
            },
            None,
        )
        p_bh_needed = well_down.get_output()["pressure_output"]
        dp_fric = well_down.get_output()["pressuredrop_fric_output"]

        esp_dp = max(0.0, p_bh_needed - p_bh_res)
        esp_power = q * esp_dp / self.challenge["pump_efficiency"]

        # ESP setting depth: intake pressure falls ~rho g per metre going up from bottomhole
        rho_g = self.challenge["brine_density"] * GRAVITY
        p_intake_min = self.esp_intake_min_bar * 1e5
        esp_depth = self.depth_m - max(0.0, p_bh_res - p_intake_min) / rho_g
        esp_depth = max(esp_depth, 0.0)
        # above the pump the column is roughly hydrostatic down from the wellhead
        gas_breakout_depth = max(0.0, (self.bubble_point_bar * 1e5 - p_wh) / rho_g)

        result = {
            "flow_m3h": flow_m3h,
            "bottomhole_pressure_bar": p_bh_res / 1e5,
            "drawdown_bar": self.reservoir_pressure_bar - p_bh_res / 1e5,
            "wellhead_temperature_c": t_wh_c,
            "wellhead_pressure_bar": p_wh / 1e5,
            "friction_dp_bar": dp_fric / 1e5,
            "esp_dp_bar": esp_dp / 1e5,
            "esp_power_w": esp_power,
            "esp_depth_m": esp_depth,
            "esp_intake_ok": p_bh_res >= p_intake_min,
            "bubble_point_bar": self.bubble_point_bar,
            "gas_breakout_depth_m": min(gas_breakout_depth, esp_depth),
        }
        self._cache[key] = result
        return result

    def injector(self, flow_m3h, injection_temperature_c):
        """Return injector wellhead pressure and injection pump power for a flow (m3/h)."""
        key = ("inj", round(flow_m3h, 6))
        if key not in self._cache:
            self._cache[key] = solve_injector_wellhead_pressure_bar(
                self.well_config,
                flow_m3h=flow_m3h,
                wellhead_temperature_c=injection_temperature_c,
            )
        wellhead_pressure_bar = self._cache[key]
        p_in = (
            self.assumptions["producer_wellhead_pressure_bar"]
            - self.assumptions["surface_pressure_loss_bar"]
        )
        dp = max(0.0, wellhead_pressure_bar - p_in)
        power = flow_m3h / 3600.0 * dp * 1e5 / self.challenge["pump_efficiency"]
        return {
            "wellhead_pressure_bar": wellhead_pressure_bar,
            "pump_dp_bar": dp,
            "pump_power_w": power,
            "bottomhole_pressure_bar": self.reservoir_pressure_bar + flow_m3h / self.ii_m3h_per_bar,
        }

    def curve(self, flows_m3h=None):
        """Return producer/injector results over a flow grid (for reports and agent context)."""
        if flows_m3h is None:
            flows_m3h = np.arange(50.0, 301.0, 25.0)
        rows = []
        for q in flows_m3h:
            row = dict(self.producer(q))
            inj = self.injector(q, row["wellhead_temperature_c"] - 40.0)
            row.update({f"injector_{k}": v for k, v in inj.items()})
            rows.append(row)
        return rows


class DoubletGroup:
    """Doublets at different depths sharing one surface plant (parallel, common header).

    The producers' brine is mixed after the wellheads (equal flow per running
    doublet, as the dispatcher sets one flow), goes through the plant and is
    split again to the injectors at one injection temperature. The 40 K
    cooling cap holds for every producer, so the hottest running producer
    sets the injection floor; mixing a cooler doublet in therefore lowers
    what the hotter one can give. Running doublets are chosen hottest first
    among those available that day.

    It answers the calls :class:`gemini_design.plant.Plant` makes on a
    :class:`DoubletHydraulics`, with the running set passed as ``active``
    (indices into ``depths_m`` as the design lists them).
    """

    def __init__(self, depths_m, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
        """Build one :class:`DoubletHydraulics` per distinct depth."""
        self.depths_m = [float(d) for d in depths_m]
        by_depth = {d: DoubletHydraulics(d, challenge, assumptions) for d in set(self.depths_m)}
        self.members = [by_depth[d] for d in self.depths_m]
        self.challenge, self.assumptions = challenge, assumptions
        # hottest first; ties keep the design's order
        self.order = sorted(
            range(len(self.members)), key=lambda i: -self.members[i].production_temperature_c
        )
        hottest = self.members[self.order[0]]
        self.depth_m = hottest.depth_m
        self.reservoir_temperature_c = hottest.reservoir_temperature_c
        self.reservoir_pressure_bar = hottest.reservoir_pressure_bar
        self.production_temperature_c = hottest.production_temperature_c
        self.pi_m3h_per_bar = hottest.pi_m3h_per_bar
        self.well_config = hottest.well_config
        self.mixed = len(by_depth) > 1

    @property
    def flow_range_m3h(self):
        """Flows every sized ESP can run at, or None for ideal pumps."""
        ranges = [m.flow_range_m3h for m in self.members if m.pump is not None]
        if not ranges:
            return None
        return (max(r[0] for r in ranges), min(r[1] for r in ranges))

    def active(self, n_active, available=None):
        """Indices of the ``n_active`` hottest doublets among the available ones."""
        pool = [i for i in self.order if available is None or available[i]]
        if len(pool) < n_active:  # the dispatcher never asks for more than are available
            pool += [i for i in self.order if i not in pool]
        return tuple(pool[:n_active])

    def producer(self, flow_m3h, heat_loss_multiplier=1.0, active=None):
        """Mixed producer results of the running doublets (per-doublet averages of pump power).

        ``wellhead_temperature_c`` is the mixed brine temperature;
        ``cap_temperature_c`` the hottest running producer's wellhead
        temperature, which the 40 K cap applies to.
        """
        active = tuple(range(len(self.members))) if active is None else active
        rows = [self.members[i].producer(flow_m3h, heat_loss_multiplier) for i in active]
        n = len(rows)
        out = dict(rows[0])
        out.update(
            {
                "wellhead_temperature_c": sum(r["wellhead_temperature_c"] for r in rows) / n,
                "cap_temperature_c": max(r["wellhead_temperature_c"] for r in rows),
                "esp_power_w": sum(r["esp_power_w"] for r in rows) / n,
                "esp_dp_bar": max(r["esp_dp_bar"] for r in rows),
                "esp_depth_m": max(r["esp_depth_m"] for r in rows),
                "esp_intake_ok": all(r["esp_intake_ok"] for r in rows),
                "drawdown_bar": max(r["drawdown_bar"] for r in rows),
                "gas_breakout_depth_m": max(r["gas_breakout_depth_m"] for r in rows),
                "running_depths_m": [self.depths_m[i] for i in active],
            }
        )
        if "esp_in_range" in out:
            out["esp_in_range"] = all(r["esp_in_range"] for r in rows)
            out["esp_efficiency"] = sum(r["esp_efficiency"] for r in rows) / n
            out["esp_speed_ratio"] = max(r["esp_speed_ratio"] for r in rows)
            out["esp_choke_bar"] = max(r["esp_choke_bar"] for r in rows)
            out["esp_pump_dp_bar"] = max(r["esp_pump_dp_bar"] for r in rows)
            out["esp_flow_ratio"] = max(r["esp_flow_ratio"] for r in rows)
        return out

    def injector(self, flow_m3h, injection_temperature_c, active=None):
        """Injector results of the running doublets (pump power averaged per doublet)."""
        active = tuple(range(len(self.members))) if active is None else active
        rows = [self.members[i].injector(flow_m3h, injection_temperature_c) for i in active]
        n = len(rows)
        out = dict(rows[0])
        out["pump_power_w"] = sum(r["pump_power_w"] for r in rows) / n
        out["wellhead_pressure_bar"] = max(r["wellhead_pressure_bar"] for r in rows)
        out["pump_dp_bar"] = max(r["pump_dp_bar"] for r in rows)
        return out


def hydraulics_for(design, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """A :class:`DoubletHydraulics`, or a :class:`DoubletGroup` for mixed doublet depths.

    A design with ``esp_rated_flow_m3h`` > 0 gets a sized ESP
    (:class:`gemini_design.esp.EspPump`) on each producer.
    """
    depths = tuple(getattr(design, "doublet_depths_m", ()) or ())
    if depths and len(set(float(d) for d in depths)) > 1:
        hyd = DoubletGroup(depths, challenge, assumptions)
        members = set(hyd.members)
    else:
        hyd = DoubletHydraulics(design.depth_m, challenge, assumptions)
        members = {hyd}
    rated = float(getattr(design, "esp_rated_flow_m3h", 0.0) or 0.0)
    if rated > 0:
        drive = getattr(design, "esp_drive", "vsd")
        for m in members:
            m.pump = EspPump.sized_for(m, rated, drive, challenge, assumptions)
    return hyd


def esp_pumps(hydraulics, design):
    """The sized ESP of each doublet (empty for the ideal pump)."""
    if isinstance(hydraulics, DoubletGroup):
        pumps = [m.pump for m in hydraulics.members]
    else:
        pumps = [hydraulics.pump] * design.n_doublets
    return [p for p in pumps if p is not None]


def flow_limits_m3h(hydraulics, challenge=CHALLENGE):
    """The flow range per doublet the dispatcher searches: the challenge's, narrowed to the ESP's.

    If the pump's range misses the challenge's entirely the challenge's range
    is returned (every flow then fails the pump check).
    """
    lo, hi = challenge["flow_min_m3h"], challenge["flow_max_m3h"]
    rng = getattr(hydraulics, "flow_range_m3h", None)
    if rng is None:
        return lo, hi
    lo2, hi2 = max(lo, rng[0]), min(hi, rng[1])
    return (lo2, hi2) if lo2 <= hi2 else (lo, hi)
