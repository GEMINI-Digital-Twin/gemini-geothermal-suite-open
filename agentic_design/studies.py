"""Design studies for the report: full sweep, Pareto front, cost and technical sensitivities.

    python -m agentic_design.studies            # writes agentic_design/results/studies/*.csv (+ pareto.png)

All numbers come from the same annual model, checker and cost model the agent uses.
"""

import dataclasses
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_design.agent.tools import ToolBox
from agentic_design.annual import PlantDesign, run_year
from agentic_design.checks import check
from agentic_design.config import Assumptions
from agentic_design.economics import CostAssumptions, economics
from agentic_design.wells import WellDesign

OUT = Path(__file__).resolve().parent / "results" / "studies"

COST_CASES = {
    "base (CO2 valued at 450 EUR/t)": {}, "CO2 value 82 (ETS today)": {"co2_shadow_eur_per_t": 82},
    "CO2 value 250 (EIB 2030)": {"co2_shadow_eur_per_t": 250}, "CO2 value 800 (EIB 2050)": {"co2_shadow_eur_per_t": 800},
    "electricity 80 (ThermoGIS)": {"electricity_eur_per_mwh": 80},
    "electricity 250": {"electricity_eur_per_mwh": 250}, "gas 35": {"natural_gas_eur_per_mwh": 35},
    "gas 90": {"natural_gas_eur_per_mwh": 90}, "wells -30%": {"well_cost_scaling": 1.3 * 0.7},
    "wells +30%": {"well_cost_scaling": 1.3 * 1.3}, "discount 4%": {"discount_rate": 0.04},
    "discount 8%": {"discount_rate": 0.08},
    "chillers/boilers +50%": {"electric_chiller_eur_per_kw": 375, "absorption_chiller_eur_per_kw": 750,
                              "boiler_eur_per_kw": 150},
    "heat pump 700 EUR/kW": {"heat_pump_eur_per_kw": 700},
    "gas reinjection capex x2": {"gas_reinjection_meur": 2.0, "gas_reinjection_meur_per_doublet": 1.0},
}
TECH_CASES = {
    "base": {}, "heating return 45 C": {"heating_return_temperature_c": 45.0},
    "heating return 65 C": {"heating_return_temperature_c": 65.0},
    "all doublets off together 35 d": {"maintenance_mode": "simultaneous"},
    "grid CO2 0.1 kg/kWh": {"electricity_co2_kg_kwh": 0.1}, "grid CO2 0.4 kg/kWh": {"electricity_co2_kg_kwh": 0.4},
    "well U 5 W/m2K": {"well_heat_transfer_u_w_m2k": 5.0}, "well U 20 W/m2K": {"well_heat_transfer_u_w_m2k": 20.0},
}


RECOMMENDED = "2x3500m_ABS5_EC5_RI"


def _design(name):
    n, z, idm, esp, hp, ab, ec, ri = ToolBox.parse_name(name)
    return PlantDesign(name, n, WellDesign(z, idm, esp), heat_pump_mw=hp, absorption_mw=ab, electric_chiller_mw=ec,
                       gas_reinjection=ri)


def evaluate(name, a=None, c=None):
    a = a or Assumptions()
    d = _design(name)
    daily, k, _, _ = run_year(d, a)
    viol = [f["code"] for f in check(daily, k, d, a) if f["severity"] == "violation"]
    e = economics(d, daily, k, a, c)
    return {"name": name, "meets_all_constraints": not viol, "violations": ",".join(viol),
            "co2_kt": k["co2_t"] / 1e3, "geothermal_share_pct": 100 * k["geothermal_share_of_heating"],
            "natural_gas_heat_gwh": k["heating_natural_gas_gwh"], "electricity_gwh": k["electricity_gwh"],
            "capex_meur": e["capex_meur"], "cost_eur_mwh": e["lcoe_eur_per_mwh"],
            "cost_with_co2_eur_mwh": e["lcoe_with_co2_eur_per_mwh"],
            "cost_with_co2_value_eur_mwh": e["lcoe_with_shadow_co2_eur_per_mwh"],
            "backup_boiler_mw": e["boiler_capacity_mw"]}, \
        (d, daily, k)


def full_sweep(doublets=(1, 2, 3), depths=(2500, 3000, 3500), hps=(0, 6, 12), abss=(0, 5), ecs=(5, 10), ris=(False, True)):
    rows = [evaluate(ToolBox.canonical_name(n, z, 0.20, 650.0, hp, ab, ec, ri))[0]
            for n, z, hp, ab, ec, ri in itertools.product(doublets, depths, hps, abss, ecs, ris)]
    return pd.DataFrame(rows)


def pareto(df):
    f = df[df["meets_all_constraints"]].sort_values("cost_eur_mwh")
    keep, best = [], np.inf
    for _, r in f.iterrows():
        if r["co2_kt"] < best - 1e-9:
            keep.append(r)
            best = r["co2_kt"]
    return pd.DataFrame(keep)


def cost_sensitivity(names):
    runs = {n: evaluate(n)[1] for n in names}
    rows = []
    for case, ch in COST_CASES.items():
        c = dataclasses.replace(CostAssumptions(), **ch)
        row = {"case": case, **{n: economics(*runs[n], Assumptions(), c)["lcoe_with_shadow_co2_eur_per_mwh"] for n in names}}
        row["cheapest"] = min(names, key=lambda n: row[n])
        rows.append(row)
    return pd.DataFrame(rows)


def tech_sensitivity(names):
    rows = []
    for case, ch in TECH_CASES.items():
        a = dataclasses.replace(Assumptions(), **ch)
        for n in names:
            rows.append({"case": case, **evaluate(n, a)[0]})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sweep = full_sweep()
    sweep.to_csv(OUT / "sweep.csv", index=False)
    par = pareto(sweep)
    par.to_csv(OUT / "pareto.csv", index=False)
    names = ["1x3000m_EC10", "2x3000m_EC10", "2x3500m_EC10_RI", "2x3000m_HP6_ABS5_EC5_RI", "2x3500m_ABS5_EC5_RI",
             "3x3500m_ABS5_EC5_RI"]
    cost_sensitivity(names).to_csv(OUT / "cost_sensitivity.csv", index=False)
    tech_sensitivity(names).to_csv(OUT / "tech_sensitivity.csv", index=False)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ok = sweep[sweep["meets_all_constraints"]]
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for n, mk in ((1, "o"), (2, "s"), (3, "^")):
            for ri, fc in ((False, None), (True, "none")):
                s = ok[ok["name"].str.startswith(f"{n}x") & (ok["name"].str.endswith("_RI") == ri)]
                ax.scatter(s["co2_kt"], s["cost_eur_mwh"], marker=mk, alpha=0.6, color=f"C{n - 1}",
                           facecolors=fc, label=f"{n} doublet(s)" + (", gas reinjected" if ri else ""))
        ax.plot(par["co2_kt"], par["cost_eur_mwh"], "k--", lw=1, label="Pareto front")
        pick = ok.loc[ok["name"] == RECOMMENDED]
        ax.scatter(pick["co2_kt"], pick["cost_eur_mwh"], s=160, facecolors="none", edgecolors="k", lw=1.5)
        ax.annotate(RECOMMENDED, (pick["co2_kt"].iloc[0], pick["cost_eur_mwh"].iloc[0]), xytext=(10, -14),
                    textcoords="offset points", fontsize=9)
        ax.set_xlabel("CO2 emissions (kt/yr)")
        ax.set_ylabel("Levelised cost (EUR/MWh delivered, excl. CO2 price)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        fig.savefig(OUT / "pareto.png", dpi=160)
    except ImportError:
        pass
    print(par[["name", "co2_kt", "geothermal_share_pct", "capex_meur", "cost_eur_mwh", "cost_with_co2_eur_mwh"]]
          .round(2).to_string(index=False))
    print(f"files in {OUT}")


if __name__ == "__main__":
    main()
