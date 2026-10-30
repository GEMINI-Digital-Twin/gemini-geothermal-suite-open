"""Uncertainty and techno-economics study of the leading GeoHackathon designs.

Runs a shared Latin-hypercube Monte Carlo (subsurface, demand, prices,
costs) over the shortlisted designs, a P10/P90 tornado on the pick, a
chiller sizing-margin sweep, and writes CSVs and report figures to
``simulator_examples/outputs/uncertainty/``.

Run with:
    $env:PYTHONPATH="src"; python simulator_examples/run_uncertainty_study.py --samples 400
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from gemini_design.challenge import load_demand
from gemini_uncertainty import plots
from gemini_uncertainty.parameters import PARAMETERS, describe_parameters
from gemini_uncertainty.study import (
    base_case,
    compare,
    design_from_name,
    monte_carlo,
    rank_correlations,
    summarise,
    tornado,
    with_capacity,
)

INPUTS = Path(__file__).parent / "hackathon_inputs"
OUTPUTS = Path(__file__).parent / "outputs" / "uncertainty"
PICK = "2D-3100m-boiler-electric"
SHORTLIST = (
    PICK,
    "1D-2800m-boiler-electric",
    "2D-3100m-boiler-absorption",
    "2D-3100m-boiler-electric-chp",
    "2D-2800m-boiler-electric",
    "2D-3100m-heat_pump-electric",
)
CHILLER_SWEEP_MW = (10.0, 11.0, 12.0, 13.0)


def main(n_samples=400, seed=2027, workers=None, out=OUTPUTS):
    """Run the full study and write results and figures."""
    out.mkdir(parents=True, exist_ok=True)
    demand = load_demand(INPUTS)
    designs = [design_from_name(n) for n in SHORTLIST]
    names = [d.name for d in designs]
    describe_parameters().to_csv(out / "parameters.csv", index=False)

    base = base_case(designs, demand, workers=workers)
    base.to_csv(out / "base_case.csv", index=False)

    # Robust sizing: every shortlisted design again with a 12 MW chiller (+20%),
    # plus an 11 and 13 MW sweep on the pick
    pick = designs[0]
    robust = [with_capacity(d, 12.0) for d in designs]
    sweep = [with_capacity(pick, c) for c in CHILLER_SWEEP_MW if c not in (10.0, 12.0)]
    all_designs = designs + robust + sweep
    results, samples = monte_carlo(all_designs, demand, n_samples, seed, workers=workers)
    results.to_csv(out / "mc_results.csv", index=False)
    samples.to_csv(out / "mc_samples.csv")
    summary = summarise(results)
    summary.to_csv(out / "mc_summary.csv", index=False)

    robust_names = [d.name for d in robust]
    comparisons = pd.DataFrame(
        [compare(results, names[0], other) for other in names[1:]]
        + [compare(results, robust_names[0], other) for other in robust_names[1:]]
    )
    comparisons.to_csv(out / "paired_comparisons.csv", index=False)

    tornados = {}
    for d in (robust[0], robust[names.index("2D-3100m-boiler-electric-chp")]):
        tornados[d.name] = tornado(d, demand, workers=workers)
        tornados[d.name].to_csv(out / f"tornado_{d.name}.csv", index=False)
    robust_pick = robust_names[0]
    tor_rob = tornados[robust_pick]
    corr = rank_correlations(results[results["design"].isin(robust_names)])
    corr.to_csv(out / "rank_correlation_lcoe.csv")

    labels = {p.name: p.label for p in PARAMETERS}
    plots.lcoe_ecdf(results, robust_names, out / "fig_lcoe_ecdf.png")
    scatter = [robust_pick, robust_names[1], robust_names[2]]
    plots.cost_co2_scatter(results, scatter, out / "fig_cost_vs_co2.png")
    for name, table in tornados.items():
        tag = "chp" if "chp" in name else "pick"
        plots.tornado_chart(table, name, out / f"fig_tornado_lcoe_{tag}.png")
        plots.tornado_chart(
            table, name, out / f"fig_tornado_co2_{tag}.png", metric="co2", unit="t/yr"
        )
    plots.probability_bars(summary, out / "fig_p_demand_met.png")
    plots.correlation_heatmap(corr, labels, out / "fig_rank_correlation.png")
    sweep_names = {10.0: PICK, **{c: with_capacity(pick, c).name for c in CHILLER_SWEEP_MW[1:]}}
    sweep_p = [
        float(summary.loc[summary["design"] == sweep_names[c], "p_demand_met"].iloc[0])
        for c in CHILLER_SWEEP_MW
    ]
    plots.margin_curve(CHILLER_SWEEP_MW, sweep_p, out / "fig_chiller_margin.png")

    headline = {
        "n_samples": n_samples,
        "seed": seed,
        "base_case": base[["design", "demand_met", "lcoe_eur_per_mwh", "co2_t_per_year"]]
        .round(3)
        .to_dict("records"),
        "summary": summary.round(4).to_dict("records"),
        "paired_comparisons": comparisons.round(4).to_dict("records"),
        "tornado_top5_pick": tor_rob.head(5)[["parameter", "lcoe_low", "lcoe_high", "lcoe_swing"]]
        .round(3)
        .to_dict("records"),
        "chiller_sweep": dict(zip(CHILLER_SWEEP_MW, sweep_p)),
    }
    (out / "headline.json").write_text(json.dumps(headline, indent=2, default=str))
    with pd.option_context("display.width", 220, "display.max_columns", 30):
        print(summary.round(2).to_string(index=False))
        print(comparisons.round(3).to_string(index=False))
        print(tor_rob.head(8)[["parameter", "lcoe_low", "lcoe_high", "lcoe_swing"]].round(2))
    return headline


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=400)
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    main(args.samples, args.seed, args.workers)
