"""GEMINI hackathon tasks 3-5: daily heating + cooling model for one design candidate.

Per day, per active doublet (all active doublets run at the same flow):
- GEMINI runs the brine chain at the dispatched flow, from
  projects/doublet_challenge.json: producer + ESP -> separator -> filter_a ->
  absorber generator -> HEX -> filter_b -> injector. The absorber generator is a
  GEMINI filter with zero resistance whose temperature drop is the absorption
  chiller's drive heat (hot end of the brine, inlet >= 75 C, outlet >= 70 C).
- Downstream is a setpoint energy balance (this module): district water 60 C
  -> HEX -> heat pump (Lorenz, sink out 100 C, COP capped; source = brine
  leaving the HEX, not below T_wellhead - 40 K + filter_b drop) -> 100 C
  top-up by the GEMINI CHP model on produced gas -> boiler (remaining produced
  gas, then external gas). The heat pump only covers the lift that CHP heat
  cannot, so produced gas is flared only if its heat cannot be used. CHP
  electricity offsets the ESP / injector / heat pump / chiller load.
  Cooling: absorption chiller first, electric chiller for the remainder.
- Dispatch: fewest active doublets, then lowest flow on the 5 m3/h grid, that
  meets heating (HEX + heat pump + CHP reach 100 C) and cooling (absorption)
  without external gas or electric chilling; otherwise all available doublets
  at maximum flow.
- 330-day rule: 35 consecutive maintenance days per doublet, non-overlapping,
  in the lowest-need part of the summer window.

The heat pump solves HeatpumpBasic's own two equations (Lorenz COP + energy
balance) with a bracketing root finder, because HeatpumpBasic's Nelder-Mead
solve is not robust (outputs/evidence/heatpumpbasic_issue.md); HeatpumpBasic's
COP is logged as a cross-check. The dispatch search evaluates the same GEMINI
HeatExchanger model directly; the chosen flow is then run through the full
GEMINI chain and the two are compared.
"""

from __future__ import annotations

import copy
import math
from datetime import date, timedelta
from pathlib import Path

from constraints import PASS, check_constraints, load_limits
from gas_solubility import dissolution_check
from doublet_model import (
    CHALLENGE_PATH,
    PROJECT_PATH,
    ROOT,
    boundary,
    derived_wellhead_temperature_c,
    install_brine_pvt,
    install_scaled_esp,
    load_json,
    solve_producer_controls,
)
from gemini_model.chp.chp import CHP
from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger
from gemini_model.heatpump.heatpump_basic import HeatpumpBasic
from gemini_simulator.project_loader import build_project
from scipy.optimize import brentq

CANDIDATES_PATH = ROOT / "projects" / "candidates_2027.json"
BRINE_CHAIN = ("producer_well", "separator", "filter_a", "heat_exchanger", "filter_b", "injector_well")
ABSORBER = "absorber_generator"
HP_COP_REL_TOLERANCE = 0.01  # HeatpumpBasic cross-check agreement
CO2_KG_PER_NM3 = 1.9635      # DERIVED 44.01 g/mol / 22.414 L/mol
UNMET_TOLERANCE_MW = 1e-3    # daily unmet heating/cooling above 1 kW fails demand_met_365
GRAVITY = 9.81
HP_MIN_SOURCE_DT_K = 1e-3  # heat pump runs only if the brine is at least this far above its minimum


def brine_chain_project(project: dict) -> dict:
    """Brine-chain subset of a plant project, with the absorber generator between filter_a and the HEX.

    HEX secondary flow becomes a boundary input.
    """
    chain = copy.deepcopy(project)
    chain["components"] = {k: v for k, v in chain["components"].items() if k in BRINE_CHAIN}
    chain["components"][ABSORBER] = {
        "type": "filter",
        "_description": "Absorption chiller generator: zero resistance; temperature_drop = drive heat / (m_dot * cp), set per day.",
        "parameters": {"base_resistance": 0.0, "fouling_coeff_a": 0.0, "fouling_coeff_b": 0.0, "temperature_drop": 0.0},
    }
    connections = []
    for c in chain["connections"]:
        if c["predecessor"] not in BRINE_CHAIN or c["successor"] not in BRINE_CHAIN:
            continue
        if c["predecessor"] == "filter_a" and c["successor"] == "heat_exchanger":
            connections.append({"predecessor": "filter_a", "successor": ABSORBER,
                                "ports": [["pressure_out", "pressure"], ["temperature_out", "temperature"], ["flow_rate", "flow_rate"]]})
            connections.append({"predecessor": ABSORBER, "successor": "heat_exchanger",
                                "ports": [["pressure_out", "pressure_in"], ["temperature_out", "primary_temperature_in"], ["flow_rate", "primary_flow_rate"]]})
        else:
            connections.append(c)
    chain["connections"] = connections
    chain["boundary_inputs"] = [b for b in chain["boundary_inputs"] if b["component"] in BRINE_CHAIN]
    chain["boundary_inputs"].append({"component": "heat_exchanger", "key": "secondary_flow_rate", "value": 0.0})
    return chain


def maintenance_schedule(need_w: dict, n_doublets: int, window: tuple[date, date], length: int) -> list[list[date]]:
    """Greedy non-overlapping ``length``-day windows with the lowest summed need, one per doublet."""
    starts = [window[0] + timedelta(days=i) for i in range((window[1] - window[0]).days - length + 2)]
    ranked = sorted(starts, key=lambda s: sum(need_w[s + timedelta(days=i)] for i in range(length)))
    chosen = []
    for start in ranked:
        span = {start + timedelta(days=i) for i in range(length)}
        if all(span.isdisjoint(other) for other in chosen):
            chosen.append(span)
        if len(chosen) == n_doublets:
            break
    if len(chosen) < n_doublets:
        raise ValueError(f"cannot fit {n_doublets} non-overlapping {length}-day windows in {window}")
    return [sorted(span) for span in sorted(chosen, key=min)]


class Plant:
    """One design candidate: n identical doublets + surface heating/cooling plant."""

    def __init__(self, candidate: dict, settings: dict, project_path: Path = PROJECT_PATH, challenge_path: Path = CHALLENGE_PATH):
        self.candidate = candidate
        self.settings = settings
        project = load_json(project_path)
        self.challenge = load_json(challenge_path)
        self.limits = load_limits()
        pvt = install_brine_pvt(project["_brine_pvt_override"])
        install_scaled_esp()
        self.rho, self.cp = pvt["RHOL"], pvt["CPL"]
        self.pump_eff = self.limits["pump_efficiency"]

        components = project["components"]
        components["producer_well"]["parameters"]["esp"].update(settings["esp_options"][candidate["esp"]])
        components["heat_exchanger"]["parameters"]["heat_transfer_coefficient"] = candidate["hex_ua_W_K"]
        self.apply_depth(components, candidate.get("depth_m", self.challenge["reservoir"]["midpoint_depth_m_TVD"]))
        self.chain = brine_chain_project(project)
        self.producer_params = self.chain["components"]["producer_well"]["parameters"]
        self.hex_params = self.chain["components"]["heat_exchanger"]["parameters"]
        self.rho_s, self.cp_s = self.hex_params["fluid_density"], self.hex_params["specific_heat"]
        self.drop_to_absorber = sum(components[n]["parameters"]["temperature_drop"] for n in ("separator", "filter_a"))
        self.drop_after_hex = components["filter_b"]["parameters"]["temperature_drop"]
        self.glr = components["separator"]["parameters"]["gas_water_ratio"]
        self.boiler_eff = components["boiler"]["parameters"]["efficiency_factor"]
        self.chp_params = components["chp"]["parameters"]
        gas = components["boiler"]["parameters"]
        self.gas_density = gas["gas_density"]
        self.produced_gas_lhv_j_nm3 = gas["caloric_value"] * gas["gas_density"]
        self.produced_gas_ef = gas["gas_emission_factor"]
        self.gas_mode, self.gas_handling_kwh_per_nm3 = self.gas_handling(gas)
        self.el_factor = self.producer_params["esp"]["electricity_emission_factor"]
        self.t_return = boundary(self.chain, "heat_exchanger", "secondary_temperature_in")["value"]
        self.t_supply = self.limits["heating_supply_temperature_C"]
        self.t_nominal = boundary(self.chain, "producer_well", "wellhead_temperature")["value"]
        self.hp = settings["heat_pump"]
        self.absorption = settings["absorption_chiller"]
        self.controls_cache = {}
        self.esp_placement = self.place_esp()
        self.flow_grid = self._flow_grid()
        self.engineering = self.engineering_checks()
        self.gas_dissolution = None

    def gas_handling(self, gas: dict) -> tuple[str, float]:
        """Produced-gas option (design variable) -> (mode, handling electricity in kWh per Nm3 of produced gas).
        Sets the produced-gas emission factor: co2_reinject counts only CH4 combustion CO2 (DERIVED),
        reinject_all burns nothing."""
        cfg = self.settings.get("gas_handling", {})
        mode = self.candidate.get("gas_handling", cfg.get("default", "chp"))
        fluid = self.challenge["fluid"]
        x_ch4 = fluid["gas_methane_mol_percent"] / 100
        x_co2 = 1 - x_ch4
        if mode == "chp":
            return mode, 0.0
        if mode == "co2_reinject":
            self.produced_gas_ef = gas["gas_emission_factor"] * x_ch4 / (x_ch4 + x_co2)
            return mode, x_co2 * CO2_KG_PER_NM3 * cfg["separation_compression_kWh_per_kg_CO2"]
        if mode == "reinject_all":
            self.produced_gas_ef = 0.0
            return mode, gas["gas_density"] * cfg["reinjection_compression_kWh_per_kg_gas"]
        raise ValueError(f"unknown gas_handling {mode!r}")

    # --- brine side -------------------------------------------------------
    def apply_depth(self, components: dict, depth_m: float):
        """Reservoir midpoint at ``depth_m`` TVD (vertical wells to that depth).

        T from the official gradient (via self.challenge); P hydrostatic from the
        official 250 bar at 2500 m: P = 250 + rho*g*(z - 2500) (DERIVED).
        """
        reservoir = self.challenge["reservoir"]
        ref_depth, ref_pressure = reservoir["midpoint_depth_m_TVD"], reservoir["pressure_bar_g"]
        self.depth_m = depth_m
        self.reservoir_pressure_bar = ref_pressure + self.rho * GRAVITY * (depth_m - ref_depth) / 1e5
        reservoir["midpoint_depth_m_TVD"] = depth_m
        reservoir["pressure_bar_g"] = self.reservoir_pressure_bar
        self.reservoir_temperature_c = reservoir["surface_temperature_C"] + reservoir["gradient_C_per_km"] * depth_m / 1000
        for name in ("producer_well", "injector_well"):
            params = components[name]["parameters"]
            params["reservoir_pressure_bar"] = self.reservoir_pressure_bar
            params["trajectory_table"][-1].update(MD=depth_m, TVD=depth_m)

    def controls(self, q_m3h: float) -> dict:
        if q_m3h not in self.controls_cache:
            self.controls_cache[q_m3h] = solve_producer_controls(self.chain, q_m3h, self.t_nominal)
        return self.controls_cache[q_m3h]

    def esp_intake_at(self, esp_depth_m: float, q_m3h: float) -> tuple[float, float]:
        """ESP intake pressure (bar) with the pump at ``esp_depth_m``, at q or the ESP maximum if lower."""
        self.producer_params["esp_depth_m"] = esp_depth_m
        self.controls_cache.clear()
        c = self.controls(q_m3h)
        q = q_m3h if c["reached"] else float(int(c["max_flow_m3h"]))
        return self.run_gemini_chain(q, 0.01, 0.0)["esp_intake_bar"], q

    def place_esp(self) -> dict:
        """ESP setting depth (design variable): the shallowest depth, on the placement step, with the
        intake >= min_intake_bar at the flow cap (ASSUMED gas-handling limit; free gas not modelled).
        The intake is close to linear in setting depth, so a secant guess plus a step check suffices."""
        cfg = self.settings["esp_placement"]
        q_cap = self.candidate.get("flow_cap_m3h", self.limits["flow_max_m3_per_h_per_doublet"])
        step, p_min = cfg["depth_step_m"], cfg["min_intake_bar"]
        deepest = self.depth_m - cfg["min_clearance_above_reservoir_m"]
        d0, d1 = cfg["start_depth_m"], cfg["start_depth_m"] + 100
        p0, _ = self.esp_intake_at(d0, q_cap)
        p1, _ = self.esp_intake_at(d1, q_cap)
        guess = d0 + (p_min - p0) * (d1 - d0) / (p1 - p0)
        depth = min(deepest, max(step, math.ceil(guess / step) * step))
        p, q = self.esp_intake_at(depth, q_cap)
        while p < p_min and depth + step <= deepest:
            depth += step
            p, q = self.esp_intake_at(depth, q_cap)
        while depth - step >= step and self.esp_intake_at(depth - step, q_cap)[0] >= p_min:
            depth -= step
        p, q = self.esp_intake_at(depth, q_cap)
        return {"esp_depth_m": depth, "intake_bar": p, "flow_m3h": q, "min_intake_bar": p_min, "deepest_allowed_m": deepest}

    def engineering_checks(self) -> list[dict]:
        """Hard engineering checks at the maximum dispatchable flow: ESP intake and tubing velocity."""
        e = self.esp_placement
        v_max = self.settings["well_checks"]["max_tubing_velocity_m_s"]
        ids = [st["ID"] for w in ("producer_well", "injector_well")
               for st in self.chain["components"][w]["parameters"]["trajectory_table"]]
        velocity = self.max_flow_m3h / 3600 / (math.pi / 4 * min(ids) ** 2)
        return [
            {"check": "esp_intake_pressure", "scope": "producer_well", "status": PASS if e["intake_bar"] >= e["min_intake_bar"] - 1e-6 else "FAIL",
             "value": e["intake_bar"], "limit": f">= {e['min_intake_bar']:g} bar at {e['flow_m3h']:g} m3/h",
             "reason": f"ESP set at {e['esp_depth_m']:g} m (deepest allowed {e['deepest_allowed_m']:g} m): intake {e['intake_bar']:.2f} bar"},
            {"check": "tubing_velocity", "scope": "producer_well + injector_well", "status": PASS if velocity <= v_max else "FAIL",
             "value": velocity, "limit": f"<= {v_max:g} m/s",
             "reason": f"{self.max_flow_m3h:g} m3/h in ID {min(ids):g} m: {velocity:.2f} m/s"},
        ]

    def _flow_grid(self) -> list[float]:
        """Dispatchable flows: 50 m3/h .. min(300, ESP maximum) on the dispatch step."""
        step = self.settings["dispatch"]["flow_step_m3h"]
        q_min, q_limit = self.limits["flow_min_when_on_m3_per_h_per_doublet"], self.limits["flow_max_m3_per_h_per_doublet"]
        q_max = self.candidate.get("flow_cap_m3h", q_limit)
        if not q_min <= q_max <= q_limit:
            raise ValueError(f"flow cap {q_max} m3/h outside the challenge range {q_min}-{q_limit} m3/h")
        self.flow_cap_m3h = q_max
        top = self.controls(q_max)
        q_top = q_max if top["reached"] else float(int(top["max_flow_m3h"]))
        self.max_flow_m3h = q_top
        grid = [float(q) for q in range(int(q_min), int(q_top) + 1, step)]
        if grid[-1] != q_top:
            grid.append(q_top)
        # Flows the ESP/choke cannot hold (e.g. 50 m3/h in deep wells) are not dispatchable.
        self.unreachable_flows_m3h = [q for q in grid if not self.controls(q)["reached"]]
        grid = [q for q in grid if q not in self.unreachable_flows_m3h]
        if not grid:
            raise ValueError(f"no flow in {q_min}-{q_max} m3/h reachable with ESP {self.candidate['esp']}")
        return grid

    def wellhead_temperature(self, q_m3h: float) -> float:
        return derived_wellhead_temperature_c(q_m3h, self.producer_params, self.challenge, self.rho, self.cp)["T_wellhead_C"]

    def hex_model(self, q_m3h: float, t_hex_in: float, secondary_m3s: float) -> dict:
        hx = HeatExchanger()
        hx.update_parameters(self.hex_params)
        hx.calculate_output({
            "pressure_in": 0.0, "primary_temperature_in": t_hex_in, "secondary_temperature_in": self.t_return,
            "primary_flow_rate": q_m3h / 3600, "secondary_flow_rate": secondary_m3s,
        })
        return hx.get_output()

    def run_gemini_chain(self, q_m3h: float, secondary_m3s: float, absorber_drop_k: float) -> dict:
        """Full GEMINI brine chain for one doublet at the dispatched flow."""
        controls = self.controls(q_m3h)
        project = copy.deepcopy(self.chain)
        project["components"]["producer_well"]["parameters"]["esp_freq_hz"] = controls["esp_freq_hz"]
        project["components"][ABSORBER]["parameters"]["temperature_drop"] = absorber_drop_k
        boundary(project, "producer_well", "wellhead_pressure")["value"] = controls["wellhead_pressure_bar"]
        boundary(project, "producer_well", "wellhead_temperature")["value"] = self.wellhead_temperature(q_m3h)
        boundary(project, "heat_exchanger", "secondary_flow_rate")["value"] = secondary_m3s
        solver = build_project(project)
        solver.run()
        out = solver.get_output
        q_m3s = out("producer_well", "flow_rate_m3s")
        esp_dp = (out("producer_well", "esp_discharge_pressure") - out("producer_well", "esp_intake_pressure")) * 1e5
        inj_dp = max(0.0, out("injector_well", "wellhead_pressure_pa") - out("filter_b", "pressure_out_pa"))
        return {
            "controls": controls,
            "production_m3h": out("producer_well", "flow_rate"),
            "injection_m3h": out("filter_b", "flow_rate_m3h"),
            "T_wellhead_C": out("producer_well", "temperature_out"),
            "wellhead_pressure_bar": out("producer_well", "pressure_out"),
            "esp_intake_bar": out("producer_well", "esp_intake_pressure"),
            "esp_discharge_bar": out("producer_well", "esp_discharge_pressure"),
            "injector_wellhead_bar": out("injector_well", "wellhead_pressure"),
            "T_absorber_in_C": out("filter_a", "temperature_out"),
            "T_hex_in_C": out(ABSORBER, "temperature_out"),
            "hex": out("heat_exchanger"),
            "gas_Nm3_s": out("separator", "gas_flow_rate"),
            "pumps": [
                {"name": "ESP", "flow_m3s": q_m3s, "dp_pa": esp_dp, "power_w": q_m3s * esp_dp / self.pump_eff},
                {"name": "injector_pump", "flow_m3s": q_m3s, "dp_pa": inj_dp, "power_w": q_m3s * inj_dp / self.pump_eff},
            ],
        }

    # --- absorption chiller (hot end) -----------------------------------------
    def absorber(self, q_m3h: float, t_in: float, cooling_w: float) -> dict:
        """Drive heat from the hot brine: inlet >= min_drive_inlet, outlet >= min_drive_outlet."""
        cop = self.absorption["cop_th"]
        if cooling_w <= 0 or t_in < self.absorption["min_drive_inlet_C"]:
            return {"cool_W": 0.0, "drive_W": 0.0, "drop_K": 0.0}
        m_cp = self.rho * q_m3h / 3600 * self.cp
        drive_max = m_cp * max(0.0, t_in - self.absorption["min_drive_outlet_C"])
        cool = min(cooling_w, cop * drive_max)
        return {"cool_W": cool, "drive_W": cool / cop, "drop_K": cool / cop / m_cp}

    # --- heat pump ----------------------------------------------------------
    def lorenz_cop(self, th_in, th_out, ts_in, ts_out) -> float:
        """HeatpumpBasic's Lorenz COP, eta * Th / (Th - Ts) with log-mean temperatures in K, capped."""
        k = 273.15
        th = (th_out - th_in) / math.log((th_out + k) / (th_in + k))
        ts = (ts_in - ts_out) / math.log((ts_in + k) / (ts_out + k))
        cop = math.inf if th <= ts else self.hp["eta_lorenz"] * th / (th - ts)
        return cop if self.hp.get("cop_cap") is None else min(cop, self.hp["cop_cap"])

    def heat_pump_point(self, fraction, t_sink_in, sink_m3s, t_src_in, src_m3s) -> dict:
        """Sink share ``fraction`` lifted to 100 C; solve the source outlet from
        COP = Qh / (Qh - Qs) (HeatpumpBasic's two equations). The residual is
        monotonic in Ts_out, so the bracketed root is unique."""
        m_src = self.rho * src_m3s
        qh = self.cp_s * self.rho_s * fraction * sink_m3s * (self.t_supply - t_sink_in)

        def residual(ts_out):
            qs = m_src * self.cp * (t_src_in - ts_out)
            return qs - qh * (1 - 1 / self.lorenz_cop(t_sink_in, self.t_supply, t_src_in, ts_out))

        dt_max = qh / (m_src * self.cp)  # source cooling if Qs = Qh, i.e. infinite COP
        if dt_max < 1e-6:  # negligible duty
            cop = self.lorenz_cop(t_sink_in, self.t_supply, t_src_in, t_src_in - 1e-6)
            return {"COP": cop, "Ts_out": t_src_in - dt_max, "Thermal_production": qh, "electrical_consumption": qh / cop}
        ts_out = brentq(residual, t_src_in - dt_max, t_src_in - 1e-9, xtol=1e-9)
        cop = self.lorenz_cop(t_sink_in, self.t_supply, t_src_in, ts_out)
        return {"COP": cop, "Ts_out": ts_out, "Thermal_production": qh, "electrical_consumption": qh / cop}

    def heat_pump(self, t_sink_in, sink_m3s, t_src_in, src_m3s, t_src_min, max_fraction=1.0):
        """Largest share (<= max_fraction) of the district flow the heat pump can lift to
        100 C without cooling the brine below ``t_src_min``. Returns (fraction, point)."""
        point = self.heat_pump_point(max_fraction, t_sink_in, sink_m3s, t_src_in, src_m3s)
        if point["Ts_out"] >= t_src_min:
            return max_fraction, point
        if self.heat_pump_point(1e-9, t_sink_in, sink_m3s, t_src_in, src_m3s)["Ts_out"] < t_src_min:
            return 0.0, self.heat_pump_point(0.0, t_sink_in, sink_m3s, t_src_in, src_m3s)  # no usable source heat
        fraction = brentq(
            lambda f: self.heat_pump_point(f, t_sink_in, sink_m3s, t_src_in, src_m3s)["Ts_out"] - t_src_min,
            1e-9, max_fraction, xtol=1e-9,
        )
        return fraction, self.heat_pump_point(fraction, t_sink_in, sink_m3s, t_src_in, src_m3s)

    def heat_pump_basic_cop(self, fraction, t_sink_in, sink_m3s, t_src_in, src_m3s):
        """Cross-check: GEMINI HeatpumpBasic (Nelder-Mead, uncapped) at the same operating point."""
        model = HeatpumpBasic()
        model.update_parameters({
            "mode": self.hp["mode"], "eta_lorenz": self.hp["eta_lorenz"], "COP_0": self.hp["COP_0"],
            "Cp_h": self.cp_s, "Cp_s": self.cp, "rho_h": self.rho_s, "rho_s": self.rho,
            "Th_out_target": self.t_supply, "Ts_in_minimum": -50.0,
        })
        model.calculate_output({"Th_in": t_sink_in, "Ts_in": t_src_in, "hot_flow_rate": fraction * sink_m3s, "source_flow_rate": src_m3s})
        return float(dict(model.get_output())["COP"])

    # --- CHP ----------------------------------------------------------------
    def chp(self, gas_nm3_s: float, secondary_m3s: float, t_in: float) -> dict:
        """GEMINI CHP model on ``gas_nm3_s`` of produced gas."""
        model = CHP()
        model.update_parameters(self.chp_params)
        model.calculate_output({"temperature_in": t_in, "water_flow_rate": secondary_m3s, "gas_flow_rate": gas_nm3_s * self.gas_density})
        return model.get_output()

    # --- downstream of the HEX ------------------------------------------------
    def downstream(self, q_m3h: float, t_wh: float, hex_out: dict, secondary_m3s: float, gas_nm3_s: float) -> dict:
        """Heat pump, CHP top-up and boiler for one doublet (setpoint energy balance)."""
        m_s = self.rho_s * secondary_m3s
        t_hex_s_out, t_brine = hex_out["secondary_temperature_out"], hex_out["primary_temperature_out"]
        hex_w, hex_bypass = hex_out["heat_duty"], False
        t_src_min = t_wh - self.limits["maximum_brine_delta_T_C"] + self.drop_after_hex
        # Hot brine (deep wells): a primary-side bypass limits the HEX duty so the district water
        # does not exceed 100 C and the brine is not cooled below the 40 K cap.
        m_cp_b = self.rho * q_m3h / 3600 * self.cp
        t_hex_p_in = t_brine + hex_w / m_cp_b
        hex_w_max = min(m_s * self.cp_s * (self.t_supply - self.t_return), m_cp_b * (t_hex_p_in - t_src_min))
        if hex_w > hex_w_max:
            hex_w, hex_bypass = hex_w_max, True
            t_hex_s_out = self.t_return + hex_w / (m_s * self.cp_s)
            t_brine = t_hex_p_in - hex_w / m_cp_b
        lift_w = max(0.0, m_s * self.cp_s * (self.t_supply - t_hex_s_out))
        if self.gas_mode == "reinject_all":  # no combustion: no CHP heat or electricity, nothing flared
            fuel_w, chp_full = 0.0, {"power_th": 0.0, "power_el": 0.0}
        else:
            fuel_w = gas_nm3_s * self.produced_gas_lhv_j_nm3
            chp_full = self.chp(gas_nm3_s, secondary_m3s, t_hex_s_out)

        # Heat pump covers only the lift that CHP heat cannot (so produced gas is not flared).
        hp = {"Q_W": 0.0, "W_W": 0.0, "COP": None, "sink_fraction": 0.0, "inputs": None, "capped": False}
        hp_target_w = max(0.0, lift_w - chp_full["power_th"])
        if hp_target_w > 0 and t_brine > t_src_min + HP_MIN_SOURCE_DT_K:
            inputs = (t_hex_s_out, secondary_m3s, t_brine, q_m3h / 3600)
            fraction, y = self.heat_pump(*inputs, t_src_min, max_fraction=hp_target_w / lift_w)
            cap = self.hp.get("cop_cap")
            hp = {"Q_W": y["Thermal_production"], "W_W": y["electrical_consumption"], "COP": y["COP"],
                  "sink_fraction": fraction, "inputs": inputs, "capped": cap is not None and y["COP"] >= cap - 1e-9}
            t_brine = y["Ts_out"]

        top_up_w = lift_w - hp["Q_W"]
        chp_share = min(1.0, top_up_w / chp_full["power_th"]) if chp_full["power_th"] > 0 else 0.0
        chp_heat = chp_share * chp_full["power_th"]
        remaining_w = top_up_w - chp_heat
        produced_left_w = fuel_w * (1 - chp_share)
        boiler_produced_fuel = min(produced_left_w, remaining_w / self.boiler_eff)
        external_fuel = (remaining_w - boiler_produced_fuel * self.boiler_eff) / self.boiler_eff
        return {
            "hex_W": hex_w, "hex_bypass": hex_bypass, "hp": hp, "T_after_hex_C": t_hex_s_out,
            "T_after_hp_C": t_hex_s_out + hp["Q_W"] / (m_s * self.cp_s),
            "chp_heat_W": chp_heat, "chp_el_W": chp_share * chp_full["power_el"], "chp_fuel_W": chp_share * fuel_w,
            "boiler_produced_fuel_W": boiler_produced_fuel, "boiler_external_fuel_W": external_fuel,
            "boiler_heat_W": (boiler_produced_fuel + external_fuel) * self.boiler_eff,
            "produced_fuel_W": fuel_w, "flared_fuel_W": produced_left_w - boiler_produced_fuel,
            "T_supply_C": t_hex_s_out + (hp["Q_W"] + chp_heat + (boiler_produced_fuel + external_fuel) * self.boiler_eff) / (m_s * self.cp_s),
            "T_injection_C": t_brine - self.drop_after_hex,
        }

    def evaluate(self, q_m3h: float, n_active: int, heating_w: float, cooling_w: float) -> dict:
        """Dispatch surrogate for one doublet: same GEMINI HEX/CHP models, no hydraulics."""
        secondary = self._secondary_m3s(heating_w) / n_active
        t_wh = self.wellhead_temperature(q_m3h)
        absorber = self.absorber(q_m3h, t_wh - self.drop_to_absorber, cooling_w / n_active)
        hex_out = self.hex_model(q_m3h, t_wh - self.drop_to_absorber - absorber["drop_K"], secondary)
        down = self.downstream(q_m3h, t_wh, hex_out, secondary, self.glr * q_m3h / 3600)
        return {"secondary_m3s": secondary, "absorber": absorber, "hex": hex_out, "down": down}

    def meets_need(self, q_m3h: float, n_active: int, heating_w: float, cooling_w: float) -> bool:
        e = self.evaluate(q_m3h, n_active, heating_w, cooling_w)
        tol_w = self.settings["dispatch"]["heating_tolerance_K"] * self.rho_s * e["secondary_m3s"] * self.cp_s
        return e["down"]["boiler_heat_W"] <= tol_w and e["absorber"]["cool_W"] >= cooling_w / n_active - 1.0

    def dispatch(self, available: list[int], heating_w: float, cooling_w: float) -> tuple[int, float, bool]:
        """(n_active, flow, geothermal_meets_need): fewest doublets, then lowest grid flow."""
        grid = self.flow_grid
        for n in range(1, len(available) + 1):
            if not self.meets_need(grid[-1], n, heating_w, cooling_w):
                continue
            lo, hi = 0, len(grid) - 1  # grid[hi] meets the need
            while lo < hi:
                mid = (lo + hi) // 2
                if self.meets_need(grid[mid], n, heating_w, cooling_w):
                    hi = mid
                else:
                    lo = mid + 1
            return n, grid[hi], True
        return len(available), grid[-1], False

    def _secondary_m3s(self, heating_w: float) -> float:
        return heating_w / (self.cp_s * (self.t_supply - self.t_return)) / self.rho_s

    # --- one day ------------------------------------------------------------
    def simulate_day(self, day: date, heating_w: float, cooling_w: float, in_maintenance: set[int]) -> dict:
        n_installed = self.candidate["n_doublets"]
        available = [i for i in range(n_installed) if i not in in_maintenance]
        if not available:
            return self.backup_day(day, heating_w, cooling_w, in_maintenance)
        n_active, q, geo_ok = self.dispatch(available, heating_w, cooling_w)
        active = available[:n_active]

        plan = self.evaluate(q, n_active, heating_w, cooling_w)
        secondary, absorber = plan["secondary_m3s"], plan["absorber"]
        chain = self.run_gemini_chain(q, secondary, absorber["drop_K"])
        s = self.downstream(q, chain["T_wellhead_C"], chain["hex"], secondary, chain["gas_Nm3_s"])
        hp_basic_cop = None
        if s["hp"]["inputs"] is not None and not s["hp"]["capped"]:
            hp_basic_cop = self.heat_pump_basic_cop(s["hp"]["sink_fraction"], *s["hp"]["inputs"])

        n = n_active
        cool_abs = n * absorber["cool_W"]
        cool_el = max(0.0, cooling_w - cool_abs)
        el_esp, el_inj = n * chain["pumps"][0]["power_w"], n * chain["pumps"][1]["power_w"]
        el_hp, el_chiller = n * s["hp"]["W_W"], cool_el / self.settings["electric_chiller_cop"]
        el_gas = n * chain["gas_Nm3_s"] * self.gas_handling_kwh_per_nm3 * 3.6e6  # Nm3/s * kWh/Nm3 * J/kWh = W
        el_load = el_esp + el_inj + el_hp + el_chiller + el_gas
        el_chp = n * s["chp_el_W"]
        grid_import, grid_export = max(0.0, el_load - el_chp), max(0.0, el_chp - el_load)
        produced_fuel, external_fuel = n * s["produced_fuel_W"], n * s["boiler_external_fuel_W"]
        delivered_heat = n * (s["hex_W"] + s["hp"]["Q_W"] + s["chp_heat_W"] + s["boiler_heat_W"])

        doublets = []
        for i in range(n_installed):
            on = i in active
            doublets.append({
                "name": f"doublet_{i + 1}", "active": on,
                "production_m3h": chain["production_m3h"] if on else 0.0,
                "injection_m3h": chain["injection_m3h"] if on else 0.0,
                "T_production_C": chain["T_wellhead_C"], "T_injection_C": s["T_injection_C"],
                "pumps": chain["pumps"] if on else [],
            })
        case = {"n_doublets": n_installed, "doublets": doublets, "heating_supply_C": s["T_supply_C"],
                "cooling_supply_C": self.settings["cooling_supply_return_C"][0]}
        report = check_constraints(case, self.limits)
        gj_day = 86400 / 1e9  # W over a day -> GJ
        return {
            "date": day.isoformat(),
            "heating_demand_MW": heating_w / 1e6, "cooling_demand_MW": cooling_w / 1e6,
            "maintenance": ";".join(f"doublet_{i + 1}" for i in sorted(in_maintenance)),
            "n_active": n, "active_doublets": ";".join(f"doublet_{i + 1}" for i in active),
            "flow_per_doublet_m3h": chain["production_m3h"], "geothermal_meets_need": geo_ok,
            "esp_freq_hz": chain["controls"]["esp_freq_hz"], "wellhead_pressure_bar": chain["controls"]["wellhead_pressure_bar"],
            "injector_wellhead_bar": chain["injector_wellhead_bar"],
            "T_wellhead_C": chain["T_wellhead_C"], "T_absorber_in_C": chain["T_absorber_in_C"], "T_hex_in_C": chain["T_hex_in_C"],
            "T_injection_C": s["T_injection_C"], "brine_dT_K": chain["T_wellhead_C"] - s["T_injection_C"],
            "heat_hex_MW": n * s["hex_W"] / 1e6, "heat_hp_MW": n * s["hp"]["Q_W"] / 1e6, "heat_chp_MW": n * s["chp_heat_W"] / 1e6,
            "heat_boiler_produced_gas_MW": n * s["boiler_produced_fuel_W"] * self.boiler_eff / 1e6,
            "heat_boiler_external_gas_MW": external_fuel * self.boiler_eff / 1e6,
            "heat_delivered_MW": delivered_heat / 1e6, "heat_unmet_MW": max(0.0, heating_w - delivered_heat) / 1e6,
            "T_after_hex_C": s["T_after_hex_C"], "T_after_hp_C": s["T_after_hp_C"], "T_supply_C": s["T_supply_C"],
            "hp_COP": s["hp"]["COP"], "hp_COP_capped": s["hp"]["capped"], "hp_sink_fraction": s["hp"]["sink_fraction"],
            "hp_COP_heatpumpbasic": hp_basic_cop,
            "cool_absorption_MW": cool_abs / 1e6, "cool_electric_MW": cool_el / 1e6,
            "cool_delivered_MW": (cool_abs + cool_el) / 1e6, "cool_unmet_MW": max(0.0, cooling_w - cool_abs - cool_el) / 1e6,
            "absorber_drive_MW": n * absorber["drive_W"] / 1e6, "absorber_brine_drop_K": absorber["drop_K"],
            "el_esp_MW": el_esp / 1e6, "el_injector_MW": el_inj / 1e6, "el_hp_MW": el_hp / 1e6, "el_chiller_MW": el_chiller / 1e6,
            "el_gas_handling_MW": el_gas / 1e6, "el_load_MW": el_load / 1e6, "el_chp_MW": el_chp / 1e6,
            "el_grid_import_MW": grid_import / 1e6, "el_grid_export_MW": grid_export / 1e6,
            "produced_gas_Nm3_day": n * chain["gas_Nm3_s"] * 86400,
            "produced_gas_fuel_MW": produced_fuel / 1e6, "produced_gas_chp_MW": n * s["chp_fuel_W"] / 1e6,
            "produced_gas_boiler_MW": n * s["boiler_produced_fuel_W"] / 1e6, "produced_gas_flared_MW": n * s["flared_fuel_W"] / 1e6,
            "external_gas_fuel_MW": external_fuel / 1e6,
            "external_gas_Nm3_day": external_fuel * 86400 / (self.settings["external_gas"]["lhv_MJ_per_Nm3"] * 1e6),
            "emission_produced_gas_t": produced_fuel * gj_day * self.produced_gas_ef / 1000,
            "emission_external_gas_t": external_fuel * gj_day * self.settings["external_gas"]["emission_factor_kg_per_GJ"] / 1000,
            "emission_electricity_t": grid_import * 24 / 1000 * self.el_factor / 1000,
            "hex_gemini_vs_model_W": chain["hex"]["heat_duty"] - plan["hex"]["heat_duty"], "hex_bypass": s["hex_bypass"],
            "constraints_pass": report["feasible"],
            "constraint_failures": ";".join(f"{r['check']}@{r['scope']}" for r in report["results"] if r["status"] != PASS),
        }

    def backup_day(self, day: date, heating_w: float, cooling_w: float, in_maintenance: set[int]) -> dict:
        """No doublet available: external-gas boiler and electric chiller carry the whole day."""
        n_installed = self.candidate["n_doublets"]
        external_fuel = heating_w / self.boiler_eff
        el_chiller = cooling_w / self.settings["electric_chiller_cop"]
        case = {"n_doublets": n_installed, "heating_supply_C": self.t_supply, "cooling_supply_C": self.settings["cooling_supply_return_C"][0],
                "doublets": [{"name": f"doublet_{i + 1}", "active": False, "production_m3h": 0.0, "injection_m3h": 0.0,
                              "T_production_C": None, "T_injection_C": None, "pumps": []} for i in range(n_installed)]}
        report = check_constraints(case, self.limits)
        gj_day = 86400 / 1e9
        zero = 0.0
        return {
            "date": day.isoformat(),
            "heating_demand_MW": heating_w / 1e6, "cooling_demand_MW": cooling_w / 1e6,
            "maintenance": ";".join(f"doublet_{i + 1}" for i in sorted(in_maintenance)),
            "n_active": 0, "active_doublets": "", "flow_per_doublet_m3h": zero, "geothermal_meets_need": False,
            "esp_freq_hz": None, "wellhead_pressure_bar": None, "injector_wellhead_bar": None,
            "T_wellhead_C": None, "T_absorber_in_C": None, "T_hex_in_C": None, "T_injection_C": None, "brine_dT_K": None,
            "heat_hex_MW": zero, "heat_hp_MW": zero, "heat_chp_MW": zero, "heat_boiler_produced_gas_MW": zero,
            "heat_boiler_external_gas_MW": heating_w / 1e6, "heat_delivered_MW": heating_w / 1e6, "heat_unmet_MW": zero,
            "T_after_hex_C": None, "T_after_hp_C": None, "T_supply_C": self.t_supply,
            "hp_COP": None, "hp_COP_capped": False, "hp_sink_fraction": zero, "hp_COP_heatpumpbasic": None,
            "cool_absorption_MW": zero, "cool_electric_MW": cooling_w / 1e6, "cool_delivered_MW": cooling_w / 1e6, "cool_unmet_MW": zero,
            "absorber_drive_MW": zero, "absorber_brine_drop_K": zero,
            "el_esp_MW": zero, "el_injector_MW": zero, "el_hp_MW": zero, "el_chiller_MW": el_chiller / 1e6,
            "el_gas_handling_MW": zero, "el_load_MW": el_chiller / 1e6, "el_chp_MW": zero, "el_grid_import_MW": el_chiller / 1e6, "el_grid_export_MW": zero,
            "produced_gas_Nm3_day": zero, "produced_gas_fuel_MW": zero, "produced_gas_chp_MW": zero,
            "produced_gas_boiler_MW": zero, "produced_gas_flared_MW": zero, "external_gas_fuel_MW": external_fuel / 1e6,
            "external_gas_Nm3_day": external_fuel * 86400 / (self.settings["external_gas"]["lhv_MJ_per_Nm3"] * 1e6),
            "emission_produced_gas_t": zero,
            "emission_external_gas_t": external_fuel * gj_day * self.settings["external_gas"]["emission_factor_kg_per_GJ"] / 1000,
            "emission_electricity_t": el_chiller * 24 / 1000 * self.el_factor / 1000,
            "hex_gemini_vs_model_W": zero, "hex_bypass": False,
            "constraints_pass": report["feasible"],
            "constraint_failures": ";".join(f"{r['check']}@{r['scope']}" for r in report["results"] if r["status"] != PASS),
        }

    # --- year ---------------------------------------------------------------
    def simulate_year(self, heating_mw: dict, cooling_mw: dict) -> dict:
        days = sorted(heating_mw)
        need = {d: heating_mw[d] + cooling_mw[d] / self.absorption["cop_th"] for d in days}
        d_cfg = self.settings["dispatch"]
        window = tuple(date.fromisoformat(s) for s in d_cfg["summer_window"])
        schedule = maintenance_schedule(need, self.candidate["n_doublets"], window, d_cfg["maintenance_days_per_doublet"])
        off = {d: {i for i, span in enumerate(schedule) if d in span} for d in days}
        rows = [self.simulate_day(d, heating_mw[d] * 1e6, cooling_mw[d] * 1e6, off[d]) for d in days]
        if any(r.keys() != rows[0].keys() for r in rows):
            raise RuntimeError("daily rows have inconsistent columns (backup_day vs simulate_day)")
        self.gas_dissolution = self.gas_dissolution_check(rows)
        return {"schedule": schedule, "rows": rows, "annual_checks": self.annual_checks(rows, schedule, days),
                "n_minus_1": self.n_minus_1(rows, heating_mw, cooling_mw, off), "gas_dissolution": self.gas_dissolution}

    def gas_dissolution_check(self, rows: list[dict]) -> dict | None:
        """Reinjected gas must dissolve in the injected brine (gas_solubility, DERIVED). Worst case on the
        injection path: lowest injector wellhead pressure of the year with the hottest injection temperature."""
        if self.gas_mode == "chp":
            return None
        on = [r for r in rows if r["n_active"]]
        cfg = self.settings["gas_handling"]
        kwh = (cfg["separation_compression_kWh_per_kg_CO2"] if self.gas_mode == "co2_reinject"
               else cfg["reinjection_compression_kWh_per_kg_gas"])
        return dissolution_check(
            self.gas_mode, self.challenge["fluid"]["gas_methane_mol_percent"] / 100, self.glr, self.rho,
            wellhead={"p_bar_g": min(r["injector_wellhead_bar"] for r in on), "t_c": max(r["T_injection_C"] for r in on)},
            reservoir={"p_bar_g": self.reservoir_pressure_bar, "t_c": self.reservoir_temperature_c},
            reservoir_depth_m=self.depth_m, compression_kwh_per_kg=kwh)

    def n_minus_1(self, rows: list[dict], heating_mw: dict, cooling_mw: dict, off: dict) -> list[dict]:
        """UNPLANNED outage of one more doublet on the peak heating and peak cooling days (ASSUMED
        resilience case): the backup duty the installed boiler / electric chiller must cover."""
        cases = []
        for label, demand in (("peak heating day", heating_mw), ("peak cooling day", cooling_mw)):
            day = max(demand, key=demand.get)
            normal = next(r for r in rows if r["date"] == day.isoformat())
            available = [i for i in range(self.candidate["n_doublets"]) if i not in off[day]]
            lost = available[0] if available else None
            r = self.simulate_day(day, heating_mw[day] * 1e6, cooling_mw[day] * 1e6, off[day] | ({lost} if lost is not None else set()))
            cases.append({
                "case": label, "date": day.isoformat(), "doublet_out": f"doublet_{lost + 1}" if lost is not None else None,
                "heating_demand_MW": r["heating_demand_MW"], "cooling_demand_MW": r["cooling_demand_MW"],
                "n_active_normal": normal["n_active"], "n_active_n_minus_1": r["n_active"],
                "boiler_MWth": r["heat_boiler_produced_gas_MW"] + r["heat_boiler_external_gas_MW"],
                "boiler_external_gas_MWth": r["heat_boiler_external_gas_MW"], "external_gas_fuel_MW": r["external_gas_fuel_MW"],
                "electric_chiller_MWcool": r["cool_electric_MW"],
                "boiler_MWth_normal": normal["heat_boiler_produced_gas_MW"] + normal["heat_boiler_external_gas_MW"],
                "electric_chiller_MWcool_normal": normal["cool_electric_MW"],
                "heat_unmet_MW": r["heat_unmet_MW"], "cool_unmet_MW": r["cool_unmet_MW"],
                "constraints_pass": r["constraints_pass"],
            })
        return cases

    def annual_checks(self, rows: list[dict], schedule: list[list[date]], days: list[date]) -> list[dict]:
        results = []
        required = self.settings["dispatch"]["maintenance_days_per_doublet"]
        op_limit = self.limits["geothermal_operating_days"]
        for i, span in enumerate(schedule):
            name = f"doublet_{i + 1}"
            op_days = sum(1 for r in rows if name in r["active_doublets"].split(";"))
            on_in_maintenance = [r["date"] for r in rows if name in r["active_doublets"].split(";") and name in r["maintenance"].split(";")]
            status = PASS if len(span) == required and op_days <= op_limit and not on_in_maintenance else "FAIL"
            results.append({"check": "330_day_rule", "scope": name, "status": status, "value": op_days,
                            "limit": f"<= {op_limit} operating days, {required} maintenance days",
                            "reason": f"maintenance {span[0]}..{span[-1]} ({len(span)} days), operated {op_days} days"})
        # Organizer clarification (Discord, 2026-11-01): the 330-day rule limits the geothermal SOURCE; the full
        # system must meet demand on all 365 days. Days with every doublet off are allowed (backup covers them)
        # and are reported as a design attribute (run_candidates.annual_summary), not checked here.
        unmet = [r["date"] for r in rows if r["heat_unmet_MW"] > UNMET_TOLERANCE_MW or r["cool_unmet_MW"] > UNMET_TOLERANCE_MW]
        results.append({"check": "demand_met_365", "scope": "plant", "status": PASS if not unmet else "FAIL", "value": len(unmet),
                        "limit": "0 days", "reason": f"{len(unmet)} day(s) with unmet heating or cooling (full system incl. backup)"
                                                     + (f" (first {unmet[0]})" if unmet else "")})
        bad_days = [r["date"] for r in rows if not r["constraints_pass"]]
        results.append({"check": "daily_constraints", "scope": "plant", "status": PASS if not bad_days else "FAIL", "value": len(bad_days),
                        "limit": "0 days", "reason": f"{len(bad_days)} day(s) failing a daily check" + (f" (first {bad_days[0]})" if bad_days else "")})
        if self.gas_dissolution:
            results.append(self.gas_dissolution["check"])
        return results + self.engineering
