"""GEMINI wrapper for the GeoBalance agent.

Builds a GEMINI simulator project from a few design variables, runs it,
and returns results plus warnings. Uses the official challenge inputs.

GEMINI source is expected at ../src (this folder lives in the repo root).
Override with the environment variable GEMINI_SRC.
"""
import copy
import json
import math
import os
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEMINI_SRC = Path(os.environ.get("GEMINI_SRC", HERE.parent / "src"))
sys.path.insert(0, str(GEMINI_SRC))
BASE_PROJECT = GEMINI_SRC.parent / "simulator_examples" / "projects" / "doublet_plant.json"

from gemini_simulator.project_loader import build_project  # noqa: E402
from gemini_model.heatpump.heatpump_basic import HeatpumpBasic  # noqa: E402

# ---- Official challenge inputs ----
SURFACE_T_C = 12.0
GRADIENT_C_KM = 30.0
P_RES_2500_BAR = 250.0           # given at 2,500 m TVD
BRINE_RHO = 1030.0
PERM_MD, THICKNESS_M, VISC_PA_S = 200.0, 100.0, 0.4e-3
GLR_NM3_M3 = 0.8
# Gas = 80% CH4 / 20% CO2 at normal conditions (0 degC, 1.01325 bar)
GAS_DENSITY_KG_NM3 = 0.8 * 0.7175 + 0.2 * 1.977          # 0.969
GAS_LHV_J_KG = 0.8 * 9.97 * 3.6e6 / GAS_DENSITY_KG_NM3     # ~29.6 MJ/kg
GAS_CO2_KG_GJ = (44.01 / 22.414) / (0.8 * 9.97 * 3.6e-3)   # ~68.4, incl. CO2 already in gas
GRID_CO2_KG_KWH = 0.3

# ---- Our assumptions (stated in the report) ----
WELLBORE_T_LOSS_C = 3.0          # reservoir -> wellhead
BUBBLE_POINT_BAR = 35.0          # estimate; keep ESP intake above this (free gas)
ESP_DEPTH_M = 650

# ESP + tubing options the sizing tool may choose from (stages, tubing ID m)
ESP_OPTIONS = [(10, 0.15), (20, 0.20), (30, 0.20)]
ESP_FREQS_HZ = [50, 60, 70, 80, 90, 100]


def reservoir_temperature_c(depth_m):
    return SURFACE_T_C + GRADIENT_C_KM * depth_m / 1000


def reservoir_pressure_bar(depth_m):
    """Given 250 bar at 2,500 m; hydrostatic for other depths (organizers' note)."""
    if abs(depth_m - 2500) < 1:
        return P_RES_2500_BAR
    return BRINE_RHO * 9.81 * depth_m / 1e5


def productivity_index_m3h_bar(skin=0.0, ln_re_rw=8.5):
    """Radial pseudo-steady-state PI from permeability, thickness, viscosity."""
    k = PERM_MD * 9.869e-16
    pi_m3s_pa = 2 * math.pi * k * THICKNESS_M / (VISC_PA_S * (ln_re_rw - 0.75 + skin))
    return pi_m3s_pa * 1e5 * 3600


def _build(depth_m, esp_stages, tubing_id_m, esp_freq_hz, pi):
    project = copy.deepcopy(json.loads(BASE_PROJECT.read_text(encoding="utf-8")))
    comps = project["components"]
    p_res = reservoir_pressure_bar(depth_m)
    for name in ("producer_well", "injector_well"):
        par = comps[name]["parameters"]
        par["reservoir_pressure_bar"] = p_res
        par["productivity_index_m3h_per_bar"] = pi
        for st in par["trajectory_table"]:
            st["ID"] = tubing_id_m
        par["trajectory_table"][-1].update(MD=depth_m, TVD=depth_m)
    prod = comps["producer_well"]["parameters"]
    prod["esp_depth_m"] = ESP_DEPTH_M
    prod["esp_freq_hz"] = esp_freq_hz
    prod["esp"]["no_stages"] = esp_stages
    prod["esp"]["electricity_emission_factor"] = GRID_CO2_KG_KWH
    comps["injector_well"]["parameters"]["injector_pump"]["efficiency_factor"] = 0.70
    # Official gas instead of the example defaults (0.5 / 0.7 / 50 MJ/kg / 56.6)
    comps["separator"]["parameters"].update(gas_water_ratio=GLR_NM3_M3, gas_density=GAS_DENSITY_KG_NM3)
    for name in ("boiler", "chp"):
        comps[name]["parameters"].update(caloric_value=GAS_LHV_J_KG, gas_emission_factor=GAS_CO2_KG_GJ)
    comps["gas_splitter"]["parameters"]["split_fractions"] = [0.0, 1.0]  # all gas to CHP (gas engine)
    for b in project["boundary_inputs"]:
        if b["component"] == "producer_well" and b["key"] == "wellhead_temperature":
            b["value"] = reservoir_temperature_c(depth_m) - WELLBORE_T_LOSS_C
    return project


@lru_cache(maxsize=512)
def run_doublet(depth_m=2500, esp_stages=20, tubing_id_m=0.20, esp_freq_hz=70, pi=None):
    """Run one GEMINI doublet. Returns results and warnings (MW, bar, degC, m3/h)."""
    pi = pi or productivity_index_m3h_bar()
    solver = build_project(_build(depth_m, esp_stages, tubing_id_m, esp_freq_hz, pi))
    solver.run()
    g = solver.get_output
    flow = float(g("producer_well", "flow_rate"))
    intake = g("producer_well", "esp_intake_pressure")
    intake = None if intake is None else float(intake)
    inj_whp = float(g("injector_well", "wellhead_pressure"))
    res = {
        "depth_m": depth_m, "esp_stages": esp_stages, "tubing_id_m": tubing_id_m,
        "esp_freq_hz": esp_freq_hz, "productivity_index_m3h_bar": round(pi, 2),
        "reservoir_temperature_c": reservoir_temperature_c(depth_m),
        "reservoir_pressure_bar": round(reservoir_pressure_bar(depth_m), 1),
        "flow_m3h": round(flow, 1),
        "brine_temp_at_plant_c": round(g("filter_a", "temperature_out"), 2),
        "esp_power_mw": round(float(g("producer_well", "esp_power_el")) / 1e6, 3),
        "esp_intake_bar": round(intake, 1) if intake is not None else None,
        "injector_pump_mw": round(g("injector_well", "power_el") / 1e6, 3),
        "injector_wellhead_bar": round(inj_whp, 2),
        "gemini_chp_power_el_mw": round(g("chp", "power_el") / 1e6, 3),
        "gemini_chp_co2_t_h": round(g("chp", "emission") * 3.6, 3),
        "warnings": [],
    }
    w = res["warnings"]
    if flow > 300:
        w.append(f"Flow {flow:.0f} m3/h above 300 m3/h cap")
    if flow < 50:
        w.append(f"Flow {flow:.0f} m3/h below 50 m3/h minimum")
    if intake is not None and intake <= 0.01:
        w.append("NON-PHYSICAL: ESP intake pressure is 0 bar (GEMINI floors it at 0, "
                 "nodal_solver.py:67). Result rejected.")
    elif intake is not None and intake < BUBBLE_POINT_BAR:
        w.append(f"ESP intake {intake:.0f} bar below bubble-point estimate "
                 f"{BUBBLE_POINT_BAR:.0f} bar: free gas / pump cavitation risk")
    if inj_whp <= 0.0011:
        w.append("Injector wellhead pressure at solver lower bound (0.001 bar): "
                 "injection pump reported as 0 MW, verify")
    return res


def size_doublet(depth_m=2500, target_flow_m3h=250):
    """Pick the lowest-power ESP/tubing/frequency that reaches the target flow
    without warnings about cavitation or non-physical results.
    If the target cannot be reached, return the highest acceptable flow."""
    ok = []
    for stages, tid in ESP_OPTIONS:
        for f in ESP_FREQS_HZ:
            r = run_doublet(depth_m, stages, tid, f)
            bad = [x for x in r["warnings"] if "NON-PHYSICAL" in x or "bubble" in x or "above 300" in x]
            if not bad:
                ok.append(r)
    if not ok:
        return {"error": "No acceptable pump configuration found", "warnings": ["sizing failed"]}
    reach = [r for r in ok if r["flow_m3h"] >= target_flow_m3h]
    if reach:
        best = min(reach, key=lambda r: r["esp_power_mw"])
        best = dict(best, sizing_note=f"Target {target_flow_m3h} m3/h reached")
    else:
        best = max(ok, key=lambda r: r["flow_m3h"])
        best = dict(best, sizing_note=(f"Target {target_flow_m3h} m3/h NOT reachable without "
                                       f"cavitation; max acceptable {best['flow_m3h']} m3/h"))
        best["warnings"] = best["warnings"] + [best["sizing_note"]]
    return best


def heat_pump_gemini(network_in_c, source_in_c, network_flow_m3h, source_flow_m3h,
                     supply_c=100.0, source_min_c=47.0, eta_carnot=0.5):
    """GEMINI HeatpumpBasic (Carnot mode). Called directly: it is not in the
    simulator registry. Returns COP, outlet temperatures and powers."""
    w = []
    if source_in_c >= network_in_c:
        w.append(f"Heat pump source {source_in_c:.0f} C is not colder than sink inlet "
                 f"{network_in_c:.0f} C: use a direct heat exchanger instead "
                 "(GEMINI heat pump model gives non-physical results here)")
    m = HeatpumpBasic()
    m.update_parameters({"mode": "carnot", "eta_carnot": eta_carnot, "eta_lorenz": 0.5, "COP_0": 4.0,
                         "Cp_h": 4181, "Cp_s": 4000, "rho_h": 1000, "rho_s": BRINE_RHO,
                         "Th_out_target": supply_c, "Ts_in_minimum": source_min_c})
    m.calculate_output({"Th_in": network_in_c, "Ts_in": source_in_c,
                        "hot_flow_rate": network_flow_m3h / 3600,
                        "source_flow_rate": source_flow_m3h / 3600}, None)
    o = m.get_output()
    o = {k: float(v) for k, v in o.items() if isinstance(v, (int, float))}
    out = {"cop": round(o["COP"], 2), "supply_out_c": round(o["Th_out"], 1),
           "source_out_c": round(o["Ts_out"], 1), "heat_mw": round(o["power_th"] / 1e6, 2),
           "electricity_mw": round(o["power_el"] / 1e6, 2), "warnings": w}
    if o["Th_out"] < supply_c - 0.5:
        w.append(f"Heat pump reaches only {o['Th_out']:.1f} C (target {supply_c} C): "
                 "source brine flow too small")
    if o["Th_out"] > supply_c + 5:
        w.append(f"NON-PHYSICAL heat pump result: supply {o['Th_out']:.0f} C above target")
    if not (1.5 < o["COP"] < 10.0):
        w.append(f"Non-physical heat pump COP {o['COP']:.2f}")
    return out


if __name__ == "__main__":
    print("PI:", round(productivity_index_m3h_bar(), 1), "m3/h/bar")
    print(run_doublet())
    print(size_doublet(2500, 250))
    print(size_doublet(3400, 250))
    print(heat_pump_gemini(82, 55, 517, 577))
    print(heat_pump_gemini(50, 87, 517, 437))
