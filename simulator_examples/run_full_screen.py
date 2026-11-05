"""Screen the whole design space on the report's basis (weather, outage, lined casing).

The first screen (``run_design_screening.py``, 96 designs) predates the
chiller menu, free cooling, aquifer cold storage (ATES) and the whole-source
35-day outage. This one runs every combination the toolkit now offers, on
the same basis as the final pick: a weather year, corrosion mitigation
priced, and each doublet down 35 days at a different time in the lowest-load
window. The grid:

- 1-3 doublets x 2.5 / 2.8 / 3.1 / 3.4 / 4.0 km
- temperature top-up by gas boiler, or heat pump + boiler
- with or without a CHP on the co-produced gas
- cooling: absorption (with half-size electric backup), or an electric
  chiller (legacy, screw + dry cooler, centrifugal + tower, air-cooled
  screw), each without or with free cooling; air-cooled + free cooling
  also with 3 ATES well pairs and a 10 MW backup chiller (the pick's cooling)

That is 3 x 5 x 2 x 2 x 10 = 600 year runs.

    $env:PYTHONPATH="src"
    python simulator_examples/run_full_screen.py --year 2025 `
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt

The KNMI file comes with the weather rerun (PR #17); --epw takes an EnergyPlus file instead.

Writes simulator_examples/outputs/full_screen/: results.csv, summary.md and
fig_full_screen.png (LCOE against CO2, coloured by cooling option).
"""

import argparse
import itertools
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from gemini_agent.tools import make_design
from gemini_design.annual import run_year
from gemini_design.challenge import add_inputs_argument, default_inputs_dir, load_demand
from gemini_design.climate import read_epw_daily, read_knmi_daily, with_climate

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "full_screen"
DEPTHS_M = (2500, 2800, 3100, 3200, 3400, 4000)
# (label, request fields)
COOLING = [
    ("absorption", {"cooling": "absorption"}),
    ("legacy electric", {"cooling": "electric"}),
    ("screw + dry cooler", {"cooling": "electric", "chiller_type": "screw_dry_cooler"}),
    ("centrifugal + tower", {"cooling": "electric", "chiller_type": "centrifugal_tower"}),
    ("air-cooled screw", {"cooling": "electric", "chiller_type": "air_cooled_screw"}),
    ("legacy + free cooling", {"cooling": "electric", "free_cooling": True}),
    (
        "screw + free cooling",
        {"cooling": "electric", "chiller_type": "screw_dry_cooler", "free_cooling": True},
    ),
    (
        "tower + free cooling",
        {"cooling": "electric", "chiller_type": "centrifugal_tower", "free_cooling": True},
    ),
    (
        "air-cooled + free cooling",
        {"cooling": "electric", "chiller_type": "air_cooled_screw", "free_cooling": True},
    ),
    (
        "air-cooled + free cooling + ATES x3",
        {
            "cooling": "electric",
            "chiller_type": "air_cooled_screw",
            "free_cooling": True,
            "ates_doublets": 3,
            "chiller_capacity_mw": 10.0,
        },
    ),
]


def requests():
    """Every design request of the grid, with its cooling label."""
    out = []
    for n, depth, upgrade, chp, (label, cool) in itertools.product(
        (1, 2, 3), DEPTHS_M, ("boiler", "heat_pump"), (False, True), COOLING
    ):
        req = {"n_doublets": n, "depth_m": depth, "upgrade": upgrade, "chp": chp, **cool}
        out.append((label, req))
    return out


def _run(args):
    label, req, climate = args
    peaks = float(climate["heating_mw"].max()), float(climate["cooling_mw"].max())
    design = make_design(req, *peaks)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, s = run_year(design, climate)
    e, k, econ = s["energy_mwh"], s["kpi"], s["economics"]
    return {
        "design": s["design"]["name"],
        "n_doublets": req["n_doublets"],
        "depth_m": req["depth_m"],
        "upgrade": req["upgrade"],
        "chp": req["chp"],
        "cooling_option": label,
        "meets_all_hard_rules": s["all_hard_constraints_met"],
        "failed_rules": ";".join(n for n, ok in s["checks"].items() if not ok),
        "unmet_heating_mwh": round(e["unmet_heating"], 1),
        "unmet_cooling_mwh": round(e["unmet_cooling"], 1),
        "purchased_gas_mwh": round(e["purchased_gas_fuel"]),
        "electricity_mwh": round(e["electricity"]),
        "co2_t_per_year": round(k["co2_t_per_year"]),
        "capex_meur": round(econ["capex_eur"]["total"] / 1e6, 2),
        "lcoe_eur_per_mwh": round(econ["lcoe_eur_per_mwh"], 2),
    }


def plot(df, path):
    """LCOE against CO2, one colour per cooling family, hollow = breaks a rule."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    families = {
        "absorption": ("absorption", "#8E44AD"),
        "chiller only": (None, "#8A93A3"),
        "chiller + free cooling": ("free cooling", "#2E86C1"),
        "free cooling + ATES": ("ATES", "#C2501E"),
    }

    def family(label):
        if label == "absorption":
            return "absorption"
        if "ATES" in label:
            return "free cooling + ATES"
        if "free cooling" in label:
            return "chiller + free cooling"
        return "chiller only"

    markers = {1: "o", 2: "s", 3: "^"}
    fig, ax = plt.subplots(figsize=(8, 5), dpi=200)
    df = df.assign(family=df["cooling_option"].map(family))
    for fam, (_, colour) in families.items():
        for n, m in markers.items():
            sub = df[(df["family"] == fam) & (df["n_doublets"] == n)]
            ok, bad = sub[sub["meets_all_hard_rules"]], sub[~sub["meets_all_hard_rules"]]
            ax.scatter(
                ok["co2_t_per_year"] / 1000,
                ok["lcoe_eur_per_mwh"],
                s=14,
                marker=m,
                color=colour,
                alpha=0.8,
                linewidths=0,
            )
            ax.scatter(
                bad["co2_t_per_year"] / 1000,
                bad["lcoe_eur_per_mwh"],
                s=14,
                marker=m,
                facecolors="none",
                edgecolors=colour,
                alpha=0.6,
                linewidths=0.8,
            )
    pick = df[df["design"] == "2D-3200m-boiler-electric-chp-aircooled-fc-ates3"]
    if len(pick):
        p = pick.iloc[0]
        ax.scatter(
            [p["co2_t_per_year"] / 1000],
            [p["lcoe_eur_per_mwh"]],
            s=160,
            facecolors="none",
            edgecolors="#14213D",
            linewidths=1.6,
            zorder=5,
        )
        ax.annotate(
            "pick: 2D · 3.2 km · CHP\nair-cooled + free cooling + ATES",
            (p["co2_t_per_year"] / 1000, p["lcoe_eur_per_mwh"]),
            xytext=(p["co2_t_per_year"] / 1000 + 1.5, p["lcoe_eur_per_mwh"] - 1.5),
            fontsize=8,
            arrowprops={"arrowstyle": "->", "lw": 0.8},
        )
    for fam, (_, colour) in families.items():
        ax.scatter([], [], color=colour, s=20, label=fam)
    for n, m in markers.items():
        ax.scatter(
            [], [], color="#5A6474", marker=m, s=20, label=f"{n} doublet" + ("s" if n > 1 else "")
        )
    ax.scatter([], [], facecolors="none", edgecolors="#5A6474", s=20, label="breaks a rule")
    ax.set_xlabel("CO₂, kt/yr")
    ax.set_ylabel("LCOE, €/MWh delivered")
    ax.set_ylim(top=min(70, df["lcoe_eur_per_mwh"].max() + 1))
    ax.legend(fontsize=7, frameon=False, loc="upper right", ncol=2)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)


def summarise(df, source):
    """Markdown summary: counts, the best designs and the best per cooling option."""
    ok = df[df["meets_all_hard_rules"]].sort_values("lcoe_eur_per_mwh")
    lines = [
        f"# Full design screen, weather: {source}",
        "",
        "Basis: each doublet down 35 days at its own time (staggered, lowest-load windows), "
        "corrosion "
        "mitigation priced, ledger prices (CO2 at the ledger price is inside the LCOE).",
        "",
        f"{len(df)} designs run, {len(ok)} meet every hard rule.",
        "",
        "## Failures by cooling option",
        "",
        "| cooling option | run | fail |",
        "|---|---|---|",
    ]
    for label, g in df.groupby("cooling_option", sort=False):
        lines.append(f"| {label} | {len(g)} | {int((~g['meets_all_hard_rules']).sum())} |")
    cols = ["design", "lcoe_eur_per_mwh", "co2_t_per_year", "capex_meur"]
    lines += [
        "",
        "## 15 cheapest that meet every rule",
        "",
        "| " + " | ".join(cols) + " |",
        "|" + "---|" * len(cols),
    ]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for _, r in ok.head(15).iterrows()]
    lines += [
        "",
        "## Cheapest per cooling option and doublet count (rules met)",
        "",
        "| cooling option | doublets | design | lcoe_eur_per_mwh | co2_t_per_year |",
        "|---|---|---|---|---|",
    ]
    for (label, n), g in ok.groupby(["cooling_option", "n_doublets"], sort=False):
        r = g.iloc[0]
        lines.append(
            f"| {label} | {n} | {r['design']} | {r['lcoe_eur_per_mwh']} | "
            f"{r['co2_t_per_year']} |"
        )
    lowest_co2 = ok.sort_values("co2_t_per_year").head(10)
    lines += [
        "",
        "## 10 lowest CO2 that meet every rule",
        "",
        "| " + " | ".join(cols) + " |",
        "|" + "---|" * len(cols),
    ]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for _, r in lowest_co2.iterrows()]
    return "\n".join(lines) + "\n"


def main():
    """Run the grid and write the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--epw", help="EnergyPlus weather file")
    src.add_argument("--knmi", help="KNMI etmgeg daily file")
    parser.add_argument("--year", type=int, default=2025, help="year to take from a KNMI file")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="run only the first N (testing)")
    add_inputs_argument(parser)
    args = parser.parse_args()
    weather = read_epw_daily(args.epw) if args.epw else read_knmi_daily(args.knmi, args.year)
    source = Path(args.epw or args.knmi).name + ("" if args.epw else f" ({args.year})")
    climate = with_climate(load_demand(args.inputs), weather, "max")
    jobs = [(label, req, climate) for label, req in requests()]
    if args.limit:
        jobs = jobs[: args.limit]
    with ProcessPoolExecutor(args.workers) as pool:
        rows = list(pool.map(_run, jobs, chunksize=4))
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "results.csv", index=False)
    (OUT / "summary.md").write_text(summarise(df, source), encoding="utf-8")
    plot(df, OUT / "fig_full_screen.png")
    print((OUT / "summary.md").read_text(encoding="utf-8")[:3000])


if __name__ == "__main__":
    main()
