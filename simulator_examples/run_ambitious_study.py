"""Would a more ambitious design beat the pick? Every option, 365 days, through the gate.

Runs the whole option space against the pick (2D-3100m boiler + 12 MW electric
chiller + CHP) through the agent's ToolBox, so each run passes the same physics
gate (hard rules, energy balance, sanity bounds, GEMINI Solver cross-check) and
gets a run id:

* every combination of 1-3 doublets, 2.5-4.5 km, boiler or heat pump,
  electric or absorption cooling, with and without CHP (12 MW chiller);
* one doublet plus a seasonal heat store instead of the second doublet, over
  store size and rating, and the pick plus a store. GEMINI has no storage
  model: the study first registers the agent's own ``thermal_storage`` model
  (the code the scripted agent writes in scenario 09) through ``write_model``,
  so it runs only if that model passes its tests.

Each run is compared with the pick (``compare_runs``). The study writes the
Pareto front of cost and CO2, any design that beats the pick on both, and the
storage price at which each store design breaks even with the pick.

    $env:PYTHONPATH="src"
    python simulator_examples/run_ambitious_study.py            # about 10 min on 4 cores
    python simulator_examples/run_ambitious_study.py --quick    # a few designs, for a check

Writes simulator_examples/outputs/ambitious_study/ (results.csv, results.md,
ambitious_study.png, the run ledger and the generated model).
"""

import argparse
import itertools
import shutil
from pathlib import Path

import pandas as pd

from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.scenarios import PICK_CHP, THERMAL_STORAGE_CODE, THERMAL_STORAGE_TESTS
from gemini_agent.tools import ToolBox
from gemini_design.challenge import ASSUMPTIONS, default_inputs_dir, load_demand
from gemini_design.economics import capital_recovery_factor

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "ambitious_study"
DEPTHS_M = (2500, 3100, 3400, 3700, 4000, 4500)


def design_grid(quick=False):
    """(family, run_design arguments) for every conventional option."""
    if quick:
        return [
            ("conventional", {**PICK_CHP, "depth_m": 3400}),
            ("conventional", {**PICK_CHP, "n_doublets": 3}),
        ]
    out = []
    for n, depth, upgrade, cooling, chp in itertools.product(
        (1, 2, 3), DEPTHS_M, ("boiler", "heat_pump"), ("electric", "absorption"), (False, True)
    ):
        args = {
            "n_doublets": n,
            "depth_m": depth,
            "upgrade": upgrade,
            "cooling": cooling,
            "chp": chp,
            "chiller_capacity_mw": 12.0,
        }
        if args != PICK_CHP:
            out.append(("conventional", args))
    return out


def storage_grid(quick=False):
    """(family, run_design arguments) for the seasonal-storage options."""
    if quick:
        return [("storage", {**PICK_CHP, "n_doublets": 1, "storage_mwh": 25000, "storage_mw": 12})]
    out = []
    for depth, mwh, mw in itertools.product(
        (3100, 3400), (10000, 15000, 20000, 25000, 30000), (10, 12, 15)
    ):
        out.append(
            (
                "storage",
                {
                    **PICK_CHP,
                    "n_doublets": 1,
                    "depth_m": depth,
                    "storage_mwh": mwh,
                    "storage_mw": mw,
                },
            )
        )
    for mwh in (5000, 10000):
        out.append(("storage", {**PICK_CHP, "storage_mwh": mwh, "storage_mw": 10}))
    return out


def break_even_storage_cost(tools, run_id, base_lcoe):
    """Storage price (EUR per MWh of capacity) at which a store design costs what the pick does.

    The price changes only CAPEX (not dispatch), so LCOE is linear in it.
    """
    summary = tools.ledger.summary(run_id)
    design, econ = summary["design"], summary["economics"]
    if not design.get("storage_mwh") or not summary["energy_mwh"]["storage_discharge"]:
        return None  # no store, or a store the plant never needs
    a = ASSUMPTIONS
    annuity = (
        capital_recovery_factor(a["discount_rate"], a["lifetime_years"]) + a["fixed_om_fraction"]
    )
    e = summary["energy_mwh"]
    delivered = e["heating_delivered"] + e["cooling_delivered"]
    slope = design["storage_mwh"] * annuity / delivered  # EUR/MWh of energy per EUR/MWh of store
    return a["storage_cost_eur_per_mwh"] + (base_lcoe - econ["lcoe_eur_per_mwh"]) / slope


def pareto_front(rows):
    """Feasible rows not beaten on both LCOE and CO2 by another feasible row."""
    ok = [r for r in rows if r["meets_all_hard_rules"]]
    front = []
    for r in ok:
        if not any(
            o["lcoe_eur_per_mwh"] <= r["lcoe_eur_per_mwh"]
            and o["co2_t_per_year"] <= r["co2_t_per_year"]
            and (o["lcoe_eur_per_mwh"], o["co2_t_per_year"])
            != (r["lcoe_eur_per_mwh"], r["co2_t_per_year"])
            for o in ok
        ):
            front.append(r)
    return sorted(front, key=lambda r: r["lcoe_eur_per_mwh"])


def run(quick=False, workers=4):
    """Run the study; return the result table."""
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    demand = load_demand(INPUTS)
    tools = ToolBox(demand, RunLedger(OUT), ProjectNotes(OUT), OUT, workers=workers)
    model = tools.call(
        "write_model",
        {
            "name": "thermal_storage",
            "register_as": "thermal_storage",
            "code": THERMAL_STORAGE_CODE,
            "test_code": THERMAL_STORAGE_TESTS,
        },
    )
    if not model.get("ok"):
        raise SystemExit(f"storage model rejected: {model}")
    print(f"storage model registered: {model['class']} ({model['pytest']})")

    base = tools.call("run_design", dict(PICK_CHP))
    print(f"pick {base['run_id']}: {base['lcoe_eur_per_mwh']} EUR/MWh, {base['co2_t_per_year']} t")
    rows = [{"family": "pick", "run_id": base["run_id"], **base, "pareto": "baseline"}]
    jobs = design_grid(quick) + storage_grid(quick)
    for i, (family, args) in enumerate(jobs, 1):
        r = tools.call("run_design", dict(args))
        if "error" in r:
            print(f"[{i}/{len(jobs)}] {args}: {r['error']}")
            continue
        row = {"family": family, **r, "storage_mw": args.get("storage_mw", 0)}
        if r["physics_gate"] == "pass":
            cmp = tools.call(
                "compare_runs", {"run_id": r["run_id"], "baseline_run_id": base["run_id"]}
            )
            row["pareto"] = cmp["pareto"]
            row["lcoe_change_pct"] = cmp["lcoe_change_pct"]
            row["co2_change_pct"] = cmp["co2_change_pct"]
        row["break_even_storage_eur_per_mwh"] = break_even_storage_cost(
            tools, r["run_id"], base["lcoe_eur_per_mwh"]
        )
        rows.append(row)
        print(
            f"[{i}/{len(jobs)}] {r['run_id']} {r['design']}: {r['lcoe_eur_per_mwh']} EUR/MWh, "
            f"{r['co2_t_per_year']} t, gate {r['physics_gate']}, {row.get('pareto', '')}"
        )
    table = pd.DataFrame(rows).drop(columns=["failed_rules"], errors="ignore")
    table.to_csv(OUT / "results.csv", index=False)
    write_markdown(table, rows, base)
    plot(table, base)
    return table


def _line(r):
    return (
        f"| {r['design']} | {r['run_id']} | {r['lcoe_eur_per_mwh']:.2f} | "
        f"{r['co2_t_per_year']:,.0f} | {r['geothermal_share_of_heat_pct']:.1f} | "
        f"{r['purchased_gas_mwh']:,.0f} | {r['capex_meur']:.1f} | {r.get('pareto', '')} |"
    )


def write_markdown(table, rows, base):
    """results.md: verdict, beaters, Pareto front, cheapest per family, storage break-even."""
    valid = [r for r in rows if r.get("physics_gate") == "pass"]
    feasible = [r for r in valid if r["meets_all_hard_rules"]]
    beats = [r for r in feasible if str(r.get("pareto", "")).startswith("dominates")]
    cheaper = [
        r for r in feasible if r["lcoe_eur_per_mwh"] < base["lcoe_eur_per_mwh"] and r is not rows[0]
    ]
    head = (
        "| Design | Run | LCOE (EUR/MWh) | CO2 (t/yr) | Geothermal (%) | Purchased gas (MWh) "
        "| CAPEX (MEUR) | vs pick |\n|---|---|---|---|---|---|---|---|"
    )
    lines = [
        "# More ambitious designs vs the pick (365 days each, physics-gated)",
        "",
        f"Pick: {base['design']} [{base['run_id']}], {base['lcoe_eur_per_mwh']:.2f} EUR/MWh, "
        f"{base['co2_t_per_year']:,.0f} t CO2/yr. {len(rows) - 1} other designs run: "
        f"{len(valid) - 1} passed the physics gate and {len(feasible) - 1} of those meet every "
        "hard rule.",
        "",
        "## Verdict",
        "",
        (
            f"{len(beats)} design(s) beat the pick on both cost and CO2."
            if beats
            else "No design beats the pick on both cost and CO2."
        )
        + f" {len(cheaper)} feasible design(s) are cheaper.",
        "",
    ]
    if beats:
        lines += ["## Designs that beat the pick", "", head]
        lines += [_line(r) for r in sorted(beats, key=lambda r: r["lcoe_eur_per_mwh"])]
        lines.append("")
    lines += ["## Pareto front (cost vs CO2)", "", head]
    lines += [_line(r) for r in pareto_front(feasible)]
    lines += ["", "## Cheapest feasible design per family", "", head]
    df = pd.DataFrame(feasible)
    df["family_key"] = (
        df["family"]
        + " "
        + df["design"].str.extract(r"^(\dD)")[0]
        + " "
        + df["design"].str.contains("heat_pump").map({True: "heat pump", False: "boiler"})
        + " "
        + df["design"].str.contains("absorption").map({True: "absorption", False: "electric"})
    )
    for _, r in df.sort_values("lcoe_eur_per_mwh").groupby("family_key").head(1).iterrows():
        lines.append(_line(r))
    store = table[table["break_even_storage_eur_per_mwh"].notna()]
    if not store.empty:
        lines += [
            "",
            "## Seasonal storage: price at which each store design matches the pick",
            "",
            "Assumed storage price: "
            f"{ASSUMPTIONS['storage_cost_eur_per_mwh']:.0f} EUR per MWh of capacity "
            "(large pit stores, 20-40 EUR/m3). A 25 GWh store holds about 430,000 m3 of water "
            "at 50 K, about twice the largest pit store built.",
            "",
            "| Design | Rating (MW) | Run | LCOE (EUR/MWh) | CO2 (t/yr) | Purchased gas (MWh) "
            "| From store (MWh) | Break-even price (EUR/MWh cap.) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for _, r in store.sort_values("lcoe_eur_per_mwh").iterrows():
            lines.append(
                f"| {r['design']} | {r['storage_mw']:g} | {r['run_id']} | "
                f"{r['lcoe_eur_per_mwh']:.2f} | "
                f"{r['co2_t_per_year']:,.0f} | {r['purchased_gas_mwh']:,.0f} | "
                f"{r.get('storage_discharge_mwh', 0) or 0:,.0f} | "
                f"{r['break_even_storage_eur_per_mwh']:.0f} |"
            )
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot(table, base):
    """Cost vs CO2 of every feasible design, the pick highlighted."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ok = table[(table["physics_gate"] == "pass") & table["meets_all_hard_rules"]]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    styles = {
        "1D": ("#7a8ca3", "o"),
        "2D": ("#2b6cb0", "o"),
        "3D": ("#9c4221", "o"),
    }
    conv = ok[ok["family"] == "conventional"]
    for key, (color, marker) in styles.items():
        sel = conv[conv["design"].str.startswith(key)]
        ax.scatter(
            sel["lcoe_eur_per_mwh"],
            sel["co2_t_per_year"] / 1e3,
            s=18,
            c=color,
            marker=marker,
            label=f"{key[0]} doublet{'s' if key != '1D' else ''}",
            alpha=0.75,
        )
    sto = ok[ok["family"] == "storage"]
    if not sto.empty:
        ax.scatter(
            sto["lcoe_eur_per_mwh"],
            sto["co2_t_per_year"] / 1e3,
            s=26,
            c="#2f855a",
            marker="s",
            label="seasonal store (agent-written model)",
        )
    ax.scatter(
        [base["lcoe_eur_per_mwh"]],
        [base["co2_t_per_year"] / 1e3],
        s=140,
        facecolors="none",
        edgecolors="black",
        linewidths=1.8,
        label="pick",
        zorder=5,
    )
    ax.axvline(base["lcoe_eur_per_mwh"], color="black", lw=0.6, ls=":")
    ax.axhline(base["co2_t_per_year"] / 1e3, color="black", lw=0.6, ls=":")
    ax.set_xlabel("Levelised cost of heat + cooling (EUR/MWh)")
    ax.set_ylabel("CO2 (kt per year)")
    ax.set_xlim(right=min(ok["lcoe_eur_per_mwh"].max(), 60) + 1)
    ax.set_title(
        "Every design run for 365 days: the lower-left quadrant would beat the pick", fontsize=10
    )
    ax.legend(fontsize=8, frameon=False, loc="upper right", bbox_to_anchor=(1.0, 0.72))
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "ambitious_study.png", dpi=180)
    plt.close(fig)


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="a few designs only")
    args = parser.parse_args(argv)
    run(quick=args.quick)
    print(f"written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
