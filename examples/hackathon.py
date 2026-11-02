"""The hackathon flow on the 2027 case: load the studies, run them, print the comparison.

``study.json`` says what is run: every stored candidate, the hand design included, is sized and
searched on LCTS over the ranges its plant file states, simulated and reported. The candidates are
ranked twice, because two readings of the brief are possible. ``study_brief.json`` runs the plants
of ``plants_brief/``, which state only what the brief states. ``study.json`` runs the plants of
``plants/``, which add the pump intake limits of standard stages (at most 18.75 % free gas, at
least 5 bar): the brief does not state them, and a gas-handling pump, which has a higher limit, is
not among the candidates. Each table gives the metrics in readable units, the rank by each and the
Pareto front of the feasible designs. The best feasible design of the second ranking is then
sampled over the values the case declares uncertain and moved one value at a time
(``study_sample.json`` and ``study_sensitivity.json``). The trials are searched in ``PROCESSES``
processes (``gm.runtime.settings``); the numbers equal a serial run. It takes about twice as long
as one ranking, a few minutes.

Shows ``gm.Study.from_json``, ``Study.run``, the comparison of its result, ``result.to_json``.

Run with ``python examples/hackathon.py``.
"""

from pathlib import Path

import gemini as gm

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(__file__).resolve().parent / "hackathon_2026"
RUNS = ROOT / "runs/hackathon"
PROCESSES = 8
"""Worker processes of the search: one per doublet count and trial; an assumption, the cores."""
FORMAT = "{:.4g}".format


def table(result):
    """Return ``(case name, frame)`` of the comparison of a study result, one row per plant."""
    (name,) = result.comparison
    frame = result.comparison[name].to_frame()
    frame.index = [run.plant_name for run in result.runs]
    return name, frame


def print_ranking(result):
    """Print the comparison table and the Pareto front of the feasible designs."""
    _, frame = table(result)
    print(frame.to_string(float_format=FORMAT))
    print("Pareto front of the feasible designs:", list(frame.index[frame["pareto"]]))


def print_candidates(result):
    """Print whether each candidate is feasible and why not, with its trials."""
    for run in result.runs:
        reasons = [item["name"] for item in run.verdict["reasons"]]
        trials = len(run.found["history"]) if run.found else 0
        print(f"{run.plant_name}: {trials} trials, feasible {run.verdict['feasible']}, {reasons}")


def print_spread(spread):
    """Print the mean and the 5th to 95th percentile of the metrics of the draws."""
    print(f"Draws of the best design: {len(spread['samples'])}")
    for name, unit in (("lcts", "EUR/MWh"), ("co2", "kt")):
        stats = spread["summary"][name]
        mean, low, high = (stats[key].to(unit).value for key in ("mean", "p5", "p95"))
        print(f"{name:<5} mean {mean:8.2f}  p5 {low:8.2f}  p95 {high:8.2f} {unit}")


def print_best(best, folder):
    """Print the sensitivity and the draws of the best design, each from its study file."""
    given = {best.plant_name: best.plant}
    moved = gm.Study.from_json(folder / "study_sensitivity.json").run(plants=given)
    print(moved.runs[0].found.to_frame().to_string(float_format=FORMAT))
    print_spread(gm.Study.from_json(folder / "study_sample.json").run(plants=given).runs[0].found)


def main(folder=SAMPLE, out=RUNS):
    """Run the brief ranking, then the ranking with the pump limits, and write the records."""
    with gm.runtime.settings(processes=PROCESSES):
        brief = gm.Study.from_json(folder / "study_brief.json").run()
        print("Ranking with the rules of the brief only (no pump intake limits)")
        print_ranking(brief)
        standard = gm.Study.from_json(folder / "study.json").run()
        print("\nRanking with the pump intake limits of standard stages")
        print_candidates(standard)
        print_ranking(standard)
        best = standard.best[table(standard)[0]]
        if best is None:
            print("No candidate is feasible: nothing to sample.")
        else:
            print_best(best, folder)
    brief.to_json(out / "brief")
    standard.to_json(out / "standard")


if __name__ == "__main__":
    main()
