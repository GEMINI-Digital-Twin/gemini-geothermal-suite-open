"""Deterministic comparison of candidate designs (no LLM).

Used to check the agent's results and to make the report table and charts.
Outputs: results/comparison.csv, results/comparison.md, results/*.png,
results/daily_<design>.csv
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import annual_sim  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)

DESIGNS = [
    {"name": "A_2x2500m_preheatHP_engine", "depth_m": 2500, "n_doublets": 2, "heating_mode": "preheat_hp", "gas_use": "engine"},
    {"name": "B_3x2500m_preheatHP_engine", "depth_m": 2500, "n_doublets": 3, "heating_mode": "preheat_hp", "gas_use": "engine"},
    {"name": "C_3x2500m_preheatHP_flare", "depth_m": 2500, "n_doublets": 3, "heating_mode": "preheat_hp", "gas_use": "flare"},
    {"name": "D_3x2500m_HPonly_engine", "depth_m": 2500, "n_doublets": 3, "heating_mode": "hp_only", "gas_use": "engine"},
    {"name": "E_3x3400m_direct_engine", "depth_m": 3400, "n_doublets": 3, "heating_mode": "direct", "gas_use": "engine"},
    {"name": "F_3x3400m_direct_reinject", "depth_m": 3400, "n_doublets": 3, "heating_mode": "direct", "gas_use": "reinject"},
    {"name": "H_2x3400m_direct_engine", "depth_m": 3400, "n_doublets": 2, "heating_mode": "direct", "gas_use": "engine"},
    {"name": "A2_2x2500m_preheatHP_storage2000", "depth_m": 2500, "n_doublets": 2, "heating_mode": "preheat_hp",
     "gas_use": "engine", "storage_mwh": 2000},
]


def main():
    rows = []
    for d in DESIGNS:
        r = annual_sim.evaluate_design(d, save_daily=OUT / f"daily_{d['name']}.csv")
        h, e, c, eq = r["heat_gwh"], r["electricity_gwh"], r["co2_t"], r["equipment_mw"]
        rows.append({
            "design": d["name"], "depth_m": d["depth_m"], "doublets": d["n_doublets"],
            "flow_per_doublet_m3h": r["gemini_doublet"]["flow_m3h"],
            "heat_direct_gwh": h["direct_geothermal"], "heat_pump_gwh": h["heat_pump"],
            "gas_engine_heat_gwh": h["gas_engine"], "storage_gwh": h["storage"],
            "boiler_gwh": h["backup_boiler"], "boiler_pct": round(h["backup_boiler"] / h["demand"] * 100, 1),
            "absorption_gwh": r["cool_gwh"]["absorption"], "electric_chiller_gwh": r["cool_gwh"]["electric_chiller"],
            "grid_el_gwh": e["from_grid"], "pumps_el_gwh": e["pumps"], "gas_engine_el_gwh": e["gas_engine_supply"],
            "co2_t": c["total"], "co2_from_gas_t": c["associated_gas"], "co2_reduction_pct": c["reduction_pct"],
            "boiler_mw": eq["backup_boiler"], "heat_pump_mw": eq["heat_pump"], "electric_chiller_mw": eq["electric_chiller"],
            "violations": len(r["violations"]), "warnings": " | ".join(r["warnings"]),
        })
    with open(OUT / "comparison.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    cols = ["design", "boiler_pct", "grid_el_gwh", "co2_t", "co2_reduction_pct", "heat_pump_mw", "boiler_mw",
            "electric_chiller_mw", "violations"]
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    (OUT / "comparison.md").write_text("\n".join(md) + f"\n\nReference (gas boiler + electric chiller): "
                                       f"{r_ref()} t CO2/yr\n")
    print("\n".join(md))

    # Chart 1: heat supply mix + CO2 per design
    names = [r["design"].split("_", 1)[0] for r in rows]
    parts = [("heat_direct_gwh", "Direct geothermal", "#2a6f97"), ("heat_pump_gwh", "Heat pump", "#61a5c2"),
             ("gas_engine_heat_gwh", "Gas engine heat", "#a9d6e5"), ("storage_gwh", "Storage", "#b5c99a"),
             ("boiler_gwh", "Backup boiler", "#e07a5f")]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    bottom = [0] * len(rows)
    for key, label, col in parts:
        vals = [r[key] for r in rows]
        ax1.bar(names, vals, bottom=bottom, label=label, color=col)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax1.set_ylabel("GWh/yr"), ax1.set_title("Heat supply by source (demand 111.7 GWh)")
    ax1.legend(fontsize=7, frameon=False)
    ax2.bar(names, [r["co2_t"] / 1000 for r in rows], color="#3d405b")
    ax2.axhline(r_ref() / 1000, color="#e07a5f", ls="--", label="Gas boiler + chiller reference")
    ax2.set_ylabel("kt CO2/yr"), ax2.set_title("Annual CO2"), ax2.legend(fontsize=7, frameon=False)
    for ax in (ax1, ax2):
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "comparison.png", dpi=160)

    # Chart 2: daily operation of the best design
    best = min(rows, key=lambda r: (r["violations"], r["co2_t"]))["design"]
    with open(OUT / f"daily_{best}.csv") as f:
        daily = list(csv.DictReader(f))
    x = range(len(daily))
    fig, ax = plt.subplots(figsize=(11, 3.6))
    stack = [("direct_mw", "Direct geothermal", "#2a6f97"), ("heat_pump_mw", "Heat pump", "#61a5c2"),
             ("engine_heat_mw", "Gas engine", "#a9d6e5"), ("storage_out_mw", "Storage", "#b5c99a"),
             ("boiler_mw", "Backup boiler", "#e07a5f")]
    ax.stackplot(x, *[[float(r[k]) for r in daily] for k, _, _ in stack],
                 labels=[s[1] for s in stack], colors=[s[2] for s in stack])
    ax.plot(x, [float(r["heat_demand_mw"]) for r in daily], color="black", lw=0.8, label="Heating demand")
    ax.plot(x, [float(r["cool_demand_mw"]) for r in daily], color="#81b29a", lw=0.8, ls="--", label="Cooling demand")
    ax.set_title(f"Daily operation 2027, design {best}"), ax.set_ylabel("MW"), ax.set_xlabel("Day of year")
    ax.legend(fontsize=7, ncol=4, frameon=False, loc="upper center")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "daily_best.png", dpi=160)
    print("best:", best)


def r_ref():
    return annual_sim.evaluate_design({"name": "ref"})["co2_t"]["reference_gas_boiler_plus_chiller"]


if __name__ == "__main__":
    main()
