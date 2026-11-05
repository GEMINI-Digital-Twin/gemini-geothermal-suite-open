"""Compare the plain daily dispatch with doublet operating memory.

Runs the recommended design (2D-3100m boiler + 12 MW electric chiller + CHP)
for a year twice: as independent steady days (the original model) and with
:class:`gemini_design.operations.OperatingRules` (minimum run and stop times,
a cost per ESP start, time-dependent wellbore heat loss). Optionally reruns
the 96-design screen both ways.

Writes to ``simulator_examples/outputs/operations/``: ``comparison.json``,
``daily_base.csv``, ``daily_operations.csv``, ``operations_year.png`` and,
with ``--screen``, ``screen_base.csv`` and ``screen_operations.csv``.

Run with:
    $env:PYTHONPATH="src"; python simulator_examples/run_operations_study.py [--screen]
"""

import json
import sys
from pathlib import Path

from gemini_design.annual import run_year
from gemini_design.challenge import default_inputs_dir, load_demand
from gemini_design.operations import OperatingRules
from gemini_design.plant import Design
from gemini_design.screening import candidate_designs, chp_size_mw_el, screen

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUTPUTS = Path(__file__).parent / "outputs" / "operations"

PICK = Design(
    n_doublets=2,
    depth_m=3100.0,
    upgrade="boiler",
    cooling="electric",
    boiler_capacity_mw=30.0,
    chiller_capacity_mw=12.0,
    chp_capacity_mw_el=chp_size_mw_el(2),
)


def _headline(daily, summary):
    e, k = summary["energy_mwh"], summary["kpi"]
    changes = int((daily["n_active"].diff().fillna(0) != 0).sum())
    return {
        "lcoe_eur_per_mwh": summary["economics"]["lcoe_eur_per_mwh"],
        "co2_t_per_year": k["co2_t_per_year"],
        "geothermal_heat_mwh": e["geothermal_heat"],
        "boiler_heat_mwh": e["boiler_heat"],
        "purchased_gas_mwh": e["purchased_gas_fuel"],
        "changes_in_running_doublets": changes,
        "doublet_starts": summary.get("operations", {}).get("doublet_starts"),
        "wellhead_temperature_c": [
            float(daily["wellhead_temperature_c"].min()),
            float(daily["wellhead_temperature_c"].max()),
        ],
        "esp_setting_depth_m": k["esp_setting_depth_m"],
        "all_hard_constraints_met": summary["all_hard_constraints_met"],
    }


def plot(base, ops, path):
    """Plot running doublets and wellhead temperature over the year, both models."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)
    days = range(len(base))
    ax1.step(days, base["n_active"], where="mid", color="#9aa0a6", label="independent days")
    ax1.step(days, ops["n_active"], where="mid", color="#1a73e8", label="with operating rules")
    ax1.set_ylabel("running doublets")
    ax1.set_yticks([0, 1, 2])
    ax1.legend(loc="lower left", frameon=False)
    ax2.plot(days, base["wellhead_temperature_c"], color="#9aa0a6", lw=1)
    ax2.plot(days, ops["wellhead_temperature_c"], color="#1a73e8", lw=1)
    for d in ops.index[ops["doublet_starts"] > 0]:
        ax2.axvline(d, color="#d93025", lw=0.8, ls=":")
    ax2.set_ylabel("wellhead temperature (°C)")
    ax2.set_xlabel("day of 2027")
    ax2.text(
        0.99,
        0.05,
        "dotted: doublet start (warm-up)",
        transform=ax2.transAxes,
        ha="right",
        color="#d93025",
        fontsize=8,
    )
    for ax in (ax1, ax2):
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)


def main(run_screen=False):
    """Run the comparison and write the outputs."""
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    demand = load_demand(INPUTS)
    rules = OperatingRules()
    base, base_summary = run_year(PICK, demand)
    ops, ops_summary = run_year(PICK, demand, operations=rules)
    base.to_csv(OUTPUTS / "daily_base.csv", index=False)
    ops.to_csv(OUTPUTS / "daily_operations.csv", index=False)
    result = {
        "design": PICK.name,
        "rules": rules.as_dict(),
        "independent_days": _headline(base, base_summary),
        "with_operating_rules": _headline(ops, ops_summary),
        "operations": ops_summary["operations"],
    }
    (OUTPUTS / "comparison.json").write_text(json.dumps(result, indent=2, default=float))
    plot(base, ops, OUTPUTS / "operations_year.png")
    print(json.dumps(result, indent=2, default=float))
    if run_screen:
        designs = candidate_designs(chiller_margin=1.2)
        for name, ops_rules in (("base", None), ("operations", rules)):
            table, _ = screen(designs, demand, operations=ops_rules)
            table.to_csv(OUTPUTS / f"screen_{name}.csv", index=False)
            print(name, table.head(5)[["name", "lcoe_eur_per_mwh", "co2_t_per_year"]])


if __name__ == "__main__":
    main(run_screen="--screen" in sys.argv)
