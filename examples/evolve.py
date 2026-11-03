"""Evolve: the best structures of the hackathon superstructure on LCTS and CO2.

One plant file states the six candidate plants of the hackathon at once: the heat pump is
optional and each cooling unit is on or off. ``gm.study.evolve`` searches the structures and the
ranges of the plant together by a genetic algorithm (NSGA-II) and returns the designs no other
beats on both LCTS and CO2. The budget is small, so the front is a first look, not the optimum.

Shows ``plant.structures``, ``gm.study.size``, ``gm.study.evolve`` and its ``front`` and ``best``.

Run with ``python examples/evolve.py``.
"""

from pathlib import Path

import gemini as gm

EXAMPLES = Path(__file__).resolve().parent
CASE = EXAMPLES / "hackathon_2026/case.json"
PLANT = EXAMPLES / "hackathon_superstructure/plants/HackathonSuperstructure.json"
POPULATION = 16
EVALUATIONS = 64
SEED = 0


def label(structure):
    """Return a structure as one line: the optional modules and choices that are on."""
    return ", ".join(
        name if value is True else f"{name}={value}"
        for name, value in structure.items()
        if value is not False
    )


def show(design):
    """Print the structure, LCTS and CO2 of one design, and why it fails when it does."""
    lcts = design["metrics"]["lcts"].to("EUR/MWh").value
    co2 = design["metrics"]["co2"].to("kt").value
    verdict = "feasible" if design["feasible"] else f"infeasible: {design['reason']}"
    print(f"  {label(design['structure'])}: {lcts:.2f} EUR/MWh, {co2:.2f} kt CO2, {verdict}")


def main():
    """Size the superstructure, evolve it on LCTS and CO2 and print the front and the best."""
    case = gm.Case.from_json(CASE)
    plant = gm.study.size(gm.Plant.from_json(PLANT), case)
    print(f"Valid structures: {len(plant.structures())}")
    found = gm.study.evolve(
        plant,
        case,
        ["lcts", "co2"],
        EVALUATIONS,
        SEED,
        population=POPULATION,
        polish=0,
    )
    print(f"Simulations: {found['evaluations']}, structures refused: {found['invalid']}")
    print("Front on LCTS and CO2:")
    for design in found["front"]:
        show(design)
    print("Best on LCTS:")
    show(found["best"])


if __name__ == "__main__":
    main()
