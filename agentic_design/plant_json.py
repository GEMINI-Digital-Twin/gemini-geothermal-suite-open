"""Generate, validate and run GEMINI simulator project files for 1-3 doublets.

The bootcamp named project-file generation as the first hurdle for an agent:
a file with a misspelled component, a missing input or wrongly ordered
connections will not load or will silently compute garbage. So the agent
never writes this JSON by hand. It calls ``build_project_dict`` with design
numbers, and ``validate_project`` checks the result before GEMINI runs it.

Topology (N = 1..3 doublets):

    producer_well_i -> production_mixer -> separator -> filter_a -> heat_exchanger
        -> filter_b -> injection_splitter -> injector_well_i
    separator gas -> gas_splitter -> boiler_assoc (used) / flare (unused)
    network return -> heat_exchanger (secondary) -> boiler_assoc -> boiler_ng -> 100 degC

Two components are added to GEMINI's registry at import (no core files edited):

* ``producer_well_fixed_rate`` - producer + ESP at a set flow rate, built on
  GEMINI's IPR/DPDT via ``wells.producer`` (GEMINI's ``producer_well`` instead
  solves the rate from an ESP pump curve, and the example curve cannot reach
  the 300 m3/h cap).
* ``injector_well_corrected`` - injector with the friction sign fixed (see
  ``wells.py``). GEMINI's original ``injector_well`` can be selected for comparison.
"""

import copy
import json

from gemini_model.model_abstract import StaticModel
from gemini_simulator.project_loader import build_project
from gemini_simulator.registry import COMPONENT_REGISTRY

from agentic_design.config import CHALLENGE, Assumptions, gas_properties
from agentic_design.wells import WellDesign, injector, producer

JOULE_PER_KWH = 3.6e6


class ProducerWellFixedRate(StaticModel):
    """Inputs: flow_rate (m3/h). Parameters: depth_m, inner_diameter_m, esp_depth_m, assumptions."""

    def __init__(self):
        self.parameters, self.output = {}, {}

    def update_parameters(self, parameters):
        self.parameters.update(parameters)

    def initialize_state(self, x):
        pass

    def update_state(self, u, x):
        pass

    def calculate_output(self, u, x=None):
        p = self.parameters
        a = Assumptions(**p.get("assumptions", {}))
        design = WellDesign(p["depth_m"], p["inner_diameter_m"], p["esp_depth_m"])
        r = producer(u["flow_rate"], design, a)
        self.output.update({
            "flow_rate": u["flow_rate"],
            "flow_rate_m3s": u["flow_rate"] / 3600.0,
            "pressure_out": r["wellhead_pressure_bar"],
            "temperature_out": r["wellhead_temperature_c"],
            "esp_power_el": r["esp_power_mw"] * 1e6,
            "esp_intake_pressure": r["esp_intake_pressure_bar"],
            "esp_discharge_pressure": r["esp_discharge_pressure_bar"],
            "power_el": r["esp_power_mw"] * 1e6,
            "power_th": 0.0,
            "emission": 0.0,
        })

    def get_output(self):
        return self.output


class InjectorWellCorrected(ProducerWellFixedRate):
    """Inputs: flow_rate (m3/h), wellhead_temperature (C), pressure_in (Pa)."""

    def calculate_output(self, u, x=None):
        p = self.parameters
        a = Assumptions(**p.get("assumptions", {}))
        design = WellDesign(p["depth_m"], p["inner_diameter_m"], p.get("esp_depth_m", 650.0))
        r = injector(u["flow_rate"], u["wellhead_temperature"], design, a)
        whp_pa = r["required_wellhead_pressure_bar"] * 1e5
        eff = p.get("injector_pump", {}).get("efficiency_factor", CHALLENGE["pump_hydraulic_efficiency"])
        ef = p.get("injector_pump", {}).get("electricity_emission_factor", 0.0)
        power = u["flow_rate"] / 3600.0 * max(0.0, whp_pa - u.get("pressure_in", 0.0)) / eff
        self.output.update({
            "wellhead_pressure": r["required_wellhead_pressure_bar"],
            "wellhead_pressure_pa": whp_pa,
            "flow_rate_m3s": u["flow_rate"] / 3600.0,
            "power_el": power,
            "power_th": 0.0,
            "emission": ef / JOULE_PER_KWH * power,
        })


COMPONENT_REGISTRY.setdefault("producer_well_fixed_rate", ProducerWellFixedRate)
COMPONENT_REGISTRY.setdefault("injector_well_corrected", InjectorWellCorrected)


def _vertical_table(depth_m, d_m):
    return [{"MD": 0, "TVD": 0, "ID": d_m}, {"MD": depth_m, "TVD": depth_m, "ID": d_m}]


def build_project_dict(design, op: dict, a: Assumptions = None, hx_ua_w_k: float = None,
                       use_gemini_injector: bool = False) -> dict:
    """Build a GEMINI project for one operating day.

    ``op`` keys: q_per_doublet_m3h, doublets_on, c_sec_w_k (network capacity
    rate), t_return_c, assoc_gas_used_fraction (0-1), ng_fuel_w.
    """
    a = a or Assumptions()
    gas = gas_properties()
    n = op["doublets_on"]
    w = design.well
    rho, cp = CHALLENGE["brine_density_kg_m3"], a.brine_specific_heat_j_kgk
    q_tot_m3s = n * op["q_per_doublet_m3h"] / 3600.0
    qmax_m3s = design.n_doublets * CHALLENGE["max_flow_m3h_per_doublet"] / 3600.0  # plant sized for installed doublets
    r_unit = a.surface_pressure_drop_bar / 4.0 / qmax_m3s  # bar per m3/s; separator, 2 filters, HX share the drop
    a_dict = {k: v for k, v in a.to_dict().items() if k != "maintenance_start_doy"}
    ng_density = a.natural_gas_density_kg_nm3

    comp = {}
    for i in range(1, n + 1):
        comp[f"producer_well_{i}"] = {"type": "producer_well_fixed_rate", "parameters": {
            "depth_m": w.depth_m, "inner_diameter_m": w.inner_diameter_m, "esp_depth_m": w.esp_depth_m,
            "assumptions": a_dict}}
        if use_gemini_injector:
            comp[f"injector_well_{i}"] = {"type": "injector_well", "parameters": {
                "reservoir_pressure_bar": None,  # filled below
                "productivity_index_m3h_per_bar": None,
                "trajectory_table": _vertical_table(w.depth_m, w.inner_diameter_m),
                "roughness_m": a.casing_roughness_m,
                "injector_pump": {"efficiency_factor": CHALLENGE["pump_hydraulic_efficiency"],
                                  "electricity_emission_factor": a.electricity_co2_kg_kwh}}}
        else:
            comp[f"injector_well_{i}"] = {"type": "injector_well_corrected", "parameters": {
                "depth_m": w.depth_m, "inner_diameter_m": w.inner_diameter_m, "assumptions": a_dict,
                "injector_pump": {"efficiency_factor": CHALLENGE["pump_hydraulic_efficiency"],
                                  "electricity_emission_factor": a.electricity_co2_kg_kwh}}}
    comp["production_mixer"] = {"type": "mixer", "parameters": {"num_inputs": n}}
    comp["separator"] = {"type": "separator", "parameters": {
        "flow_resistance": r_unit, "temperature_drop": a.surface_temperature_loss_c,
        "gas_water_ratio": CHALLENGE["gas_liquid_ratio_nm3_per_m3"], "gas_density": gas["density_kg_nm3"]}}
    for f in ("filter_a", "filter_b"):
        comp[f] = {"type": "filter", "parameters": {
            "base_resistance": r_unit, "fouling_coeff_a": 0.0, "fouling_coeff_b": 0.0, "temperature_drop": 0.0}}
    comp["heat_exchanger"] = {"type": "heat_exchanger", "parameters": {
        "flow_resistance": r_unit, "flow_configuration": "counter",
        "heat_transfer_coefficient": hx_ua_w_k, "fluid_density": rho, "specific_heat": cp}}
    comp["injection_splitter"] = {"type": "splitter", "parameters": {"split_fractions": [1.0 / n] * n}}
    used = op.get("assoc_gas_used_fraction", 1.0)
    comp["gas_splitter"] = {"type": "splitter", "parameters": {"split_fractions": [used, 1.0 - used]}}
    boiler_common = {"efficiency_factor": a.boiler_efficiency, "fluid_density": rho, "specific_heat": cp}
    comp["boiler_assoc"] = {"type": "boiler", "parameters": {
        **boiler_common, "caloric_value": gas["lhv_mj_kg"] * 1e6,
        "gas_emission_factor": gas["co2_kg_nm3_burned"] / gas["lhv_mj_nm3"] * 1e3}}
    comp["boiler_ng"] = {"type": "boiler", "parameters": {
        **boiler_common, "caloric_value": a.natural_gas_lhv_mj_nm3 / ng_density * 1e6,
        "gas_emission_factor": a.natural_gas_co2_kg_nm3 / a.natural_gas_lhv_mj_nm3 * 1e3}}

    if use_gemini_injector:
        from agentic_design.config import reservoir_pressure_bar
        from agentic_design.wells import productivity_index_m3h_per_bar
        for i in range(1, n + 1):
            comp[f"injector_well_{i}"]["parameters"]["reservoir_pressure_bar"] = reservoir_pressure_bar(w.depth_m)
            comp[f"injector_well_{i}"]["parameters"]["productivity_index_m3h_per_bar"] = productivity_index_m3h_per_bar(a)

    sec_flow_m3s = op["c_sec_w_k"] / (rho * cp)  # capacity-equivalent flow (HX/boiler use one rho*cp)
    boundary = [{"component": f"producer_well_{i}", "key": "flow_rate", "value": op["q_per_doublet_m3h"]}
                for i in range(1, n + 1)]
    boundary += [
        {"component": "heat_exchanger", "key": "secondary_flow_rate", "value": sec_flow_m3s},
        {"component": "heat_exchanger", "key": "secondary_temperature_in", "value": op["t_return_c"]},
        {"component": "boiler_ng", "key": "gas_flow_rate", "value": op["ng_fuel_w"] / (a.natural_gas_lhv_mj_nm3 / ng_density * 1e6)},
    ]
    conn = []
    for i in range(1, n + 1):
        conn.append({"predecessor": f"producer_well_{i}", "successor": "production_mixer",
                     "ports": [["flow_rate_m3s", f"input_{i - 1}_flow"], ["temperature_out", f"input_{i - 1}_temperature"]]})
    conn += [
        {"predecessor": "production_mixer", "successor": "separator",
         "ports": [["flow", "flow_rate"], ["temperature", "temperature"]]},
        {"predecessor": "producer_well_1", "successor": "separator", "ports": [["pressure_out", "pressure"]]},
        {"predecessor": "separator", "successor": "filter_a",
         "ports": [["pressure_out", "pressure"], ["temperature_out", "temperature"], ["flow_rate", "flow_rate"]]},
        {"predecessor": "separator", "successor": "gas_splitter", "ports": [["gas_mass_flow_rate", "input"]]},
        {"predecessor": "filter_a", "successor": "heat_exchanger",
         "ports": [["pressure_out", "pressure_in"], ["temperature_out", "primary_temperature_in"],
                   ["flow_rate", "primary_flow_rate"]]},
        {"predecessor": "heat_exchanger", "successor": "filter_b",
         "ports": [["pressure_out", "pressure"], ["primary_temperature_out", "temperature"],
                   ["primary_flow_rate", "flow_rate"]]},
        {"predecessor": "filter_b", "successor": "injection_splitter", "ports": [["flow_rate_m3h", "input"]]},
    ]
    for i in range(1, n + 1):
        conn.append({"predecessor": "injection_splitter", "successor": f"injector_well_{i}",
                     "ports": [[f"output_{i - 1}", "flow_rate"]]})
        conn.append({"predecessor": "filter_b", "successor": f"injector_well_{i}",
                     "ports": [["temperature_out", "wellhead_temperature"], ["pressure_out_pa", "pressure_in"]]})
    conn += [
        {"predecessor": "heat_exchanger", "successor": "boiler_assoc",
         "ports": [["secondary_temperature_out", "temperature_in"], ["secondary_flow_rate", "water_flow_rate"]]},
        {"predecessor": "gas_splitter", "successor": "boiler_assoc", "ports": [["output_0", "gas_flow_rate"]]},
        {"predecessor": "boiler_assoc", "successor": "boiler_ng",
         "ports": [["temperature_out", "temperature_in"], ["water_flow_rate", "water_flow_rate"]]},
    ]
    return {
        "_description": f"{design.describe()} | {n} doublet(s) on at {op['q_per_doublet_m3h']:.0f} m3/h each",
        "_units": "flow m3/s on surface (m3/h at wells), pressure bar (Pa where named *_pa), temperature degC",
        "components": comp, "boundary_inputs": boundary, "connections": conn,
    }


# ----------------------------------------------------------------------------
# Validation: catch what makes GEMINI fail or silently mis-compute
# ----------------------------------------------------------------------------
REQUIRED_INPUTS = {
    "producer_well_fixed_rate": {"flow_rate"},
    "injector_well_corrected": {"flow_rate", "wellhead_temperature", "pressure_in"},
    "injector_well": {"flow_rate", "wellhead_temperature"},
    "separator": {"pressure", "temperature", "flow_rate"},
    "filter": {"pressure", "temperature", "flow_rate"},
    "heat_exchanger": {"pressure_in", "primary_flow_rate", "secondary_flow_rate",
                       "primary_temperature_in", "secondary_temperature_in"},
    "boiler": {"temperature_in", "water_flow_rate"},
    "splitter": {"input"},
}


def validate_project(project: dict) -> list:
    """Return a list of problems (empty = OK)."""
    errs = []
    comps = project.get("components", {})
    for key in ("components", "boundary_inputs", "connections"):
        if key not in project:
            errs.append(f"missing section '{key}'")
    for name, spec in comps.items():
        if spec.get("type") not in COMPONENT_REGISTRY:
            errs.append(f"{name}: unknown type '{spec.get('type')}'")
    provided = {name: set() for name in comps}
    for b in project.get("boundary_inputs", []):
        if b["component"] not in comps:
            errs.append(f"boundary input on unknown component '{b['component']}'")
        else:
            provided[b["component"]].add(b["key"])
    seen_groups, last_succ = set(), None
    for c in project.get("connections", []):
        for role in ("predecessor", "successor"):
            if c[role] not in comps:
                errs.append(f"connection {c[role]!r} is not a declared component (check spelling)")
        if c["successor"] != last_succ:
            if c["successor"] in seen_groups:
                errs.append(f"connections into '{c['successor']}' are not consecutive (GEMINI evaluates it twice)")
            seen_groups.add(c["successor"])
            last_succ = c["successor"]
        ports = c.get("ports") or [[c.get("predecessor_output"), c.get("successor_input")]]
        for _, inp in ports:
            if c["successor"] in provided:
                provided[c["successor"]].add(inp)
    for name, spec in comps.items():
        t = spec.get("type")
        need = set(REQUIRED_INPUTS.get(t, set()))
        if t == "mixer":
            need = {f"input_{i}_{k}" for i in range(spec["parameters"]["num_inputs"]) for k in ("flow", "temperature")}
        if t == "boiler":
            need = need | ({"gas_flow_rate"} if "gas_volumetric_flow_rate" not in provided[name] else set())
        missing = need - provided[name]
        if missing:
            errs.append(f"{name} ({t}) has unconnected inputs: {sorted(missing)}")
        fr = spec.get("parameters", {}).get("split_fractions")
        if fr is not None and abs(sum(fr) - 1.0) > 1e-9:
            errs.append(f"{name}: split fractions sum to {sum(fr):.4f}, not 1")
    return errs


def run_project(project: dict):
    """Validate, then build and run one GEMINI steady state. Returns the solver."""
    errs = validate_project(project)
    if errs:
        raise ValueError("Project file rejected before GEMINI run:\n- " + "\n- ".join(errs))
    solver = build_project(copy.deepcopy(project))
    solver.run()
    return solver


def save_project(project: dict, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2)
