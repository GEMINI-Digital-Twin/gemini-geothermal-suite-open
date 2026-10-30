"""Daily plant flowsheet: geothermal doublets + upgrade + cooling, built from GEMINI models.

Primary (brine) path, per active doublet sharing the load equally::

    producer well (ESP) -> separator (gas off) -> [absorption chiller generator]
        -> district heating HEX -> [heat pump evaporator] -> injection pump -> injector well

Secondary (district heating) path::

    return 40 degC -> [CHP heat recovery] -> HEX (with bypass) -> [heat pump condenser]
        -> [gas boiler] -> 100 degC supply

Co-produced (associated) gas from the separator fuels the CHP first (its
electricity offsets the pumps, heat pump and chillers; any surplus is
exported), then the boiler; the boiler buys natural gas for the rest.
Associated gas that neither burns is flared, and its CO2 is counted either way.

Cooling path (20 degC supply): absorption chiller driven by brine, or an
electric chiller, plus an optional electric backup chiller.

The HEX bypass keeps the brine from being cooled by more than the
challenge's 40 K; the heat pump's minimum source outlet temperature is set
to the same limit, so no component can break that hard cap.
"""

from dataclasses import dataclass, field

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, associated_gas_properties
from gemini_model.boiler.boiler import Boiler
from gemini_model.chiller.absorption_chiller import AbsorptionChiller
from gemini_model.chiller.electric_chiller import ElectricChiller
from gemini_model.chp.chp import CHP
from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger
from gemini_model.heatpump.heatpump_basic import HeatpumpBasic
from gemini_model.separator.separator import Separator

UPGRADES = ("boiler", "heat_pump")
COOLING = ("absorption", "electric")


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
    name: str = ""
    notes: list = field(default_factory=list)

    def __post_init__(self):
        """Fill a default name and check the categorical choices."""
        if self.upgrade not in UPGRADES:
            raise ValueError(f"upgrade must be one of {UPGRADES}, got '{self.upgrade}'")
        if self.cooling not in COOLING:
            raise ValueError(f"cooling must be one of {COOLING}, got '{self.cooling}'")
        if not self.name:
            self.name = f"{self.n_doublets}D-{int(self.depth_m)}m-{self.upgrade}-{self.cooling}"
            if self.chp_capacity_mw_el > 0:
                self.name += "-chp"

    def as_dict(self):
        """Return the design as a plain dict (for JSON reports and agent context)."""
        return {k: v for k, v in self.__dict__.items() if k != "notes"}


class Plant:
    """Evaluates one day of plant operation for a design."""

    def __init__(self, design, hydraulics, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
        """Build the GEMINI component models once for a design."""
        self.design = design
        self.hyd = hydraulics
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
        self.electric = ElectricChiller()
        self.electric.update_parameters(
            {
                "capacity_nominal": electric_capacity * 1e6,
                "eta_carnot": assumptions["electric_chiller_eta_carnot"],
                "cop_max": assumptions["electric_chiller_cop_max"],
                "evaporator_approach": assumptions["electric_chiller_evaporator_approach_k"],
                "condenser_approach": assumptions["electric_chiller_condenser_approach_k"],
                "units": assumptions["electric_chiller_units"],
                "aux_power_fraction": assumptions["chiller_aux_power_fraction"],
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
    def evaluate(self, heating_w, cooling_w, n_active, flow_m3h):
        """Simulate one steady day; return energy flows, temperatures and checks.

        ``flow_m3h`` is the production (= injection) rate of each active doublet.
        """
        d, a, c = self.design, self.a, self.c
        rho_cp = self.rho * self.cp
        t_supply = c["heating_supply_c"]
        t_return = a["heating_return_c"]
        secondary_flow = heating_w / (rho_cp * (t_supply - t_return))  # m3/s
        chilled_flow = self._chilled_flow(cooling_w)

        r = {
            "n_active": n_active,
            "flow_per_doublet_m3h": flow_m3h if n_active else 0.0,
            "heating_demand_w": heating_w,
            "cooling_demand_w": cooling_w,
            "violations": [],
        }

        if n_active > 0:
            prod = self.hyd.producer(flow_m3h)
            q_brine = n_active * flow_m3h / 3600.0  # m3/s
            t_wh = prod["wellhead_temperature_c"]
            t_inj_min = t_wh - c["brine_cooling_max_k"]

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
            prod, q_brine, t_wh, t_inj_min = None, 0.0, None, None
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
                    "cooling_water_temperature": a["cooling_water_c"],
                }
            )
            ab = self.absorption.output
            cooling_delivered = ab["cooling_power"]
            absorption_heat = ab["heat_consumed"]
            chiller_el += ab["power_el"]
            t_brine = ab["hot_temperature_out"]
            r["absorption_cop"] = ab["COP"]
        remaining_cooling = cooling_w - cooling_delivered
        if remaining_cooling > 1.0 and self.electric.parameters["capacity_nominal"] > 0:
            self.electric.calculate_output(
                {
                    "chilled_temperature_in": a["cooling_return_c"],
                    "chilled_flow_rate": self._chilled_flow(remaining_cooling),
                    "cooling_water_temperature": a["cooling_water_c"],
                }
            )
            cooling_delivered += self.electric.output["cooling_power"]
            chiller_el += self.electric.output["power_el"]
            r["electric_chiller_cop"] = self.electric.output["COP"]

        # ---- CHP on associated gas, heat recovered into the district return line
        cap_secondary = rho_cp * secondary_flow
        chp_gas, chp_el, chp_heat = 0.0, 0.0, 0.0
        t_after_chp = t_return
        if self.chp_gas_capacity > 0 and gas_mass > 0 and secondary_flow > 0:
            heat_room = cap_secondary * (t_supply - t_return)
            th_per_kg = self.gas["lhv"] * a["chp_efficiency"] * (1 - CHP.ELECTRICAL_POWER_FRACTION)
            chp_gas = min(gas_mass, self.chp_gas_capacity, heat_room / th_per_kg)
            self.chp.calculate_output(
                {
                    "temperature_in": t_return,
                    "water_flow_rate": secondary_flow,
                    "gas_flow_rate": chp_gas,
                }
            )
            chp_el, chp_heat = self.chp.output["power_el"], self.chp.output["power_th"]
            t_after_chp = self.chp.output["temperature_out"]
        boiler_gas_mass = gas_mass - chp_gas

        # ---- district heating: HEX with bypass so the brine stays within the 40 K cap
        t_secondary = t_after_chp
        hex_duty = 0.0
        t_inj = t_brine
        if n_active > 0 and secondary_flow > 0:
            fraction = 1.0
            hex_args = (t_brine, q_brine, secondary_flow, n_active)
            t_b, t_s, duty = self._run_hex(*hex_args, fraction, t_after_chp)
            if t_b < t_inj_min:
                lo, hi = 0.0, 1.0
                for _ in range(40):
                    mid = 0.5 * (lo + hi)
                    t_b_mid, _, _ = self._run_hex(*hex_args, mid, t_after_chp)
                    lo, hi = (mid, hi) if t_b_mid >= t_inj_min else (lo, mid)
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
                    hp_heat, hp_el = hp["power_th"], hp["power_el"]
                    t_hp_out, t_src_out = hp["Th_out"], hp["Ts_out"]
                    if t_hp_out > t_target + 0.05:
                        # HeatpumpBasic's fallback solve (source pinned at its minimum) can
                        # overshoot the target when the source is rich; a real unit
                        # modulates down to the setpoint at the same COP instead.
                        hp_heat = cap_secondary * (t_target - t_secondary)
                        hp_el = hp_heat / hp["COP"]
                        t_hp_out = t_target
                        t_src_out = t_inj - (hp_heat - hp_el) / (rho_cp * q_brine)
                    t_secondary, t_inj = t_hp_out, t_src_out
                    r["heat_pump_cop"] = hp["COP"]

        # ---- gas boiler top-up to 100 degC (associated gas first)
        boiler_needed = max(0.0, cap_secondary * (t_supply - t_secondary))
        boiler_heat = min(boiler_needed, d.boiler_capacity_mw * 1e6)
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
        purchased_gas_w = (boiler_heat - assoc_used) / eff  # fuel energy, LHV
        unmet_heat = boiler_needed - boiler_heat

        # ---- pumps
        esp_el, inj_el = 0.0, 0.0
        if n_active > 0:
            inj = self.hyd.injector(flow_m3h, t_inj)
            esp_el = n_active * prod["esp_power_w"]
            inj_el = n_active * inj["pump_power_w"]
            r.update(
                {
                    "wellhead_temperature_c": t_wh,
                    "injection_temperature_c": t_inj,
                    "brine_cooling_k": t_wh - t_inj,
                    "esp_dp_bar": prod["esp_dp_bar"],
                    "esp_depth_m": prod["esp_depth_m"],
                    "injector_wellhead_pressure_bar": inj["wellhead_pressure_bar"],
                    "drawdown_bar": prod["drawdown_bar"],
                }
            )
            if t_wh - t_inj > c["brine_cooling_max_k"] + 1e-6:
                r["violations"].append("brine_cooling_above_40K")
            if not c["flow_min_m3h"] - 1e-9 <= flow_m3h <= c["flow_max_m3h"] + 1e-9:
                r["violations"].append("flow_outside_50_300")

        geo_heat = q_brine * rho_cp * (t_wh - t_inj) if n_active else 0.0
        electricity = esp_el + inj_el + hp_el + chiller_el
        grid_import = max(0.0, electricity - chp_el)
        grid_export = max(0.0, chp_el - electricity)
        assoc_fuel = gas_mass * self.gas["lhv"]
        flared_fuel = max(
            0.0, assoc_fuel - chp_gas * self.gas["lhv"] - assoc_used / a["boiler_efficiency"]
        )

        # ---- emissions (kg/s) and cost (EUR/s)
        gas_props = self.gas
        assoc_co2 = gas_mass * (
            gas_props["co2_mass_fraction"] + gas_props["ch4_mass_fraction"] * 44.01 / 16.04
        )  # all associated gas is burned (boiler or flare)
        purchased_co2 = purchased_gas_w * a["natural_gas_emission_kg_per_gj"] / 1e9
        electric_co2 = grid_import * a["electricity_emission_kg_per_kwh"] / 3.6e6
        co2 = assoc_co2 + purchased_co2 + electric_co2
        cost = (
            grid_import / 3.6e9 * a["electricity_price_eur_per_mwh"]
            - grid_export / 3.6e9 * a["electricity_export_price_eur_per_mwh"]
            + purchased_gas_w / 3.6e9 * a["gas_price_eur_per_mwh"]
            + co2 / 1000.0 * a["co2_price_eur_per_t"]
        )

        r.update(
            {
                "heat_delivered_w": heating_w - unmet_heat,
                "unmet_heat_w": unmet_heat,
                "cooling_delivered_w": cooling_delivered,
                "unmet_cooling_w": max(0.0, cooling_w - cooling_delivered),
                "geothermal_heat_w": geo_heat,
                "hex_heat_w": hex_duty,
                "absorption_heat_w": absorption_heat,
                "heat_pump_heat_w": hp_heat,
                "boiler_heat_w": boiler_heat,
                "associated_gas_heat_w": assoc_used,
                "associated_gas_available_w": assoc_heat_available,
                "associated_gas_fuel_w": assoc_fuel,
                "associated_gas_flared_w": flared_fuel,
                "chp_fuel_w": chp_gas * self.gas["lhv"],
                "chp_heat_w": chp_heat,
                "chp_power_el_w": chp_el,
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
                    else t_secondary + boiler_heat / max(cap_secondary, 1e-9)
                ),
            }
        )
        return r
