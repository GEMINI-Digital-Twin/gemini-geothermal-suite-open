"""Daily plant flowsheet: geothermal doublets + upgrade + cooling, built from GEMINI models.

Primary (brine) path, per active doublet sharing the load equally::

    producer well (ESP) -> separator (gas off) -> [absorption chiller generator]
        -> district heating HEX -> [heat pump evaporator] -> injection pump -> injector well

Secondary (district heating) path::

    return 40 degC -> [CHP heat recovery] -> HEX (with bypass) -> [heat pump condenser]
        -> [gas boiler] -> 100 degC supply

Optionally, an air-cooled ORC power unit takes the brine after the HEX and
heat pump, down to the 40 K cap (it uses only heat the district does not
need that day); its net power offsets the plant's electricity like the CHP
and any surplus is exported. The 40 K cap is shared, so a unit ahead of the
HEX would take heat the 100 degC supply needs (see run_orc_study.py).

Co-produced (associated) gas from the separator fuels the CHP first (its
electricity offsets the pumps, heat pump and chillers; any surplus is
exported), then the boiler; the boiler buys natural gas for the rest.
Associated gas that neither burns is flared, and its CO2 is counted either way.

Cooling path (20 degC supply), in order: an optional dry-cooler
economizer (free cooling), an optional shallow aquifer cold store (ATES,
planned for the year by :mod:`gemini_design.ates`), then an absorption
chiller driven by brine or an electric chiller (one of
``CHILLER_TYPES``: dry cooler, wet cooling tower or air-cooled), plus an
optional electric backup chiller.

The HEX bypass keeps the brine from being cooled by more than the
challenge's 40 K; the heat pump's minimum source outlet temperature is set
to the same limit, so no component can break that hard cap.
"""

import math
from dataclasses import dataclass, field

from gemini_design.challenge import (
    ASSUMPTIONS,
    CHALLENGE,
    CHILLER_TYPES,
    associated_gas_properties,
)
from gemini_design.doublet import DoubletGroup
from gemini_design.esp import DRIVES as ESP_DRIVES
from gemini_design.network import design_assumptions
from gemini_model.boiler.boiler import Boiler
from gemini_model.chiller.absorption_chiller import AbsorptionChiller
from gemini_model.chiller.electric_chiller import ElectricChiller
from gemini_model.chp.chp import CHP
from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger
from gemini_model.heatpump.heatpump_basic import HeatpumpBasic
from gemini_model.orc.orc import OrganicRankineCycle
from gemini_model.separator.separator import Separator

UPGRADES = ("boiler", "heat_pump")
COOLING = ("absorption", "electric")
CHILLER_SHORT_NAMES = {
    "screw_dry_cooler": "screw",
    "centrifugal_tower": "tower",
    "air_cooled_screw": "aircooled",
}


@dataclass
class Design:
    """A candidate heating and cooling plant."""

    n_doublets: int
    depth_m: float
    upgrade: str = "boiler"  # "boiler" or "heat_pump" (heat pump backed by boiler)
    cooling: str = "absorption"  # "absorption" or "electric"
    heat_pump_capacity_mw: float = 0.0
    boiler_capacity_mw: float = 30.0
    chiller_capacity_mw: float = 10.0
    electric_backup_mw: float = 0.0  # electric chiller backing an absorption chiller
    chp_capacity_mw_el: float = 0.0  # gas engine on associated gas (0 = none)
    free_cooling: bool = False  # dry-cooler economizer ahead of the electric chiller
    storage_mwh: float = 0.0  # seasonal heat store (needs a registered thermal_storage model)
    storage_mw: float = 0.0  # its charge / discharge rating
    pit_store_m3: float = 0.0  # built-in seasonal pit heat store (gemini_design.pit_storage)
    pit_store_mw: float = 0.0  # its charge / discharge rating at the full temperature difference
    chiller_type: str = "legacy"  # electric chiller technology, a key of CHILLER_TYPES
    ates_doublets: int = 0  # shallow aquifer cold-store well pairs (0 = none)
    orc_capacity_mw_el: float = 0.0  # air-cooled ORC power unit on the brine (0 = none)
    # first day (0 = 1 January) of each doublet's 35-day stop; -1 = placed automatically
    # in the lowest-load window; empty = the geothermal_outage_* assumptions decide
    outage_start_days: tuple = ()
    # depth of each doublet (m TVD) when they differ; empty = all at depth_m. Mixed depths
    # share one surface plant (gemini_design.doublet.DoubletGroup); depth_m becomes the deepest
    doublet_depths_m: tuple = ()
    electric_boiler_mw: float = 0.0  # electric boiler top-up next to the gas boiler (0 = none)
    heat_recovery_hp_mw: float = 0.0  # cooling (MW) of a heat pump that heats the return line
    boiler_units: int = 1  # gas boiler split into equal units (part load, N-1 and cost)
    # sized downhole pump (gemini_design.esp): best-efficiency flow per producer (m3/h);
    # 0 = the ideal pump (any flow at the challenge's pump efficiency, cost in the surface cost)
    esp_rated_flow_m3h: float = 0.0
    esp_drive: str = "vsd"  # "vsd" (variable speed) or "fixed" (fixed speed + surface choke)
    # district return temperatures (degC); None = the heating_return_c / cooling_return_c
    # assumptions. Other values than the reference network's are priced (gemini_design.network)
    heating_return_c: float = None
    cooling_return_c: float = None
    name: str = ""
    notes: list = field(default_factory=list)

    def __post_init__(self):
        """Fill a default name and check the categorical choices."""
        if self.upgrade not in UPGRADES:
            raise ValueError(f"upgrade must be one of {UPGRADES}, got '{self.upgrade}'")
        if self.cooling not in COOLING:
            raise ValueError(f"cooling must be one of {COOLING}, got '{self.cooling}'")
        if self.free_cooling and self.cooling != "electric":
            raise ValueError("free_cooling is only modelled ahead of an electric chiller")
        if self.chiller_type not in CHILLER_TYPES:
            raise ValueError(
                f"chiller_type must be one of {tuple(CHILLER_TYPES)}, got '{self.chiller_type}'"
            )
        if self.ates_doublets < 0:
            raise ValueError("ates_doublets must not be negative")
        self.doublet_depths_m = tuple(float(x) for x in self.doublet_depths_m)
        if self.doublet_depths_m:
            if len(self.doublet_depths_m) != self.n_doublets:
                raise ValueError("doublet_depths_m needs one depth per doublet")
            if len(set(self.doublet_depths_m)) == 1:  # all equal: the ordinary design
                self.depth_m, self.doublet_depths_m = self.doublet_depths_m[0], ()
            else:
                self.depth_m = max(self.doublet_depths_m)
        self.outage_start_days = tuple(int(x) for x in self.outage_start_days)
        if self.outage_start_days:
            if len(self.outage_start_days) != self.n_doublets:
                raise ValueError("outage_start_days needs one start day per doublet")
            if any(not -1 <= x <= 364 for x in self.outage_start_days):
                raise ValueError("outage start days must be -1 (automatic) or 0-364")
        for key in ("heating_return_c", "cooling_return_c"):
            if getattr(self, key) is not None:
                setattr(self, key, float(getattr(self, key)))
        self.boiler_units = int(self.boiler_units)
        if self.boiler_units < 1:
            raise ValueError("boiler_units must be at least 1")
        if self.electric_boiler_mw < 0 or self.heat_recovery_hp_mw < 0:
            raise ValueError("electric_boiler_mw and heat_recovery_hp_mw must not be negative")
        self.esp_rated_flow_m3h = float(self.esp_rated_flow_m3h)
        if self.esp_drive not in ESP_DRIVES:
            raise ValueError(f"esp_drive must be one of {ESP_DRIVES}, got '{self.esp_drive}'")
        if self.esp_rated_flow_m3h and not 50.0 <= self.esp_rated_flow_m3h <= 300.0:
            raise ValueError("esp_rated_flow_m3h must be 0 (ideal pump) or 50-300 m3/h")
        if not self.esp_rated_flow_m3h and self.esp_drive != "vsd":
            raise ValueError("esp_drive needs a sized pump (esp_rated_flow_m3h > 0)")
        if self.orc_capacity_mw_el < 0:
            raise ValueError("orc_capacity_mw_el must not be negative")
        if self.storage_mwh < 0 or self.storage_mw < 0:
            raise ValueError("storage_mwh and storage_mw must not be negative")
        if (self.storage_mwh > 0) != (self.storage_mw > 0):
            raise ValueError("storage needs a capacity (storage_mwh) and a rating (storage_mw)")
        if self.pit_store_m3 < 0 or self.pit_store_mw < 0:
            raise ValueError("pit_store_m3 and pit_store_mw must not be negative")
        if (self.pit_store_m3 > 0) != (self.pit_store_mw > 0):
            raise ValueError(
                "a pit store needs a volume (pit_store_m3) and a rating (pit_store_mw)"
            )
        if self.pit_store_m3 > 0 and self.storage_mwh > 0:
            raise ValueError("use either the pit store or the thermal_storage slot, not both")
        if not self.name:
            depth = "+".join(f"{d:g}" for d in self.doublet_depths_m) or f"{int(self.depth_m)}"
            self.name = f"{self.n_doublets}D-{depth}m-{self.upgrade}-{self.cooling}"
            if self.chp_capacity_mw_el > 0:
                self.name += "-chp"
            if self.chiller_type != "legacy":
                self.name += "-" + CHILLER_SHORT_NAMES[self.chiller_type]
            if self.free_cooling:
                self.name += "-fc"
            if self.ates_doublets > 0:
                self.name += f"-ates{self.ates_doublets}"
            if self.orc_capacity_mw_el > 0:
                self.name += f"-orc{self.orc_capacity_mw_el:g}"
            if self.electric_boiler_mw > 0:
                self.name += f"-eb{self.electric_boiler_mw:g}"
            if self.heat_recovery_hp_mw > 0:
                self.name += f"-hrhp{self.heat_recovery_hp_mw:g}"
            if self.boiler_units > 1:
                self.name += f"-{self.boiler_units}xB"
            if self.esp_rated_flow_m3h > 0:
                self.name += f"-esp{self.esp_rated_flow_m3h:g}" + self.esp_drive[0]
            if self.storage_mwh > 0:
                self.name += f"-tes{self.storage_mwh / 1000:g}GWh"
            if self.pit_store_m3 > 0:
                self.name += f"-pit{self.pit_store_m3 / 1000:g}k"
            if self.heating_return_c is not None or self.cooling_return_c is not None:
                self.name += "-ret" + "/".join(
                    "ref" if t is None else f"{t:g}"
                    for t in (self.heating_return_c, self.cooling_return_c)
                )
            if self.outage_start_days:
                self.name += "-stops" + ",".join(
                    "auto" if x < 0 else str(x) for x in self.outage_start_days
                )

    def well_depths_m(self):
        """Depth of each doublet (m), in the design's order."""
        return list(self.doublet_depths_m) or [self.depth_m] * self.n_doublets

    def as_dict(self):
        """Return the design as a plain dict (for JSON reports and agent context)."""
        out = {k: v for k, v in self.__dict__.items() if k != "notes"}
        # keep the run keys of earlier designs stable: new fields only when set
        for key in ("outage_start_days", "doublet_depths_m"):
            if not out[key]:
                del out[key]
            else:
                out[key] = list(out[key])
        for key in ("heating_return_c", "cooling_return_c"):
            if out[key] is None:
                del out[key]
        for key in ("electric_boiler_mw", "heat_recovery_hp_mw"):
            if not out[key]:
                del out[key]
        if out["boiler_units"] == 1:
            del out["boiler_units"]
        if not out["esp_rated_flow_m3h"]:
            del out["esp_rated_flow_m3h"], out["esp_drive"]
        return out


class Plant:
    """Evaluates one day of plant operation for a design."""

    def __init__(self, design, hydraulics, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
        """Build the GEMINI component models once for a design."""
        assumptions = design_assumptions(design, assumptions)
        self.design = design
        self.hyd = hydraulics
        self.grouped = isinstance(hydraulics, DoubletGroup)
        self.availability = None  # (days, n_doublets) bool, set by run_year for mixed depths
        self.c = challenge
        self.a = assumptions
        self.gas = associated_gas_properties(challenge)
        self.rho = challenge["brine_density"]
        self.cp = assumptions["brine_cp"]

        self.separator = Separator()
        self.separator.update_parameters(
            {
                "flow_resistance": 0.0,
                "temperature_drop": assumptions["separator_temperature_drop_k"],
                "gas_water_ratio": challenge["gas_liquid_ratio"],
                "gas_density": self.gas["density"],
            }
        )
        self.hex = HeatExchanger()
        self.hex.update_parameters(
            {
                "flow_resistance": 0.0,
                "flow_configuration": "counter",
                "heat_transfer_coefficient": assumptions["hex_ua_per_doublet_w_per_k"],
                "fluid_density": self.rho,
                "specific_heat": self.cp,
            }
        )
        self.heat_pump = HeatpumpBasic()
        self.heat_pump.update_parameters(
            {
                "mode": "lorenz",
                "eta_lorenz": assumptions["heat_pump_eta_lorenz"],
                "Cp_h": self.cp,
                "Cp_s": self.cp,
                "rho_h": self.rho,
                "rho_s": self.rho,
            }
        )
        self.boiler = Boiler()
        self.boiler.update_parameters(
            {
                "caloric_value": self.gas["lhv"],
                "efficiency_factor": assumptions["boiler_efficiency"],
                "gas_emission_factor": 0.0,  # associated-gas CO2 is booked separately
                "fluid_density": self.rho,
                "specific_heat": self.cp,
            }
        )
        self.absorption = AbsorptionChiller()
        self.absorption.update_parameters(
            {
                "capacity_nominal": design.chiller_capacity_mw * 1e6,
                "eta_rev": assumptions["absorption_eta_rev"],
                "cop_max": assumptions["absorption_cop_max"],
                "chilled_temperature_out_target": challenge["cooling_supply_c"],
                "aux_power_fraction": assumptions["chiller_aux_power_fraction"],
                "hot_temperature_drop_max": assumptions["absorption_hot_dt_max_k"],
                "rho_hot": self.rho,
                "cp_hot": self.cp,
            }
        )
        electric_capacity = (
            design.chiller_capacity_mw
            if design.cooling == "electric"
            else design.electric_backup_mw
        )
        tech = dict(CHILLER_TYPES[design.chiller_type])
        if design.chiller_type == "legacy":  # the first screen's model, tunable by assumptions
            tech.update(
                {
                    "eta_carnot": assumptions["electric_chiller_eta_carnot"],
                    "cop_max": assumptions["electric_chiller_cop_max"],
                    "condenser_approach_k": assumptions["electric_chiller_condenser_approach_k"],
                    "units": assumptions["electric_chiller_units"],
                    "aux_power_fraction": assumptions["chiller_aux_power_fraction"],
                }
            )
        self.chiller_tech = tech
        self.electric = ElectricChiller()
        self.electric.update_parameters(
            {
                "capacity_nominal": electric_capacity * 1e6,
                "eta_carnot": tech["eta_carnot"],
                "cop_max": tech["cop_max"],
                "evaporator_approach": assumptions["electric_chiller_evaporator_approach_k"],
                "condenser_approach": tech["condenser_approach_k"],
                "units": tech["units"],
                "part_load_coefficients": tech["part_load_coefficients"],
                "plr_min": tech["plr_min"],
                "aux_power_fraction": tech["aux_power_fraction"],
                "chilled_temperature_out_target": challenge["cooling_supply_c"],
            }
        )
        self.chp = CHP()
        self.chp.update_parameters(
            {
                "caloric_value": self.gas["lhv"],
                "efficiency_factor": assumptions["chp_efficiency"],
                "gas_emission_factor": 0.0,  # associated-gas CO2 is booked separately
                "fluid_density": self.rho,
                "specific_heat": self.cp,
            }
        )
        self.orc = OrganicRankineCycle()
        self.orc.update_parameters(
            {
                "capacity_net": getattr(design, "orc_capacity_mw_el", 0.0) * 1e6,
                "second_law_fraction": assumptions.get("orc_second_law_fraction", 0.45),
                "condenser_approach": assumptions.get("orc_condenser_approach_k", 15.0),
                "min_outlet_above_condensing": assumptions.get(
                    "orc_min_outlet_above_condensing_k", 20.0
                ),
                "plr_min": assumptions.get("orc_plr_min", 0.3),
                "fluid_density": self.rho,
                "specific_heat": self.cp,
            }
        )
        # associated gas (kg/s) the CHP burns at its rated electrical output
        self.chp_gas_capacity = (
            design.chp_capacity_mw_el
            * 1e6
            / (self.gas["lhv"] * assumptions["chp_efficiency"] * CHP.ELECTRICAL_POWER_FRACTION)
        )

    # ------------------------------------------------------------------ helpers
    def _chilled_flow(self, cooling_w):
        dt = self.a["cooling_return_c"] - self.c["cooling_supply_c"]
        return cooling_w / (self.a["water_density"] * self.a["water_cp"] * dt)

    def _run_hex(self, t_primary_in, primary_flow, secondary_flow, n_active, fraction, t_in=None):
        """Run the HEX with a share ``fraction`` of the secondary flow; return mixed outlet.

        ``t_in`` is the secondary inlet temperature (defaults to the network return).
        """
        t_return = self.a["heating_return_c"] if t_in is None else t_in
        self.hex.update_parameters(
            {"heat_transfer_coefficient": n_active * self.a["hex_ua_per_doublet_w_per_k"]}
        )
        self.hex.calculate_output(
            {
                "pressure_in": self.a["producer_wellhead_pressure_bar"],
                "primary_temperature_in": t_primary_in,
                "primary_flow_rate": primary_flow,
                "secondary_temperature_in": t_return,
                "secondary_flow_rate": fraction * secondary_flow,
            }
        )
        out = self.hex.output
        t_mixed = fraction * out["secondary_temperature_out"] + (1.0 - fraction) * t_return
        return out["primary_temperature_out"], t_mixed, out["heat_duty"]

    # ------------------------------------------------------------------ main
    def evaluate(
        self,
        heating_w,
        cooling_w,
        n_active,
        flow_m3h,
        ambient_c=None,
        wet_bulb_c=None,
        ates_cooling_w=0.0,
        ates_power_w=0.0,
        heat_loss_multiplier=1.0,
        ambient_mean_c=None,
        day=None,
        electricity_price=None,
        export_price=None,
    ):
        """Simulate one steady day; return energy flows, temperatures and checks.

        ``flow_m3h`` is the production (= injection) rate of each active doublet.

        With a CHP, associated gas can go to the CHP first (its power is worth
        more) or to the boiler first, up to the boiler's top-up need (on the
        return line the CHP heat only displaces free HEX heat, so a boiler that
        would otherwise buy natural gas values the gas more). Both allocations
        are simulated and the cheaper one, after unmet demand, is kept.

        ``ambient_c`` is the day's outdoor air temperature (see
        :mod:`gemini_design.climate`). Without it the heat-rejection circuit
        sits at the fixed ``cooling_water_c`` and there is no free cooling.
        ``wet_bulb_c`` (the day's air wet-bulb) sets a cooling tower's
        outlet; without it the tower uses ``design_wet_bulb_c``.

        ``ates_cooling_w`` is the cooling the aquifer cold store gives that
        day (planned for the whole year by :mod:`gemini_design.ates`, after
        any free cooling) and ``ates_power_w`` its well-pump and dry-cooler
        electricity, which is drawn on charging days too.

        ``heat_loss_multiplier`` scales the producers' wellbore heat loss
        (see :meth:`DoubletHydraulics.producer` and :mod:`gemini_design.operations`).

        ``ambient_mean_c`` (the day's mean air) sets an ORC unit's condenser,
        which runs all day; without it the ORC uses ``ambient_c``, then
        ``orc_default_air_c``.

        ``day`` (index into ``self.availability``) tells a design with mixed
        doublet depths which doublets may run; the hottest available run first.

        ``electricity_price`` / ``export_price`` (EUR/MWh) replace the flat
        assumptions for this day (daily price profile, :mod:`gemini_design.prices`).

        A heat-recovery heat pump is run or left off, whichever is cheaper that day.
        """
        kw = {
            "day": day,
            "electricity_price": electricity_price,
            "export_price": export_price,
            "ambient_mean_c": ambient_mean_c,
            "ambient_c": ambient_c,
            "wet_bulb_c": wet_bulb_c,
            "ates_cooling_w": ates_cooling_w,
            "ates_power_w": ates_power_w,
            "heat_loss_multiplier": heat_loss_multiplier,
        }
        if getattr(self.design, "heat_recovery_hp_mw", 0.0) > 0 and cooling_w > 0:
            options = [
                self._evaluate_gas_split(heating_w, cooling_w, n_active, flow_m3h, hr, kw)
                for hr in (True, False)
            ]
            return min(options, key=_day_key)
        return self._evaluate_gas_split(heating_w, cooling_w, n_active, flow_m3h, False, kw)

    def _evaluate_gas_split(self, heating_w, cooling_w, n_active, flow_m3h, heat_recovery, kw):
        """Run the day with associated gas to the CHP first and to the boiler first; keep the
        cheaper (see :meth:`evaluate`)."""
        kw = {**kw, "heat_recovery": heat_recovery}
        chp_first = self._evaluate(heating_w, cooling_w, n_active, flow_m3h, **kw)
        if self.chp_gas_capacity <= 0 or n_active == 0 or chp_first["purchased_gas_w"] <= 0:
            return chp_first
        no_chp = self._evaluate(heating_w, cooling_w, n_active, flow_m3h, chp_gas_limit=0.0, **kw)
        gas_mass = no_chp["associated_gas_fuel_w"] / self.gas["lhv"]
        boiler_gas = no_chp["associated_gas_heat_w"] / (
            self.a["boiler_efficiency"] * self.gas["lhv"]
        )
        boiler_first = self._evaluate(
            heating_w,
            cooling_w,
            n_active,
            flow_m3h,
            chp_gas_limit=max(0.0, gas_mass - boiler_gas),
            **kw,
        )

        best = min((chp_first, boiler_first), key=_day_key)
        best["gas_priority"] = "chp" if best is chp_first else "boiler"
        return best

    def free_cooling(self, cooling_w, ambient_c):
        """Return (free cooling W, chilled-water temperature after it) for one day.

        The dry-cooler economizer cools the chilled-water return towards
        ``ambient_c + free_cooling_approach_k`` (never below the supply
        temperature); without the economizer or weather it does nothing.
        """
        a, c = self.a, self.c
        t_return = a["cooling_return_c"]
        if not self.design.free_cooling or ambient_c is None or cooling_w <= 0:
            return 0.0, t_return
        t_fc = max(c["cooling_supply_c"], ambient_c + a["free_cooling_approach_k"])
        if t_fc >= t_return:
            return 0.0, t_return
        water_cap = a["water_density"] * a["water_cp"] * self._chilled_flow(cooling_w)
        return water_cap * (t_return - t_fc), t_fc

    def boiler_part_load_ratio(self, heat_w):
        """Gas boiler efficiency at this day's load over the rated efficiency (1 when off).

        With ``boiler_part_load`` = 1 the boiler is ``boiler_units`` equal units,
        staged so that as few run as possible, all at the same part-load ratio
        (PLR). Fuel relative to full load is HIR(PLR) = a + b PLR + c PLR^2
        (``boiler_hir_fplr_coefficients``; the constant term is the standby and
        cycling loss of a running unit), so efficiency(PLR) = rated x PLR / HIR(PLR).
        """
        if not round(float(self.a.get("boiler_part_load", 0.0))) or heat_w <= 0:
            return 1.0
        units = max(1, int(getattr(self.design, "boiler_units", 1)))
        unit_w = self.design.boiler_capacity_mw * 1e6 / units
        if unit_w <= 0:
            return 1.0
        running = min(units, max(1, math.ceil(heat_w / unit_w - 1e-9)))
        plr = min(1.0, heat_w / (running * unit_w))
        a0, a1, a2 = self.a["boiler_hir_fplr_coefficients"]
        return plr / (a0 + a1 * plr + a2 * plr * plr)

    def _heat_recovery(self, cooling_w, chilled_flow, t_chw_in, t_return, cap_secondary):
        """Heat-recovery heat pump: chilled water -> district return line.

        Returns (cooling W, heat W, power W, return-line outlet degC, chilled-water
        outlet degC). The COP follows the Lorenz cycle of the two streams' mean
        temperatures with ``heat_recovery_approach_k`` on each side, times
        ``heat_pump_eta_lorenz``. The return line is heated at most to
        ``heat_recovery_max_supply_c``; the cooling is limited by the rating, the
        chilled water (down to the 20 degC supply) and that heat sink.
        """
        a, c = self.a, self.c
        water_cap = a["water_density"] * a["water_cp"] * chilled_flow
        q_c = min(
            cooling_w,
            self.design.heat_recovery_hp_mw * 1e6,
            water_cap * max(0.0, t_chw_in - c["cooling_supply_c"]),
        )
        t_max = min(a["heat_recovery_max_supply_c"], c["heating_supply_c"])
        if q_c <= 1.0 or t_return >= t_max - 0.1:
            return 0.0, 0.0, 0.0, t_return, t_chw_in
        dt_app = a["heat_recovery_approach_k"]
        cop_h = 2.0
        for _ in range(30):  # COP <-> outlet temperature fixed point (and the sink limit)
            q_h = q_c * cop_h / (cop_h - 1.0)
            if t_return + q_h / cap_secondary > t_max:
                q_h = cap_secondary * (t_max - t_return)
                q_c = q_h * (cop_h - 1.0) / cop_h
            t_hot = 0.5 * (t_return + t_return + q_h / cap_secondary) + dt_app + 273.15
            t_chw_out = t_chw_in - q_c / water_cap
            t_cold = 0.5 * (t_chw_in + t_chw_out) - dt_app + 273.15
            new = min(a["heat_pump_eta_lorenz"] * t_hot / (t_hot - t_cold), 10.0)
            if abs(new - cop_h) < 1e-6:
                break
            cop_h = new
        if cop_h <= 1.0:
            return 0.0, 0.0, 0.0, t_return, t_chw_in
        q_h = q_c * cop_h / (cop_h - 1.0)
        return q_c, q_h, q_h - q_c, t_return + q_h / cap_secondary, t_chw_in - q_c / water_cap

    def _cooling_water_c(self, ambient_c):
        """Dry-cooler circuit temperature (degC) for the day's outdoor air."""
        if ambient_c is None:
            return self.a["cooling_water_c"]
        return max(self.a["cooling_water_min_c"], ambient_c + self.a["dry_cooler_approach_k"])

    def _chiller_sink_c(self, ambient_c, wet_bulb_c):
        """Heat-sink temperature (degC) the electric chiller's condenser sees.

        Dry cooler: its water loop (as :meth:`_cooling_water_c`). Wet tower:
        the air wet-bulb + tower approach. Air-cooled: the outdoor air itself
        (the chiller's condenser approach is then the air-side one).
        """
        a = self.a
        kind = self.chiller_tech["heat_rejection"]
        if kind == "tower":
            wb = a["design_wet_bulb_c"] if wet_bulb_c is None else wet_bulb_c
            return max(a["cooling_water_min_c"], wb + a["cooling_tower_approach_k"])
        if kind == "air":
            if ambient_c is None:
                return a["cooling_water_c"] - a["dry_cooler_approach_k"]  # design dry-bulb
            return max(a["cooling_water_min_c"] - a["dry_cooler_approach_k"], ambient_c)
        return self._cooling_water_c(ambient_c)

    def _evaluate(
        self,
        heating_w,
        cooling_w,
        n_active,
        flow_m3h,
        chp_gas_limit=None,
        ambient_c=None,
        wet_bulb_c=None,
        ates_cooling_w=0.0,
        ates_power_w=0.0,
        heat_loss_multiplier=1.0,
        ambient_mean_c=None,
        day=None,
        electricity_price=None,
        export_price=None,
        heat_recovery=False,
    ):
        """Run the flowsheet; ``chp_gas_limit`` (kg/s) caps the associated gas the CHP may burn."""
        d, a, c = self.design, self.a, self.c
        price_el = (
            a["electricity_price_eur_per_mwh"] if electricity_price is None else electricity_price
        )
        price_export = (
            a["electricity_export_price_eur_per_mwh"] if export_price is None else export_price
        )
        rho_cp = self.rho * self.cp
        t_supply = c["heating_supply_c"]
        t_return = a["heating_return_c"]
        secondary_flow = heating_w / (rho_cp * (t_supply - t_return))  # m3/s
        chilled_flow = self._chilled_flow(cooling_w)
        t_cw = self._cooling_water_c(ambient_c)

        r = {
            "n_active": n_active,
            "flow_per_doublet_m3h": flow_m3h if n_active else 0.0,
            "heating_demand_w": heating_w,
            "cooling_demand_w": cooling_w,
            "violations": [],
        }

        hyd_kw = {}
        if n_active > 0 and self.grouped:
            available = (
                self.availability[day]
                if self.availability is not None and day is not None
                else None
            )
            hyd_kw["active"] = self.hyd.active(n_active, available)
        if n_active > 0:
            prod = self.hyd.producer(flow_m3h, heat_loss_multiplier, **hyd_kw)
            q_brine = n_active * flow_m3h / 3600.0  # m3/s
            t_wh = prod["wellhead_temperature_c"]  # mixed brine with mixed doublet depths
            t_cap = prod.get("cap_temperature_c", t_wh)  # hottest running producer
            t_inj_min = t_cap - c["brine_cooling_max_k"]

            self.separator.calculate_output(
                {
                    "pressure": prod["wellhead_pressure_bar"],
                    "temperature": t_wh,
                    "flow_rate": q_brine,
                }
            )
            t_brine = self.separator.output["temperature_out"]
            gas_mass = self.separator.output["gas_mass_flow_rate"]  # kg/s
        else:
            prod, q_brine, t_wh, t_inj_min, t_cap = None, 0.0, None, None, None
            t_brine, gas_mass = None, 0.0

        # ---- cooling
        cooling_delivered = 0.0
        chiller_el = 0.0
        absorption_heat = 0.0
        if d.cooling == "absorption" and cooling_w > 0 and n_active > 0:
            self.absorption.calculate_output(
                {
                    "hot_temperature_in": t_brine,
                    "hot_flow_rate": q_brine,
                    "chilled_temperature_in": a["cooling_return_c"],
                    "chilled_flow_rate": chilled_flow,
                    "cooling_water_temperature": t_cw,
                }
            )
            ab = self.absorption.output
            cooling_delivered = ab["cooling_power"]
            absorption_heat = ab["heat_consumed"]
            chiller_el += ab["power_el"]
            t_brine = ab["hot_temperature_out"]
            r["absorption_cop"] = ab["COP"]
        # dry-cooler economizer: pre-cool the chilled-water return against outdoor air
        free_cooling, t_chw_in = self.free_cooling(cooling_w, ambient_c)
        if free_cooling > 0:
            cooling_delivered += free_cooling
            chiller_el += free_cooling * a["free_cooling_fan_power_fraction"]
        # aquifer cold store: pre-cools the chilled-water return after free cooling
        ates_cooling = 0.0
        if ates_cooling_w > 0 and cooling_w > 0:
            water_cap = a["water_density"] * a["water_cp"] * chilled_flow
            ates_cooling = min(
                ates_cooling_w,
                cooling_w - cooling_delivered,
                water_cap * (t_chw_in - c["cooling_supply_c"]),
            )
            ates_cooling = max(0.0, ates_cooling)
            cooling_delivered += ates_cooling
            t_chw_in -= ates_cooling / water_cap
        # heat-recovery heat pump: cools the chilled water, heats the district return line
        hr_cool, hr_heat, hr_el = 0.0, 0.0, 0.0
        cap_secondary = rho_cp * secondary_flow
        t_return_line = t_return
        if heat_recovery and cap_secondary > 0 and cooling_w - cooling_delivered > 1.0:
            hr_cool, hr_heat, hr_el, t_return_line, t_chw_out = self._heat_recovery(
                cooling_w - cooling_delivered, chilled_flow, t_chw_in, t_return, cap_secondary
            )
            if hr_cool > 0:
                cooling_delivered += hr_cool
                t_chw_in = t_chw_out
                r["heat_recovery_cop_heating"] = hr_heat / hr_el
        precooled = free_cooling > 0 or ates_cooling > 0 or hr_cool > 0
        remaining_cooling = cooling_w - cooling_delivered
        t_sink = self._chiller_sink_c(ambient_c, wet_bulb_c)
        tower_water_m3 = 0.0
        if remaining_cooling > 1.0 and self.electric.parameters["capacity_nominal"] > 0:
            self.electric.calculate_output(
                {
                    "chilled_temperature_in": t_chw_in,
                    "chilled_flow_rate": (
                        chilled_flow if precooled else self._chilled_flow(remaining_cooling)
                    ),
                    "cooling_water_temperature": t_sink,
                }
            )
            cooling_delivered += self.electric.output["cooling_power"]
            chiller_el += self.electric.output["power_el"]
            r["electric_chiller_cop"] = self.electric.output["COP"]
            r["electric_chiller_sink_c"] = t_sink
            if self.chiller_tech["heat_rejection"] == "tower":
                cycles = a["cooling_tower_cycles"]
                evaporation = (
                    self.electric.output["heat_rejected"] / a["water_latent_heat_j_per_kg"]
                )
                tower_water_m3 = evaporation * cycles / (cycles - 1.0) / a["water_density"]

        # ---- CHP on associated gas, heat recovered into the district return line
        chp_gas, chp_el, chp_heat = 0.0, 0.0, 0.0
        t_after_chp = t_return_line
        if (
            self.chp_gas_capacity > 0
            and gas_mass > 0
            and secondary_flow > 0
            and (chp_gas_limit is None or chp_gas_limit > 0)
        ):
            heat_room = cap_secondary * (t_supply - t_return_line)
            th_per_kg = self.gas["lhv"] * a["chp_efficiency"] * (1 - CHP.ELECTRICAL_POWER_FRACTION)
            chp_gas = min(gas_mass, self.chp_gas_capacity, heat_room / th_per_kg)
            if chp_gas_limit is not None:
                chp_gas = min(chp_gas, chp_gas_limit)
            self.chp.calculate_output(
                {
                    "temperature_in": t_return_line,
                    "water_flow_rate": secondary_flow,
                    "gas_flow_rate": chp_gas,
                }
            )
            chp_el, chp_heat = self.chp.output["power_el"], self.chp.output["power_th"]
            t_after_chp = self.chp.output["temperature_out"]
        boiler_gas_mass = gas_mass - chp_gas

        # ---- district heating: HEX with bypass so the brine stays within the 40 K cap
        # and the mixed secondary outlet never overshoots the 100 degC supply setpoint
        t_secondary = t_after_chp
        hex_duty = 0.0
        t_inj = t_brine
        if n_active > 0 and secondary_flow > 0:
            fraction = 1.0
            hex_args = (t_brine, q_brine, secondary_flow, n_active)
            t_b, t_s, duty = self._run_hex(*hex_args, fraction, t_after_chp)

            def within_limits(f):
                t_b_f, t_s_f, _ = self._run_hex(*hex_args, f, t_after_chp)
                return t_b_f >= t_inj_min and t_s_f <= t_supply + 1e-9

            if t_b < t_inj_min or t_s > t_supply + 1e-9:
                lo, hi = 0.0, 1.0  # both limits tighten monotonically as more water passes the HEX
                for _ in range(50):
                    mid = 0.5 * (lo + hi)
                    lo, hi = (mid, hi) if within_limits(mid) else (lo, mid)
                fraction = lo
                t_b, t_s, duty = self._run_hex(*hex_args, fraction, t_after_chp)
            r["hex_bypass_fraction"] = 1.0 - fraction
            t_secondary, hex_duty, t_inj = t_s, duty, t_b

        # ---- heat pump on the remaining brine (source floor = 40 K cap)
        hp_heat, hp_el = 0.0, 0.0
        if (
            d.upgrade == "heat_pump"
            and n_active > 0
            and secondary_flow > 0
            and t_secondary < t_supply - 0.1
            and t_inj > t_inj_min + 0.1
            and d.heat_pump_capacity_mw > 0
        ):
            t_target = min(t_supply, t_secondary + d.heat_pump_capacity_mw * 1e6 / cap_secondary)
            if t_target > t_secondary + 0.1:
                self.heat_pump.update_parameters(
                    {"Th_out_target": t_target, "Ts_in_minimum": t_inj_min, "COP_0": 3.0}
                )
                self.heat_pump.calculate_output(
                    {
                        "Th_in": t_secondary,
                        "Ts_in": t_inj,
                        "hot_flow_rate": secondary_flow,
                        "source_flow_rate": q_brine,
                    }
                )
                hp = self.heat_pump.output
                if hp["COP"] > 1.0 and hp["Th_out"] > t_secondary:
                    # Take only the COP from HeatpumpBasic and rebuild both outlet
                    # temperatures from the energy balance (Qh = Qs + W). Its fallback
                    # solve (source pinned at Ts_in_minimum) can overshoot the setpoint
                    # or report a source outlet inconsistent with the heat it delivers.
                    cop = hp["COP"]
                    source_share = 1.0 - 1.0 / cop
                    hp_heat = min(hp["power_th"], cap_secondary * (t_target - t_secondary))
                    source_max = rho_cp * q_brine * (t_inj - t_inj_min)
                    hp_heat = max(0.0, min(hp_heat, source_max / source_share))
                    hp_el = hp_heat / cop
                    t_hp_out = t_secondary + hp_heat / cap_secondary
                    t_src_out = t_inj - hp_heat * source_share / (rho_cp * q_brine)
                    t_secondary, t_inj = t_hp_out, t_src_out
                    r["heat_pump_cop"] = hp["COP"]

        # ---- ORC power unit on the brine the district did not use (down to the 40 K cap)
        orc_heat, orc_el = 0.0, 0.0
        if self.orc.parameters["capacity_net"] > 0 and n_active > 0 and t_inj > t_inj_min + 0.1:
            air = next(
                (t for t in (ambient_mean_c, ambient_c) if t is not None),
                a.get("orc_default_air_c", 10.0),
            )
            self.orc.calculate_output(
                {
                    "hot_temperature_in": t_inj,
                    "hot_flow_rate": q_brine,
                    "air_temperature": air,
                    "hot_temperature_out_min": t_inj_min,
                }
            )
            orc = self.orc.output
            if orc["power_el"] > 0:
                orc_heat, orc_el = orc["heat_in"], orc["power_el"]
                r["orc_inlet_temperature_c"] = t_inj
                r["orc_efficiency"] = orc["efficiency"]
                r["orc_air_c"] = air
                t_inj = orc["hot_temperature_out"]

        # ---- gas boiler top-up to 100 degC (associated gas first)
        boiler_needed = max(0.0, cap_secondary * (t_supply - t_secondary))
        boiler_heat = min(boiler_needed, d.boiler_capacity_mw * 1e6)
        eb_cap = getattr(d, "electric_boiler_mw", 0.0) * 1e6
        eff = a["boiler_efficiency"]
        self.boiler.calculate_output(
            {
                "temperature_in": t_secondary,
                "water_flow_rate": secondary_flow,
                "gas_flow_rate": gas_mass,
            }
        )
        assoc_heat_available = self.boiler.output["power_th"]  # if all gas went to the boiler
        boiler_assoc_capacity = assoc_heat_available * (
            boiler_gas_mass / gas_mass if gas_mass > 0 else 0.0
        )
        assoc_used = min(boiler_assoc_capacity, boiler_heat)
        eb_heat = 0.0
        if eb_cap > 0:
            # top-up beyond the associated gas: cheaper of bought gas and grid electricity first
            # (EUR per MWh of heat, CO2 priced), each within its own capacity
            gas_eur = (
                a["gas_price_eur_per_mwh"]
                + a["co2_price_eur_per_t"] * a["natural_gas_emission_kg_per_gj"] * 3.6 / 1000.0
            ) / eff
            eb_eur = (
                price_el + a["co2_price_eur_per_t"] * a["electricity_emission_kg_per_kwh"]
            ) / a["electric_boiler_efficiency"]
            rest = boiler_needed - assoc_used
            gas_room = d.boiler_capacity_mw * 1e6 - assoc_used
            if eb_eur < gas_eur:
                eb_heat = min(rest, eb_cap)
                boiler_heat = assoc_used + min(rest - eb_heat, gas_room)
            else:
                boiler_heat = assoc_used + min(rest, gas_room)
                eb_heat = min(rest - (boiler_heat - assoc_used), eb_cap)
        eb_el = eb_heat / a["electric_boiler_efficiency"]
        # part load: the running units' efficiency falls at low load (boiler_part_load)
        ratio = self.boiler_part_load_ratio(boiler_heat)
        if ratio != 1.0:
            eff *= ratio
            assoc_heat_available *= ratio
            boiler_assoc_capacity *= ratio
            assoc_used = min(boiler_assoc_capacity, boiler_heat)
            r["boiler_efficiency_day"] = eff
        purchased_gas_w = (boiler_heat - assoc_used) / eff  # fuel energy, LHV
        unmet_heat = boiler_needed - boiler_heat - eb_heat

        # ---- pumps
        esp_el, inj_el = 0.0, 0.0
        if n_active > 0:
            inj = self.hyd.injector(flow_m3h, t_inj, **hyd_kw)
            esp_el = n_active * prod["esp_power_w"]
            inj_el = n_active * inj["pump_power_w"]
            r.update(
                {
                    "wellhead_temperature_c": t_wh,
                    "injection_temperature_c": t_inj,
                    "brine_cooling_k": t_cap - t_inj,
                    "esp_dp_bar": prod["esp_dp_bar"],
                    "esp_depth_m": prod["esp_depth_m"],
                    "gas_breakout_depth_m": prod["gas_breakout_depth_m"],
                    "injector_wellhead_pressure_bar": inj["wellhead_pressure_bar"],
                    "drawdown_bar": prod["drawdown_bar"],
                }
            )
            if self.grouped:
                r["hottest_wellhead_temperature_c"] = t_cap
                r["active_doublets"] = ",".join(str(i + 1) for i in hyd_kw["active"])
            if t_cap - t_inj > c["brine_cooling_max_k"] + 1e-6:
                r["violations"].append("brine_cooling_above_40K")
            if not c["flow_min_m3h"] - 1e-9 <= flow_m3h <= c["flow_max_m3h"] + 1e-9:
                r["violations"].append("flow_outside_50_300")
            if not prod["esp_intake_ok"]:
                r["violations"].append("esp_intake_below_bubble_point")
            if "esp_in_range" in prod:  # sized ESP (gemini_design.esp)
                r.update(
                    {
                        k: prod[k]
                        for k in (
                            "esp_pump_dp_bar",
                            "esp_choke_bar",
                            "esp_speed_ratio",
                            "esp_efficiency",
                            "esp_flow_ratio",
                        )
                    }
                )
                if not prod["esp_in_range"]:
                    r["violations"].append("esp_outside_operating_range")

        geo_heat = q_brine * rho_cp * (t_wh - t_inj) if n_active else 0.0
        electricity = esp_el + inj_el + hp_el + chiller_el + ates_power_w + hr_el + eb_el
        generation = chp_el + orc_el
        grid_import = max(0.0, electricity - generation)
        grid_export = max(0.0, generation - electricity)
        assoc_fuel = gas_mass * self.gas["lhv"]
        flared_fuel = max(0.0, assoc_fuel - chp_gas * self.gas["lhv"] - assoc_used / eff)

        # ---- emissions (kg/s) and cost (EUR/s)
        gas_props = self.gas
        assoc_co2 = gas_mass * (
            gas_props["co2_mass_fraction"] + gas_props["ch4_mass_fraction"] * 44.01 / 16.04
        )  # all associated gas is burned (boiler or flare)
        purchased_co2 = purchased_gas_w * a["natural_gas_emission_kg_per_gj"] / 1e9
        electric_co2 = grid_import * a["electricity_emission_kg_per_kwh"] / 3.6e6
        co2 = assoc_co2 + purchased_co2 + electric_co2
        cost = (
            grid_import / 3.6e9 * price_el
            - grid_export / 3.6e9 * price_export
            + purchased_gas_w / 3.6e9 * a["gas_price_eur_per_mwh"]
            + co2 / 1000.0 * a["co2_price_eur_per_t"]
            + tower_water_m3 * a["water_price_eur_per_m3"]
        )

        r.update(
            {
                "heat_delivered_w": heating_w - unmet_heat,
                "unmet_heat_w": unmet_heat,
                "cooling_delivered_w": cooling_delivered,
                "free_cooling_w": free_cooling,
                "ates_cooling_w": ates_cooling,
                "ates_power_w": ates_power_w,
                "tower_water_m3_s": tower_water_m3,
                "cooling_water_c": t_cw,
                "unmet_cooling_w": max(0.0, cooling_w - cooling_delivered),
                "geothermal_heat_w": geo_heat,
                "hex_heat_w": hex_duty,
                "absorption_heat_w": absorption_heat,
                "heat_pump_heat_w": hp_heat,
                "boiler_heat_w": boiler_heat,
                "electric_boiler_heat_w": eb_heat,
                "electric_boiler_power_w": eb_el,
                "heat_recovery_cooling_w": hr_cool,
                "heat_recovery_heat_w": hr_heat,
                "heat_recovery_power_w": hr_el,
                "associated_gas_heat_w": assoc_used,
                "associated_gas_available_w": assoc_heat_available,
                "associated_gas_fuel_w": assoc_fuel,
                "associated_gas_flared_w": flared_fuel,
                "chp_fuel_w": chp_gas * self.gas["lhv"],
                "chp_heat_w": chp_heat,
                "chp_power_el_w": chp_el,
                "orc_heat_w": orc_heat,
                "orc_power_el_w": orc_el,
                "grid_import_w": grid_import,
                "grid_export_w": grid_export,
                "purchased_gas_w": purchased_gas_w,
                "esp_power_w": esp_el,
                "injection_pump_power_w": inj_el,
                "heat_pump_power_w": hp_el,
                "chiller_power_w": chiller_el,
                "electricity_w": electricity,
                "co2_kg_s": co2,
                "cost_eur_s": cost,
                "supply_temperature_c": (
                    t_supply
                    if unmet_heat < 1.0
                    else t_secondary + (boiler_heat + eb_heat) / max(cap_secondary, 1e-9)
                ),
            }
        )
        return r


def _day_key(r):
    """Rank day results: least unmet energy first, then cost."""
    return (round(r["unmet_heat_w"] + r["unmet_cooling_w"]), r["cost_eur_s"])
