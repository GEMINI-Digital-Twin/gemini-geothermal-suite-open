"""The hackathon flow on the 2027 case: size, minimise, check, report, compare.

Every stored candidate, the hand design included, is sized, searched on LCTS with one list of
variables in ``<role>.<parameter>`` names, simulated and reported. A candidate is feasible when no
step fails and every constraint of the case passes; the table gives each one's reasons, the
variables the plant could not take, the metrics in readable units and the Pareto front of the
feasible designs only. Sizes with the backup policy ``"peak"``. The best design is then sampled
over the values the case declares uncertain. The candidates are searched in ``PROCESSES`` processes
(``gm.runtime.settings``); the numbers equal a serial run. Shows ``gm.study.size``, ``minimize``,
``sensitivity``, ``sample`` and ``gm.evaluate.compare``.

Run with ``python examples/hackathon.py``.
"""

import json
from pathlib import Path

import gemini as gm

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "inputs/examples/hackathon_2026"
EVALUATIONS = 20
"""Simulations of the search for each doublet count: five for each of four variables, the least."""
PROCESSES = 8
"""Worker processes of the search: one per doublet count and trial; an assumption, the cores."""
DRAWS = 5
"""Simulations of the sample of the best design: few, a year of simulation each."""
SEED = 1
"""The seed of the draws: the same seed gives the same draws."""
SEARCH_SEED = 0
"""The seed of the search: the same seed gives the same trials."""


def design(plant, case):
    """Return ``(searched design, search result)``; the sized plant and ``None`` if not searched."""
    sized = gm.study.size(plant, case)
    try:
        found = gm.study.minimize(sized, case, "lcts", EVALUATIONS, SEARCH_SEED)
    except gm.errors.ValidationError as error:
        print(f"  not searched: {error}")
        return sized, None
    return found["best"]["plant"], found


def print_candidate(name, report, found):
    """Print whether a candidate is feasible and why not, with what the search left fixed."""
    entry = gm.evaluate.compare([report], by="lcts")[0]
    reasons = [item["name"] for item in entry.get("reasons", [])]
    trials = len(found["history"]) if found else 0
    print(f"{name}: {trials} trials, feasible {entry['feasible']}, reasons {reasons}")


def study():
    """Search every candidate, print the table, the front and the spread, write the reports."""
    case = gm.Case.from_json(SAMPLE / "case.json")
    found = {}
    for path in sorted((SAMPLE / "plants").glob("*.json")):
        plant, result = design(gm.Plant.from_json(path), case)
        report = gm.evaluate.report(plant, case, gm.simulate(plant, case))
        found[path.stem] = plant, report
        print_candidate(path.stem, report, result)
    ranked = gm.evaluate.compare([report for _, report in found.values()], by=["lcts", "co2"])
    frame = ranked.to_frame()
    frame.index = list(found)
    print(frame.to_string(float_format="{:.4g}".format))
    print("Pareto front of the feasible designs:", list(frame.index[frame["pareto"]]))
    feasible = {name: found[name] for name in frame.index[frame["feasible"]]}
    best, _ = min(feasible.values(), key=lambda item: item[1]["lcts"].si)
    print(
        gm.study.sensitivity(best, case, ["lcts"])
        .to_frame()
        .to_string(float_format="{:.4g}".format)
    )
    spread = gm.study.sample(best, case, ["lcts", "co2"], DRAWS, SEED)
    print(f"Draws of the best design: {len(spread['samples'])}")
    for name, unit in (("lcts", "EUR/MWh"), ("co2", "kt")):
        stats = spread["summary"][name]
        mean, low, high = (stats[key].to(unit).value for key in ("mean", "p5", "p95"))
        print(f"{name:<5} mean {mean:8.2f}  p5 {low:8.2f}  p95 {high:8.2f} {unit}")
    (ROOT / ".tmp").mkdir(exist_ok=True)
    for name, (_, report) in found.items():
        (ROOT / ".tmp" / f"{name}.json").write_text(json.dumps(report.to_dict(), indent=2))


def main():
    """Run the study with the trials spread over ``PROCESSES`` processes."""
    with gm.runtime.settings(processes=PROCESSES):
        study()


if __name__ == "__main__":
    main()
