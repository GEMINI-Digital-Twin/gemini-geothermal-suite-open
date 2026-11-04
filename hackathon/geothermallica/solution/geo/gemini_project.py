"""One of our designs written as a native GEMINI simulator project and re-run by GEMINI's own solver.

Format: GEMINI's simulator_examples/projects/doublet_plant.json (producer with ESP, separator, filters, exchanger,
boiler on the separator gas, injector). Parameter sources are in the inline comments. replay() returns, for a few days
of 2027, GEMINI's pressures, duty and boiler heat next to ours, the project file path and a basis string.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

import geo.gemini_contrib  # noqa: F401  (GEMINI development tree first on sys.path)
from geo import gas
from geo.common import DEPTH_M, DT_BRINE_MAX_K, RHO, T_SUPPLY_HEAT_C
from geo.cost import BOILER_EFF
from geo.plant import CP, doublet_at
from geo.well import CELL_M, ESP_DEPTH_M, ROUGHNESS_M, TUBING_ID_M, Injector, Producer, reservoir_pressure
from geo.year import heating_year
from gemini_simulator.project_loader import build_project

P_WELLHEAD_BAR = 10.0        # producer wellhead pressure the ESP holds, bar; the floor used by geo.well.Producer
SEPARATOR = {"flow_resistance": 3.6, "temperature_drop": 0.0}   # resistance as in GEMINI's example; no temperature loss, assumed
FILTER = {"base_resistance": 3.6, "fouling_coeff_a": 18.0, "fouling_coeff_b": 0.036, "temperature_drop": 0.0}   # GEMINI's example
M_GAS = gas.Y_CH4 * gas.M_CH4 + gas.Y_CO2 * gas.M_CO2    # molar mass of the 80/20 gas, kg/mol
GAS_DENSITY = M_GAS / gas.V_M                            # gas density at normal conditions, kg/Nm3
GAS_LHV_J_KG = gas.Y_CH4 * gas.LHV_CH4 * 1e3 / M_GAS     # lower heating value of the gas, J/kg (only the methane burns)
GAS_CO2_KG_GJ = gas.M_CO2 / (gas.Y_CH4 * gas.LHV_CH4 * 1e-6)   # CO2 per GJ burned: one CO2 per mole of gas, kg/GJ
RUNS = Path(__file__).resolve().parents[1] / "ai" / "runs"
COMPARED = ("q_m3h", "p_esp_intake_bar", "esp_head_bar", "p_injection_wellhead_bar", "T_brine_out_C", "MW_exchanger",
            "MW_boiler_gas")


def _stations(depth_m):
    """Trajectory table of a vertical well, one station per CELL_M, the tubing diameter of geo.well."""
    md = np.arange(0.0, depth_m + 1e-9, CELL_M)
    return [{"MD": float(z), "TVD": float(z), "ID": TUBING_ID_M} for z in md]


def _well_params(w, depth_m, ii):
    """Shared producer and injector parameters in the units GEMINI's well components expect."""
    return {"reservoir_pressure_bar": reservoir_pressure(depth_m), "trajectory_table": _stations(depth_m),
            "roughness_m": ROUGHNESS_M, "ambient_temperature_c": w.t_ambient_c,
            "productivity_index_m3h_per_bar": ii}


def project_dict(w, t_return_c, t_wellhead_c, esp_freq_hz, secondary_m3s, ua_w_per_k, ii_m3h_bar):
    """Native GEMINI project dict of one doublet of our design around the producer w at these day values."""
    prod = {**_well_params(w, w.depth_m, w.pi), "esp_depth_m": w.esp_depth_m, "esp_freq_hz": esp_freq_hz,
            "esp": {**w.pump.parameters, "electricity_emission_factor": 0.3}}
    comps = {"producer_well": {"type": "producer_well", "parameters": prod},
             "separator": {"type": "separator",
                           "parameters": {**SEPARATOR, "gas_water_ratio": gas.GLR, "gas_density": GAS_DENSITY}},
             "filter_a": {"type": "filter", "parameters": FILTER},
             "heat_exchanger": {"type": "heat_exchanger", "parameters": {"flow_resistance": 0.0, "flow_configuration": "counter",
                                                                         "heat_transfer_coefficient": ua_w_per_k,
                                                                         "fluid_density": RHO, "specific_heat": CP * 1e3}},
             "filter_b": {"type": "filter", "parameters": FILTER},
             "boiler": {"type": "boiler", "parameters": {"caloric_value": GAS_LHV_J_KG, "efficiency_factor": BOILER_EFF,
                                                         "gas_emission_factor": GAS_CO2_KG_GJ}},
             "injector_well": {"type": "injector_well", "parameters": {**_well_params(w, w.depth_m, ii_m3h_bar),
                                                                       "injector_pump": {"efficiency_factor": 0.7}}}}
    boundary = [{"component": "producer_well", "key": "wellhead_pressure", "value": P_WELLHEAD_BAR},
                {"component": "producer_well", "key": "wellhead_temperature", "value": t_wellhead_c},
                {"component": "heat_exchanger", "key": "secondary_temperature_in", "value": t_return_c},
                {"component": "heat_exchanger", "key": "secondary_flow_rate", "value": secondary_m3s}]

    def link(a, b, ports):
        return {"predecessor": a, "successor": b, "ports": ports}
    conn = [link("producer_well", "separator", [["flow_rate_m3s", "flow_rate"], ["pressure_out", "pressure"],
                                                ["temperature_out", "temperature"]]),
            link("separator", "filter_a", [["pressure_out", "pressure"], ["temperature_out", "temperature"],
                                           ["flow_rate", "flow_rate"]]),
            link("filter_a", "heat_exchanger", [["pressure_out", "pressure_in"], ["temperature_out", "primary_temperature_in"],
                                                ["flow_rate", "primary_flow_rate"]]),
            link("heat_exchanger", "filter_b", [["pressure_out", "pressure"], ["primary_temperature_out", "temperature"],
                                                ["primary_flow_rate", "flow_rate"]]),
            link("heat_exchanger", "boiler", [["secondary_temperature_out", "temperature_in"],
                                              ["secondary_flow_rate", "water_flow_rate"]]),
            link("separator", "boiler", [["gas_mass_flow_rate", "gas_flow_rate"]]),
            link("filter_b", "injector_well", [["flow_rate_m3h", "flow_rate"], ["temperature_out", "wellhead_temperature"],
                                               ["pressure_out_pa", "pressure_in"]])]
    return {"_description": "Generated from the Geothermallica design; one doublet; units as in GEMINI's doublet_plant.json",
            "components": comps, "boundary_inputs": boundary, "connections": conn}


def write_project(path, project):
    """Write the project dict as JSON and return the path."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(project, indent=1))
    return str(path)


def _solve(project):
    """Build the project with GEMINI's loader, run its solver once and return the solver."""
    s = build_project(json.loads(json.dumps(project)))   # a copy: the loader hands the dicts to the components
    s.run()
    return s


def _freq_for_flow(project, q_m3h, f_lo=30.0, f_hi=60.0):
    """ESP frequency at which GEMINI's own nodal solve gives q_m3h (bisection); None if 60 Hz is not enough."""
    def flow(f):
        project["components"]["producer_well"]["parameters"]["esp_freq_hz"] = f
        return _solve(project).get_output("producer_well", "flow_rate")
    if flow(f_hi) < q_m3h:
        return None
    for _ in range(30):
        f = 0.5 * (f_lo + f_hi)
        f_lo, f_hi = (f, f_hi) if flow(f) < q_m3h else (f_lo, f)
    return f_hi


def _ua(t_hot_in, t_cold_in, c_hot, c_cold, duty_w):
    """Heat-transfer coefficient UA (W/K) of a counter-flow exchanger with this duty, inverted NTU-effectiveness method."""
    c_min, c_max = min(c_hot, c_cold), max(c_hot, c_cold)
    eff, cr = duty_w / (c_min * (t_hot_in - t_cold_in)), c_min / c_max
    ntu = eff / (1 - eff) if cr > 0.999 else np.log((1 - eff * cr) / (1 - eff)) / (1 - cr)
    return float(ntu * c_min)


def _days(n, t_return_c, depth_m, esp_depth_m, k=3):
    """Up to k representative days with every doublet running: the coldest, the median demand and the mildest."""
    d = heating_year(n, t_return_c, depth_m=depth_m, esp_depth_m=esp_depth_m)
    d = d[(d.doublets_on == n) & (d.q_m3h > 0)].sort_values("demand")
    picks = [d.index[-1], d.index[len(d) // 2], d.index[0]][:k]
    return d.loc[picks]


def _ours(w, inj, q_m3h, t_return_c):
    """Our numbers for one doublet at q_m3h: well, exchanger, injector and the boiler heat of the separator gas."""
    pt = doublet_at(w, q_m3h, t_return_c)
    r = w.run(q_m3h, pt["freq_hz"])
    mcp_w = pt["mcp_MW_per_K"] * 1e6
    t_brine_out = pt["T_wh_C"] - pt["MW_hx"] * 1e6 / mcp_w
    m_net = (pt["MW_hx"] + pt["MW_hp"]) * 1e3 / (CP * (T_SUPPLY_HEAT_C - t_return_c))   # network water, kg/s
    t_inj = pt["T_wh_C"] - DT_BRINE_MAX_K
    i = inj.run(q_m3h, t_inj)
    return {"q_m3h": q_m3h, "freq_hz": pt["freq_hz"], "T_wellhead_C": pt["T_wh_C"], "p_esp_intake_bar": r["p_esp_intake_bar"],
            "esp_head_bar": r["esp_head_bar"], "p_injection_wellhead_bar": i["p_wh_bar"], "T_brine_out_C": t_brine_out,
            "MW_exchanger": pt["MW_hx"], "MW_boiler_gas": gas.gas_at(q_m3h, w.depth_m)["CH4_MW_LHV"] * BOILER_EFF,
            "MW_heat_pump": pt["MW_hp"], "secondary_m3s": m_net / RHO, "ii_m3h_bar": i["II"],
            "ua_w_per_k": _ua(pt["T_wh_C"], t_return_c, mcp_w, m_net * CP * 1e3, pt["MW_hx"] * 1e6)}


def _theirs(s):
    """Read GEMINI's outputs of the solved project into the keys of _ours."""
    g = s.get_output
    return {"q_m3h": g("producer_well", "flow_rate"), "p_esp_intake_bar": g("producer_well", "esp_intake_pressure"),
            "esp_head_bar": g("producer_well", "esp_discharge_pressure") - g("producer_well", "esp_intake_pressure"),
            "p_injection_wellhead_bar": g("injector_well", "wellhead_pressure"),
            "T_brine_out_C": g("heat_exchanger", "primary_temperature_out"),
            "MW_exchanger": g("heat_exchanger", "heat_duty") / 1e6,
            "MW_boiler_gas": g("boiler", "power_th") / 1e6}


def _version():
    """Path and git commit of the GEMINI simulator package the replay imports."""
    import gemini_simulator
    root = str(Path(gemini_simulator.__file__).parents[2])
    sha = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    return f"{root} @ {sha or 'no git'}"


def replay(n=2, t_return_c=60.0, depth_m=DEPTH_M, esp_depth_m=ESP_DEPTH_M, days=None):
    """Run GEMINI's own solver on the generated project for a few days against our numbers; dict of day rows, file path, basis."""
    w, inj = Producer(depth_m=depth_m, stages=24, esp_depth_m=esp_depth_m), Injector(depth_m=depth_m)
    rows, path = [], None
    for day, d in (days if days is not None else _days(n, t_return_c, depth_m, esp_depth_m)).iterrows():
        o = _ours(w, inj, float(d.q_m3h), t_return_c)
        p = project_dict(w, t_return_c, o["T_wellhead_C"], o["freq_hz"], o["secondary_m3s"], o["ua_w_per_k"], o["ii_m3h_bar"])
        path = path or write_project(RUNS / f"gemini_project_{n}d_{t_return_c:g}C.json", p)
        q_at_our_freq = _solve(p).get_output("producer_well", "flow_rate")
        f = _freq_for_flow(p, o["q_m3h"])
        t = _theirs(_solve(p)) if f is not None else {}
        row = {"date": str(day.date()), "demand_MW": float(d.demand), "freq_hz_ours": o["freq_hz"], "freq_hz_gemini_same_flow": f,
               "q_m3h_gemini_at_our_freq": q_at_our_freq}
        for k in COMPARED:
            row[k + "_ours"] = o[k]
            row[k + "_gemini"] = t.get(k)
            row[k + "_diff_pct"] = None if k not in t or o[k] == 0 else 100 * (t[k] - o[k]) / o[k]
        offset = (RHO - 1000.0) * 9.81 * depth_m / 1e5   # brine column minus GEMINI's water column over the well, bar
        row["water_column_offset_bar"] = offset
        row["esp_head_residual_bar"] = None if not t else t["esp_head_bar"] + offset - o["esp_head_bar"]
        row["p_injection_wellhead_residual_bar"] = (None if not t else
                                                    t["p_injection_wellhead_bar"] - offset - o["p_injection_wellhead_bar"])
        rows.append(row)
    basis = (f"GEMINI simulator {_version()} re-runs our generated project (one doublet; producer with 24-stage ESP, separator, "
             f"filters, counter-flow exchanger, boiler on the separator gas, injector) on {len(rows)} days of 2027 at the "
             "day's flow; the ESP frequency is re-solved so GEMINI's nodal solve gives our flow, then pressures, duty and boiler "
             "heat are compared; differences = (GEMINI - ours) / ours. Not in the native chain: the heat-pump lift after the "
             "exchanger, the backup boiler on the network, staggered outages, our brine density and viscosity in the well "
             "(GEMINI's well PVT is water at standard conditions), the pump similarity law (GEMINI reads the 60 Hz curve at the "
             "actual flow). The residual columns remove the water-column offset: GEMINI's well walks a 1 000 kg/m3 column, ours "
             "1 030 kg/m3 [C]")
    return {"n_doublets": n, "t_return_c": t_return_c, "depth_m": depth_m, "esp_depth_m": esp_depth_m, "days": rows,
            "n_days": len(rows),
            "project_path": path, "gemini_version": _version(), "basis": basis}


if __name__ == "__main__":
    r = replay(2, 57.5)
    for row in r["days"]:
        print(row["date"], {k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items() if k != "date"})
    print(r["project_path"])
