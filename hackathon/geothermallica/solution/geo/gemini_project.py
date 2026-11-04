"""One of our designs written as a native GEMINI simulator project and re-run by GEMINI's own solver.

Format: GEMINI's simulator_examples/projects/doublet_plant.json (producer with ESP, separator, filters, exchanger,
boiler on the separator gas, injector), plus our four models: absorption chiller before the exchanger, heat pump after it,
dissolved-gas bubble point and thermal breakthrough on the producer flow. Parameter sources are in the inline comments.
replay() returns, for a few days of 2027, GEMINI's outputs next to ours (geo.gemini_compare), the project file path and a basis.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

import geo.gemini_contrib  # noqa: F401  (GEMINI development tree first on sys.path)
from geo import gas, lifetime
from geo.common import DEPTH_M, MU_PA_S, PERM_MD, RHO, T_SUPPLY_HEAT_C, THICKNESS_M, t_reservoir_c
from geo.cost import BOILER_EFF, EF_EL_KG_KWH, GCV_LHV
from geo.gemini_compare import compare, ours, theirs
from geo.gemini_contrib import absorption_chiller, heatpump_lift, henry_gas, thermal_breakthrough
from geo.plant import CP, LORENZ_EFF, T_ABS_MIN_C
from geo.well import CELL_M, ESP_DEPTH_M, PUMP_EFF, ROUGHNESS_M, TUBING_ID_M, Injector, reservoir_pressure
from geo.year import AUX_KW_PER_KW_COLD, COP_ABSORPTION, heating_year, table
from gemini_simulator.project_loader import build_project
from gemini_simulator.registry import COMPONENT_REGISTRY

P_WELLHEAD_BAR = 10.0        # producer wellhead pressure the ESP holds, bar; the floor used by geo.well.Producer
SEPARATOR = {"flow_resistance": 3.6, "temperature_drop": 0.0}   # resistance as in GEMINI's example; no temperature loss, assumed
FILTER = {"base_resistance": 3.6, "fouling_coeff_a": 18.0, "fouling_coeff_b": 0.036, "temperature_drop": 0.0}   # filter_b of GEMINI's example; no temperature drop assumed
M_GAS = gas.Y_CH4 * gas.M_CH4 + gas.Y_CO2 * gas.M_CO2    # molar mass of the 80/20 gas, kg/mol
GAS_DENSITY = M_GAS / gas.V_M                            # gas density at normal conditions, kg/Nm3
GAS_LHV_J_KG = gas.Y_CH4 * gas.LHV_CH4 * 1e3 / M_GAS     # lower heating value of the gas, J/kg (only the methane burns)
GAS_CO2_KG_GJ = gas.M_CO2 / (gas.Y_CH4 * gas.LHV_CH4 * 1e-6)   # CO2 per GJ burned: one CO2 per mole of gas, kg/GJ
BOILER_EFF_LHV = BOILER_EFF * GCV_LHV   # GEMINI's boiler burns caloric_value on LHV; our efficiency is on GCV
RUNS = Path(__file__).resolve().parents[1] / "ai" / "runs"

# our models, registered only where the GEMINI tree in use lacks them (TNO's tree; our fork registers its own copies)
for _name, _module in (("absorption_chiller", absorption_chiller), ("heatpump_lift", heatpump_lift),
                       ("henry_gas", henry_gas), ("thermal_breakthrough", thermal_breakthrough)):
    if _name not in COMPONENT_REGISTRY:
        _module.register()


def _stations(depth_m):
    """Trajectory table of a vertical well, one station per CELL_M, the tubing diameter of geo.well."""
    md = np.arange(0.0, depth_m + 1e-9, CELL_M)
    return [{"MD": float(z), "TVD": float(z), "ID": TUBING_ID_M} for z in md]


def _well_params(w, depth_m, ii):
    """Shared producer and injector parameters in the units GEMINI's well components expect."""
    return {"reservoir_pressure_bar": reservoir_pressure(depth_m), "trajectory_table": _stations(depth_m),
            "roughness_m": ROUGHNESS_M, "ambient_temperature_c": w.t_ambient_c,
            "productivity_index_m3h_per_bar": ii}


def _our_models(n, day):
    """Project components of our four models for one doublet of n on this day (keys of geo.gemini_compare.ours)."""
    chiller = {"cop_thermal": COP_ABSORPTION, "min_driving_temperature": T_ABS_MIN_C, "fluid_density": RHO,
               "specific_heat": CP * 1e3, "auxiliary_power_fraction": AUX_KW_PER_KW_COLD}
    # the exchanger uses one density for both sides and hands the water over as m3/s at RHO, so the heat pump does too
    pump = {"Ts_in_minimum": day["T_hp_floor_C"], "Th_out_target": T_SUPPLY_HEAT_C, "eta_lorenz": LORENZ_EFF,
            "rho_s": RHO, "rho_h": RHO, "Cp_s": CP * 1e3, "Cp_h": CP * 1e3}
    henry = {"GLR": gas.GLR, "methane_fraction": gas.Y_CH4, "co2_fraction": gas.Y_CO2, "nacl_concentration": gas.SALT_G_L,
             "salting_out_coefficient": gas.K_SALT_CH4, "salting_out_convention": "ln", "henry_method": "fits",
             "henry_fits": gas.FITS}   # the defaults of geo.gas.p_bubble_bar
    front = {"rock_density": lifetime.ROCK_DENSITY, "rock_heat_capacity": lifetime.ROCK_CP, "water_density": RHO,
             "water_heat_capacity": lifetime.BRINE_CP, "well_spacing": lifetime.SPACING_M, "porosity": lifetime.PHI,
             "reservoir_thickness": THICKNESS_M, "reservoir_permeability": PERM_MD * lifetime.MD_TO_M2,
             "viscosity": MU_PA_S, "number_of_doublets": n}
    return {"absorption_chiller": {"type": "absorption_chiller", "parameters": chiller},
            "heat_pump": {"type": "heatpump_lift", "parameters": pump},
            "gas": {"type": "henry_gas", "parameters": henry},
            "breakthrough": {"type": "thermal_breakthrough", "parameters": front}}


def project_dict(w, t_return_c, day, n=1):
    """Native GEMINI project dict of one doublet (of n) around the producer w; day = geo.gemini_compare.ours() of that day."""
    prod = {**_well_params(w, w.depth_m, w.pi), "esp_depth_m": w.esp_depth_m, "esp_freq_hz": day["freq_hz"],
            "esp": {**w.pump.parameters, "electricity_emission_factor": EF_EL_KG_KWH}}
    mine = _our_models(n, day)
    comps = {"producer_well": {"type": "producer_well", "parameters": prod},
             "separator": {"type": "separator",
                           "parameters": {**SEPARATOR, "gas_water_ratio": gas.GLR, "gas_density": GAS_DENSITY}},
             "filter_a": {"type": "filter", "parameters": FILTER},
             "absorption_chiller": mine["absorption_chiller"],
             "heat_exchanger": {"type": "heat_exchanger", "parameters": {"flow_resistance": 0.0, "flow_configuration": "counter",
                                                                         "heat_transfer_coefficient": day["ua_w_per_k"],
                                                                         "fluid_density": RHO, "specific_heat": CP * 1e3}},
             "heat_pump": mine["heat_pump"],
             "filter_b": {"type": "filter", "parameters": FILTER},
             "boiler": {"type": "boiler", "parameters": {"caloric_value": GAS_LHV_J_KG, "efficiency_factor": BOILER_EFF_LHV,
                                                         "gas_emission_factor": GAS_CO2_KG_GJ, "fluid_density": RHO,
                                                         "specific_heat": CP * 1e3}},
             "injector_well": {"type": "injector_well", "parameters": {**_well_params(w, w.depth_m, day["ii_m3h_bar"]),
                                                                       "injector_pump": {"efficiency_factor": PUMP_EFF,
                                                                                         "electricity_emission_factor": EF_EL_KG_KWH}}},
             "gas": mine["gas"], "breakthrough": mine["breakthrough"]}
    boundary = [{"component": "producer_well", "key": "wellhead_pressure", "value": P_WELLHEAD_BAR},
                {"component": "producer_well", "key": "wellhead_temperature", "value": day["T_wellhead_C"]},
                {"component": "absorption_chiller", "key": "temperature_floor", "value": day["T_chiller_floor_C"]},
                {"component": "heat_exchanger", "key": "secondary_temperature_in", "value": t_return_c},
                {"component": "heat_exchanger", "key": "secondary_flow_rate", "value": day["secondary_m3s"]},
                {"component": "gas", "key": "temperature", "value": t_reservoir_c(w.depth_m) + 273.15}]

    def link(a, b, ports):
        return {"predecessor": a, "successor": b, "ports": ports}
    conn = [link("producer_well", "separator", [["flow_rate_m3s", "flow_rate"], ["pressure_out", "pressure"],
                                                ["temperature_out", "temperature"]]),
            link("separator", "filter_a", [["pressure_out", "pressure"], ["temperature_out", "temperature"],
                                           ["flow_rate", "flow_rate"]]),
            link("filter_a", "absorption_chiller", [["pressure_out", "pressure"], ["temperature_out", "temperature"],
                                                    ["flow_rate", "flow_rate"]]),
            link("absorption_chiller", "heat_exchanger", [["pressure_out", "pressure_in"],
                                                          ["temperature_out", "primary_temperature_in"],
                                                          ["flow_rate", "primary_flow_rate"]]),
            link("heat_exchanger", "heat_pump", [["primary_temperature_out", "Ts_in"], ["primary_flow_rate", "source_flow_rate"],
                                                 ["secondary_temperature_out", "Th_in"], ["secondary_flow_rate", "hot_flow_rate"],
                                                 ["pressure_out", "source_pressure_in"]]),
            link("heat_pump", "filter_b", [["source_pressure_out", "pressure"], ["Ts_out", "temperature"],
                                           ["source_flow_rate", "flow_rate"]]),
            link("heat_pump", "boiler", [["Th_out", "temperature_in"], ["hot_flow_rate", "water_flow_rate"]]),   # in series
            link("separator", "boiler", [["gas_mass_flow_rate", "gas_flow_rate"]]),
            link("filter_b", "injector_well", [["flow_rate_m3h", "flow_rate"], ["temperature_out", "wellhead_temperature"],
                                               ["pressure_out_pa", "pressure_in"]]),
            link("producer_well", "gas", [["flow_rate_m3s", "flowrate"]]),
            link("producer_well", "breakthrough", [["flow_rate_m3s", "flowrate"]])]
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
    if flow(f_hi) < q_m3h or flow(f_lo) > q_m3h:   # the bracket does not hold
        return None
    for _ in range(30):
        f = 0.5 * (f_lo + f_hi)
        f_lo, f_hi = (f, f_hi) if flow(f) < q_m3h else (f_lo, f)
    return f_hi


def _days(n, t_return_c, depth_m, esp_depth_m, k=3):
    """Up to k representative days with every doublet running: the coldest, the median demand and the mildest."""
    d = heating_year(n, t_return_c, depth_m=depth_m, esp_depth_m=esp_depth_m)
    d = d[(d.doublets_on == n) & (d.q_m3h > 0)].sort_values("demand")
    picks = [d.index[-1], d.index[len(d) // 2], d.index[0]][:k]
    return d.loc[picks]


def _version():
    """Path and git commit of the GEMINI simulator package the replay imports."""
    import gemini_simulator
    root = str(Path(gemini_simulator.__file__).parents[2])
    sha = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    return f"{root} @ {sha or 'no git'}"


def replay(n=2, t_return_c=60.0, depth_m=DEPTH_M, esp_depth_m=ESP_DEPTH_M, days=None):
    """Run GEMINI's own solver on the generated project for a few days against our numbers; dict of day rows, file path, basis."""
    tab, inj = table(t_return_c, depth_m, True, esp_depth_m), Injector(depth_m=depth_m)
    w = tab.w
    rows, path = [], None
    for day, d in (days if days is not None else _days(n, t_return_c, depth_m, esp_depth_m)).iterrows():
        o = ours(w, inj, tab.at_output(float(d.demand) / int(d.doublets_on)), t_return_c, n)   # the day's dispatch per doublet
        p = project_dict(w, t_return_c, o, n)
        path = path or write_project(RUNS / f"gemini_project_{n}d_{t_return_c:g}C.json", p)
        q_at_our_freq = _solve(p).get_output("producer_well", "flow_rate")
        f = _freq_for_flow(p, o["q_m3h"])
        t = theirs(_solve(p)) if f is not None else {}
        row = {"date": str(day.date()), "demand_MW": float(d.demand), "freq_hz_ours": o["freq_hz"], "freq_hz_gemini_same_flow": f,
               "q_m3h_gemini_at_our_freq": q_at_our_freq, **compare(o, t)}
        offset = (RHO - 1000.0) * 9.81 * depth_m / 1e5   # brine column minus GEMINI's water column over the well, bar
        row["water_column_offset_bar"] = offset
        row["esp_head_residual_bar"] = None if not t else t["esp_head_bar"] + offset - o["esp_head_bar"]
        row["p_injection_wellhead_residual_bar"] = (None if not t else
                                                    t["p_injection_wellhead_bar"] - offset - o["p_injection_wellhead_bar"])
        rows.append(row)
    basis = (f"GEMINI simulator {_version()} re-runs our generated project (one doublet; producer with 24-stage ESP, separator, "
             "filters, our absorption chiller, counter-flow exchanger, our heat pump with a brine floor, then the boiler on the separator "
             f"gas, injector, plus our dissolved-gas bubble point and thermal breakthrough on the producer flow) on {len(rows)} "
             "days of 2027 at the day's dispatch per doublet; the ESP frequency is re-solved so GEMINI's nodal solve gives our "
             "flow; differences = (GEMINI - ours) / ours. Inputs by construction: the exchanger UA is set to give our duty, the "
             "chiller floor and the heat-pump floor are our day's brine temperatures, the network water flow is ours, so the "
             "exchanger duty, the heat-pump duty on full-draw days and the boiler heat match by construction. Independent: the "
             "pressures from GEMINI's nodal solve, the heat-pump COP and brine outlet from its own Lorenz solve, the bubble point "
             "and the breakthrough time from the GEMINI models with our parameters; on the mildest day the chiller drive (set by "
             "the chiller's 78 C minimum, not by our floor) and the supply temperature the series chain really reaches. Not in "
             "the native chain: the boiler lift at low return temperatures, the backup boiler on the network, staggered outages, "
             "our brine density and viscosity in the well "
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
