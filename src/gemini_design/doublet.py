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
        self.pi_m3h_per_bar = productivity_index_m3h_per_bar(challenge, assumptions)
        self.trajectory_table = vertical_trajectory(depth_m, assumptions["well_inner_diameter_m"])
        self.pvt = {"RHOL": challenge["brine_density"], "VISL": challenge["brine_viscosity"]}
        self.well_config = {
            "reservoir_pressure_bar": self.reservoir_pressure_bar,
            "productivity_index_m3h_per_bar": self.pi_m3h_per_bar,
            "trajectory_table": self.trajectory_table,
            "pvt": self.pvt,
            "roughness_m": assumptions["well_roughness_m"],
        }
        self._cache = {}

    def producer(self, flow_m3h):
        """Return producer results for a flow rate (m3/h).

        Keys: ``bottomhole_pressure_bar``, ``wellhead_temperature_c``,
        ``wellhead_pressure_bar``, ``esp_dp_bar``, ``esp_power_w``,
        ``esp_depth_m`` (shallowest setting depth keeping the intake above
        ``esp_intake_pressure_min_bar``), ``drawdown_bar``.
        """
        key = ("prod", round(flow_m3h, 6))
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
        t_res_k = self.reservoir_temperature_c + CELSIUS_TO_KELVIN
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
        p_intake_min = a["esp_intake_pressure_min_bar"] * 1e5
        esp_depth = self.depth_m - max(0.0, p_bh_res - p_intake_min) / rho_g
        esp_depth = max(esp_depth, 0.0)

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
            "bottomhole_pressure_bar": self.reservoir_pressure_bar + flow_m3h / self.pi_m3h_per_bar,
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
