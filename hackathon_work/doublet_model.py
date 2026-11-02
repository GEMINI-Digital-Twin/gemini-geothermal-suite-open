"""GEMINI hackathon: one-doublet challenge model built on gemini_simulator.

Shared by run_doublet_challenge.py (task 1-2) and the later daily driver.
``run_case`` loads projects/doublet_challenge.json, applies the design and
control variables (target brine flow, HEX UA, demand-based secondary flow),
runs one GEMINI time step and returns our own KPIs plus a constraint-checker
case. No src/ files are modified: the well brine PVT is overridden at
runtime (see ``install_brine_pvt``).
"""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "src"))  # same as PYTHONPATH=src

import gemini_simulator.well_flow as well_flow  # noqa: E402
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP  # noqa: E402
from gemini_model.pump.esp import ESP  # noqa: E402
from gemini_simulator.project_loader import build_project  # noqa: E402
from gemini_simulator.registry import create_component  # noqa: E402

PROJECT_PATH = ROOT / "projects" / "doublet_challenge.json"
CHALLENGE_PATH = ROOT / "inputs" / "challenge_inputs.json"

WELLBORE_U_W_M2K = 10.0  # same U that gemini_model DPDT hard-codes (well/pressure_drop.py)
JOULE_PER_KWH = 3.6e6
FLOW_TOLERANCE_M3H = 0.01


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


class ScaledESP(ESP):
    """GEMINI ESP curve stretched along the flow axis by ``flow_scale`` = s (ASSUMED pump sizing).

    head(Q) = H_ref(Q/s), power(Q) = s * P_ref(Q/s): the same efficiency curve
    shape at s times the flow. ``no_stages`` sets the head. s = 1 is the
    unchanged GEMINI model.
    """

    def head_function(self, pump_flow, freq):
        return super().head_function(pump_flow / self._flow_scale(), freq)

    def power_function(self, pump_flow, freq):
        return self._flow_scale() * super().power_function(pump_flow / self._flow_scale(), freq)

    def _flow_scale(self):
        return self.parameters.get("flow_scale", 1.0)


def install_scaled_esp():
    """Make gemini_simulator.well_flow build ScaledESP pumps (no src/ edits)."""
    well_flow.ESP = ScaledESP


def install_brine_pvt(override: dict) -> dict:
    """Make every well DPDT built by gemini_simulator.well_flow use the challenge brine.

    well_flow._build_dpdt instantiates ``PVTConstantSTP()`` from its own
    module namespace, so replacing that name is enough; src/ is untouched.
    """
    values = {k: v for k, v in override.items() if not k.startswith("_")}

    class ChallengeBrinePVT(PVTConstantSTP):
        def __init__(self):
            super().__init__()
            self.parameters.update(values)

    well_flow.PVTConstantSTP = ChallengeBrinePVT
    probe = well_flow._build_dpdt([{"angle": 90.0, "depth": 1.0, "diameter": 0.15}])
    for key, value in values.items():
        if probe.PVT.parameters[key] != value:
            raise RuntimeError(f"PVT override not applied for {key}")
    return {key: probe.PVT.parameters[key] for key in ("RHOL", "VISL", "CPL", "GMF")}


def boundary(project: dict, component: str, key: str) -> dict:
    for entry in project["boundary_inputs"]:
        if entry["component"] == component and entry["key"] == key:
            return entry
    raise KeyError(f"No boundary input {component}.{key}")


def derived_wellhead_temperature_c(flow_m3h: float, well_params: dict, challenge: dict, rho: float, cp: float) -> dict:
    """T_wh = T_res - U*A*(T_res - T_form_mean) / (m_dot*cp), A = sum(pi*ID*dMD)."""
    r = challenge["reservoir"]
    t_res = r["surface_temperature_C"] + r["gradient_C_per_km"] * r["midpoint_depth_m_TVD"] / 1000
    t_form_mean = (r["surface_temperature_C"] + t_res) / 2
    stations = well_params["trajectory_table"]
    area = sum(math.pi * b["ID"] * (b["MD"] - a["MD"]) for a, b in zip(stations, stations[1:]))
    loss_w = WELLBORE_U_W_M2K * area * (t_res - t_form_mean)
    m_dot = rho * flow_m3h / 3600
    return {
        "T_reservoir_C": t_res,
        "T_formation_mean_C": t_form_mean,
        "wellbore_area_m2": area,
        "wellbore_loss_W": loss_w,
        "T_wellhead_C": t_res - loss_w / (m_dot * cp),
    }


def district_secondary_flow_m3s(heating_demand_w: float, rho: float, cp: float, t_supply_c: float, t_return_c: float) -> float:
    """Secondary flow that carries the demand at the design supply/return temperatures."""
    return heating_demand_w / (cp * (t_supply_c - t_return_c)) / rho


def surface_pressure_drop_bar(project: dict, flow_m3s: float) -> float:
    """Pressure drop wellhead -> injector pump suction, from the GEMINI surface models.

    The separator/filter models are linear in pressure, so the drop only
    depends on flow; evaluating them from 0 bar gives it directly.
    """
    components = project["components"]
    drop = flow_m3s * components["heat_exchanger"]["parameters"]["flow_resistance"]
    for name in ("separator", "filter_a", "filter_b"):
        model = create_component(components[name]["type"])
        model.update_parameters(components[name]["parameters"])
        model.calculate_output({"pressure": 0.0, "temperature": 0.0, "flow_rate": flow_m3s})
        drop -= model.output["pressure_out"]
    return drop


def esp_zero_head_flow_m3h(esp_params: dict, freq_hz: float, max_m3h: float = 700.0) -> float | None:
    """First flow (1 m3/h steps) at which the ESP curve gives no head.

    gemini_model's ESP scales head by (f/60)^2 but evaluates the polynomial at
    the actual flow, so this flow is the same at every frequency.
    """
    esp = ScaledESP()
    esp.update_parameters(esp_params)
    for q in range(1, int(max_m3h) + 1):
        if esp.head_function(q / 3600, freq_hz) <= 0:
            return float(q)
    return None


def solve_producer_controls(project: dict, target_m3h: float, wellhead_temperature_c: float) -> dict:
    """Choose esp_freq_hz and wellhead pressure so the producer delivers ``target_m3h``.

    1. Wellhead pressure = max(nominal, surface-pressure floor at the target flow).
    2. Solve the ESP frequency within its range.
    3. If even the maximum frequency is too low, lower the wellhead pressure
       towards its floor; if the minimum frequency is too high, raise it (choke).
    4. Otherwise report the target as unreachable and run at the closest flow.
    """
    params = project["components"]["producer_well"]["parameters"]
    controls = project["_design_controls"]
    f_min, f_max = controls["esp_freq_hz_range"]
    p_surface_min = controls["min_surface_pressure_bar"]
    p_wh_max = controls["max_wellhead_pressure_bar"]
    p_nominal = boundary(project, "producer_well", "wellhead_pressure")["value"]

    def flow_at(freq_hz, p_wh_bar):
        try:
            return well_flow.solve_primary_flow_m3h(
                {**params, "esp_freq_hz": freq_hz},
                wellhead_pressure_bar=p_wh_bar,
                wellhead_temperature_c=wellhead_temperature_c,
                ambient_temperature_c=params.get("ambient_temperature_c", 20.0),
                flow_bracket_m3h=params.get("flow_bracket_m3h", (0.01, 700.0)),
            )
        except ValueError:  # no root in the flow bracket: the well does not flow
            return 0.0

    def p_floor(q_m3h):
        return p_surface_min + surface_pressure_drop_bar(project, q_m3h / 3600)

    p_wh = max(p_nominal, p_floor(target_m3h))
    q_at_fmin, q_at_fmax = flow_at(f_min, p_wh), flow_at(f_max, p_wh)
    result = {
        "target_m3h": target_m3h,
        "esp_freq_range_hz": [f_min, f_max],
        "wellhead_pressure_nominal_bar": p_nominal,
        "wellhead_pressure_floor_at_target_bar": p_floor(target_m3h),
        "wellhead_pressure_floor_bar": p_floor(target_m3h),
        "flow_range_wellhead_pressure_bar": p_wh,
        "flow_at_fmin_m3h": q_at_fmin,
        "flow_at_fmax_m3h": q_at_fmax,
        "esp_zero_head_flow_m3h": esp_zero_head_flow_m3h(params["esp"], f_max),
    }

    if q_at_fmin <= target_m3h <= q_at_fmax:
        freq = brentq(lambda f: flow_at(f, p_wh) - target_m3h, f_min, f_max, xtol=1e-6)
        result.update(mode="esp_frequency", reached=True, esp_freq_hz=freq, wellhead_pressure_bar=p_wh)
    elif target_m3h > q_at_fmax:
        floor = p_floor(target_m3h)
        if floor < p_wh and flow_at(f_max, floor) >= target_m3h:
            p = brentq(lambda p: flow_at(f_max, p) - target_m3h, floor, p_wh, xtol=1e-6)
            result.update(mode="wellhead_pressure_down", reached=True, esp_freq_hz=f_max, wellhead_pressure_bar=p)
        else:
            # Closest achievable: maximum frequency at the floor of the achieved flow.
            p, q = floor, flow_at(f_max, floor)
            for _ in range(3):
                p = max(p_floor(q), 0.0)
                q = flow_at(f_max, p)
            result.update(
                mode="unreachable_high", reached=False, esp_freq_hz=f_max, wellhead_pressure_bar=p, max_flow_m3h=q,
                wellhead_pressure_floor_bar=p,
                reason=(
                    f"{target_m3h:.1f} m3/h not reachable: {q:.1f} m3/h at {f_max} Hz with wellhead pressure at its "
                    f"{p:.2f} bar floor (ESP curve gives no head above "
                    f"{result['esp_zero_head_flow_m3h']} m3/h at any frequency)"
                ),
            )
    else:
        if flow_at(f_min, p_wh_max) <= target_m3h:
            p = brentq(lambda p: flow_at(f_min, p) - target_m3h, p_wh, p_wh_max, xtol=1e-6)
            result.update(mode="wellhead_pressure_up", reached=True, esp_freq_hz=f_min, wellhead_pressure_bar=p)
        else:
            q = flow_at(f_min, p_wh_max)
            result.update(
                mode="unreachable_low", reached=False, esp_freq_hz=f_min, wellhead_pressure_bar=p_wh_max, min_flow_m3h=q,
                reason=f"{target_m3h:.1f} m3/h not reachable: {q:.1f} m3/h even at {f_min} Hz and {p_wh_max} bar wellhead",
            )
    return result


def compute_kpis(solver, project: dict, rho: float, cp: float, pump_eff: float) -> dict:
    out = solver.get_output
    hex_params = project["components"]["heat_exchanger"]["parameters"]
    rho_s, cp_s = hex_params["fluid_density"], hex_params["specific_heat"]

    q_m3s = out("producer_well", "flow_rate_m3s")
    m_dot = rho * q_m3s
    t_wh = out("producer_well", "temperature_out")
    t_inj = out("filter_b", "temperature_out")
    t_hex_in, t_hex_out = out("filter_a", "temperature_out"), out("heat_exchanger", "primary_temperature_out")

    esp_dp_pa = (out("producer_well", "esp_discharge_pressure") - out("producer_well", "esp_intake_pressure")) * 1e5
    esp_power_w = q_m3s * esp_dp_pa / pump_eff
    inj_dp_pa = max(0.0, out("injector_well", "wellhead_pressure_pa") - out("filter_b", "pressure_out_pa"))
    inj_power_w = q_m3s * inj_dp_pa / pump_eff

    q_s_m3s = boundary(project, "secondary_splitter", "input")["value"]
    t_s_in = boundary(project, "heat_exchanger", "secondary_temperature_in")["value"]
    t_s_out = out("water_mixer", "temperature")
    district_heat_w = q_s_m3s * rho_s * cp_s * (t_s_out - t_s_in)

    boiler_th, chp_th, chp_el = out("boiler", "power_th"), out("chp", "power_th"), out("chp", "power_el")
    gas_kg_s = out("separator", "gas_mass_flow_rate")
    hex_duty_w = out("heat_exchanger", "heat_duty")

    el_factor = project["components"]["producer_well"]["parameters"]["esp"]["electricity_emission_factor"]
    grid_w = max(0.0, esp_power_w + inj_power_w - chp_el)
    gas_emission_kg_day = (out("boiler", "emission") + out("chp", "emission")) * 86400
    el_emission_kg_day = el_factor / JOULE_PER_KWH * grid_w * 86400

    return {
        "primary_flow_m3h": out("producer_well", "flow_rate"),
        "injection_flow_m3h": out("filter_b", "flow_rate_m3h"),
        "T_wellhead_C": t_wh,
        "T_hex_primary_in_C": t_hex_in,
        "T_hex_primary_out_C": t_hex_out,
        "T_injection_C": t_inj,
        "brine_dT_K": t_wh - t_inj,
        "brine_heat_extracted_W": m_dot * cp * (t_wh - t_inj),
        "hex_heat_duty_W": hex_duty_w,
        "surface_brine_losses_W": m_dot * cp * ((t_wh - t_inj) - (t_hex_in - t_hex_out)),
        "wellhead_pressure_bar": out("producer_well", "pressure_out"),
        "min_surface_pressure_bar": out("filter_b", "pressure_out"),
        "esp_freq_hz": project["components"]["producer_well"]["parameters"]["esp_freq_hz"],
        "esp_intake_bar": out("producer_well", "esp_intake_pressure"),
        "esp_discharge_bar": out("producer_well", "esp_discharge_pressure"),
        "esp_dp_pa": esp_dp_pa,
        "esp_power_W_at_pump_eff": esp_power_w,
        "esp_power_W_curve_reference": out("producer_well", "esp_power_el"),
        "esp_curve_efficiency": q_m3s * esp_dp_pa / out("producer_well", "esp_power_el"),
        "injector_wellhead_bar": out("injector_well", "wellhead_pressure"),
        "injector_inlet_bar": out("filter_b", "pressure_out"),
        "injector_pump_dp_pa": inj_dp_pa,
        "injector_pump_power_W_at_pump_eff": inj_power_w,
        "injector_pump_power_W_gemini": out("injector_well", "power_el"),
        "secondary_flow_m3h": q_s_m3s * 3600,
        "T_secondary_in_C": t_s_in,
        "T_hex_secondary_out_C": out("heat_exchanger", "secondary_temperature_out"),
        "T_boiler_out_C": out("boiler", "temperature_out"),
        "T_chp_out_C": out("chp", "temperature_out"),
        "T_supply_C": t_s_out,
        "district_heat_W": district_heat_w,
        "heat_balance_residual_W": district_heat_w - (hex_duty_w + boiler_th + chp_th),
        "gas_Nm3h": out("separator", "gas_flow_rate") * 3600,
        "gas_kg_s": gas_kg_s,
        "gas_fuel_power_W": gas_kg_s * project["components"]["boiler"]["parameters"]["caloric_value"],
        "boiler_heat_W": boiler_th,
        "chp_heat_W": chp_th,
        "chp_electricity_W": chp_el,
        "grid_electricity_W": grid_w,
        "emission_gas_kg_CO2_day": gas_emission_kg_day,
        "emission_electricity_kg_CO2_day": el_emission_kg_day,
        "emission_total_kg_CO2_day": gas_emission_kg_day + el_emission_kg_day,
    }


def checker_case(kpis: dict, n_doublets: int = 1, cooling_supply_c: float | None = None) -> dict:
    """Constraint-checker case for ``n_doublets`` identical doublets."""
    q_m3s = kpis["primary_flow_m3h"] / 3600
    doublets = [
        {
            "name": f"doublet_{i}",
            "active": True,
            "production_m3h": kpis["primary_flow_m3h"],
            "injection_m3h": kpis["injection_flow_m3h"],
            "T_production_C": kpis["T_wellhead_C"],
            "T_injection_C": kpis["T_injection_C"],
            "pumps": [
                {"name": "ESP", "flow_m3s": q_m3s, "dp_pa": kpis["esp_dp_pa"], "power_w": kpis["esp_power_W_at_pump_eff"]},
                {"name": "injector_pump", "flow_m3s": q_m3s, "dp_pa": kpis["injector_pump_dp_pa"], "power_w": kpis["injector_pump_power_W_at_pump_eff"]},
            ],
        }
        for i in range(1, n_doublets + 1)
    ]
    return {"n_doublets": n_doublets, "doublets": doublets, "heating_supply_C": kpis["T_supply_C"], "cooling_supply_C": cooling_supply_c}


def run_case(target_flow_m3h: float, hex_ua_w_k: float, heating_demand_w: float, n_doublets: int = 1,
             project_path: Path = PROJECT_PATH) -> dict:
    """Apply design/control variables, run one GEMINI time step, return KPIs and logs."""
    project = copy.deepcopy(load_json(project_path))
    challenge = load_json(CHALLENGE_PATH)
    pvt = install_brine_pvt(project["_brine_pvt_override"])
    install_scaled_esp()
    rho, cp = pvt["RHOL"], pvt["CPL"]
    pump_eff = challenge["constraints"]["pump_efficiency"]
    components = project["components"]
    producer_params = components["producer_well"]["parameters"]

    # Design variable: HEX UA.
    components["heat_exchanger"]["parameters"]["heat_transfer_coefficient"] = hex_ua_w_k

    # Secondary flow from the day's heating demand (per doublet) at supply/return design temperatures.
    hex_params = components["heat_exchanger"]["parameters"]
    t_supply = challenge["constraints"]["heating_supply_temperature_C"]
    t_return = boundary(project, "heat_exchanger", "secondary_temperature_in")["value"]
    demand_per_doublet_w = heating_demand_w / n_doublets
    q_s = district_secondary_flow_m3s(demand_per_doublet_w, hex_params["fluid_density"], hex_params["specific_heat"], t_supply, t_return)
    boundary(project, "secondary_splitter", "input")["value"] = q_s

    # Control variables: ESP frequency / wellhead pressure for the target flow.
    # Constant well PVT -> solved flow is independent of the wellhead temperature.
    t_wh_entry = boundary(project, "producer_well", "wellhead_temperature")
    t_wh_nominal = t_wh_entry["value"]
    controls = solve_producer_controls(project, target_flow_m3h, t_wh_nominal)
    producer_params["esp_freq_hz"] = controls["esp_freq_hz"]
    boundary(project, "producer_well", "wellhead_pressure")["value"] = controls["wellhead_pressure_bar"]

    solver = build_project(project)
    solver.run()
    flow_m3h = solver.get_output("producer_well", "flow_rate")
    wellhead = derived_wellhead_temperature_c(flow_m3h, producer_params, challenge, rho, cp)
    t_wh_entry["value"] = wellhead["T_wellhead_C"]
    solver = build_project(project)
    solver.run()
    wellhead.update(nominal_C=t_wh_nominal, used_C=t_wh_entry["value"])
    controls["achieved_m3h"] = solver.get_output("producer_well", "flow_rate")
    controls["reached"] = controls["reached"] and abs(controls["achieved_m3h"] - target_flow_m3h) <= FLOW_TOLERANCE_M3H

    kpis = compute_kpis(solver, project, rho, cp, pump_eff)
    return {
        "design": {
            "target_flow_m3h": target_flow_m3h,
            "hex_ua_W_K": hex_ua_w_k,
            "n_doublets": n_doublets,
            "heating_demand_W": heating_demand_w,
            "heating_demand_per_doublet_W": demand_per_doublet_w,
            "district_supply_return_C": [t_supply, t_return],
        },
        "controls": controls,
        "pump_efficiency": pump_eff,
        "well_pvt_effective": pvt,
        "wellhead_temperature": wellhead,
        "effective_project": project,
        "solver": solver,
        "kpis": kpis,
    }
