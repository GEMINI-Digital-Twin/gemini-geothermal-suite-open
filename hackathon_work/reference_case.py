"""GEMINI hackathon: conventional reference plant for the same 2027 loads.

Run in GEMINI repository root:
    py -3.11 -m poetry run python hackathon_work/reference_case.py

Gas boiler (eta 0.90, natural gas 56.6 kg CO2/GJ) for heating and an electric
chiller (COP 5.0) for cooling; grid electricity 0.3 kg CO2/kWh (same factor as
the geothermal candidates). Writes outputs/reference/summary.json and compares
with every geothermal candidate summary found in outputs/candidates/base/.
"""

from __future__ import annotations

import json
from pathlib import Path

from demand_baseline import load_demand

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "reference"
CANDIDATES = ROOT / "outputs" / "candidates" / "base"

# ASSUMED reference plant (user decision); emission factors as in projects/candidates_2027.json.
BOILER_EFFICIENCY = 0.90
GAS_EMISSION_FACTOR_KG_GJ = 56.6
GAS_LHV_MJ_NM3 = 35.8
CHILLER_COP = 5.0
ELECTRICITY_EMISSION_FACTOR_KG_KWH = 0.3


def reference_summary() -> dict:
    heating = load_demand("GEMINI_Heating_Demand_Daily_2027.csv", "heating_demand_MWth")
    cooling = load_demand("GEMINI_Cooling_Demand_Daily_2027.csv", "cooling_demand_MWcool")
    heat_gwh = sum(heating.values()) * 24 / 1000
    cool_gwh = sum(cooling.values()) * 24 / 1000
    gas_gwh = heat_gwh / BOILER_EFFICIENCY
    el_gwh = cool_gwh / CHILLER_COP
    gas_t = gas_gwh * 3600 * GAS_EMISSION_FACTOR_KG_GJ / 1000  # GWh -> GJ: x 3600
    el_t = el_gwh * 1e6 * ELECTRICITY_EMISSION_FACTOR_KG_KWH / 1000
    return {
        "assumptions": {
            "boiler_efficiency": BOILER_EFFICIENCY, "gas_emission_factor_kg_per_GJ": GAS_EMISSION_FACTOR_KG_GJ,
            "gas_lhv_MJ_per_Nm3": GAS_LHV_MJ_NM3, "chiller_cop": CHILLER_COP,
            "electricity_emission_factor_kg_per_kWh": ELECTRICITY_EMISSION_FACTOR_KG_KWH,
        },
        "heating_demand_GWh": heat_gwh,
        "cooling_demand_GWh": cool_gwh,
        "gas_fuel_GWh": gas_gwh,
        "gas_Mm3": gas_gwh * 3600 / GAS_LHV_MJ_NM3 / 1e3,
        "grid_import_GWh": el_gwh,
        "emissions_gas_t": gas_t,
        "emissions_electricity_t": el_t,
        "emissions_t": gas_t + el_t,
    }


def reduction(reference: float, value: float) -> float:
    return (reference - value) / reference


def main():
    ref = reference_summary()
    comparisons = {}
    for path in sorted(CANDIDATES.glob("*/summary.json")):
        s = json.loads(path.read_text(encoding="utf-8"))
        gas = s["external_gas_fuel_GWh"]
        comparisons[s["candidate"]["name"]] = {
            "emissions_t": s["emissions_t"], "emissions_reduction": reduction(ref["emissions_t"], s["emissions_t"]),
            "external_gas_GWh": gas, "external_gas_reduction": reduction(ref["gas_fuel_GWh"], gas),
            "grid_import_GWh": s["grid_import_GWh"], "grid_import_change": -reduction(ref["grid_import_GWh"], s["grid_import_GWh"]),
            "verdict": s.get("ranking", {}).get("status"),
        }
    ref["candidates_vs_reference"] = comparisons
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(ref, indent=2), encoding="utf-8")

    print("=== CONVENTIONAL REFERENCE: gas boiler (eta 0.90) + electric chiller (COP 5.0), 2027 loads ===")
    print(f"Heating {ref['heating_demand_GWh']:.2f} GWh -> natural gas {ref['gas_fuel_GWh']:.2f} GWh fuel ({ref['gas_Mm3']:.2f} Mm3)")
    print(f"Cooling {ref['cooling_demand_GWh']:.2f} GWh -> grid electricity {ref['grid_import_GWh']:.2f} GWh")
    print(f"Emissions: {ref['emissions_t']:.0f} t CO2/yr (gas {ref['emissions_gas_t']:.0f}, electricity {ref['emissions_electricity_t']:.0f})")
    for name, c in comparisons.items():
        print(
            f"{name} [{c['verdict']}]: emissions {c['emissions_t']:.0f} t ({c['emissions_reduction'] * 100:.1f}% lower), "
            f"external gas {c['external_gas_GWh']:.3f} GWh ({c['external_gas_reduction'] * 100:.1f}% lower), "
            f"grid import {c['grid_import_GWh']:.2f} GWh ({c['grid_import_change'] * 100:+.0f}%)"
        )
    print(f"OUTPUT: hackathon_work/outputs/reference/summary.json")


if __name__ == "__main__":
    main()
