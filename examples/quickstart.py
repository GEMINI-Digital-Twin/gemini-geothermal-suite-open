"""Quickstart: a case and a plant from JSON, one simulation, its requirements and its report.

Shows ``gm.Case.from_json``, ``gm.Plant.from_json``, ``gm.check``, ``gm.simulate``,
``gm.evaluate.requirements`` and ``gm.evaluate.report`` on the shallow district sample.

Run with ``python examples/quickstart.py``.
"""

from pathlib import Path

import gemini as gm

SAMPLE = Path(__file__).resolve().parents[1] / "inputs/examples/shallow_district"


def show(label, quantity, unit):
    """Print one quantity in ``unit``."""
    value = quantity.to(unit)
    print(f"{label:<18} {value.value:10.2f} {value.unit}")


def main():
    """Run the sample for its three weeks and print what it delivered and what it costs."""
    case = gm.Case.from_json(SAMPLE / "case.json")
    plant = gm.Plant.from_json(SAMPLE / "plants/HeatingHeatPumpCoolingPlant.json")
    issues = gm.check(plant, case)
    print("Check: ready" if not issues else f"Check: {issues}")
    results = gm.simulate(plant, case)
    for check in gm.evaluate.requirements(plant, case, results):
        print(f"{check['name']:<45} {'ok' if check['passed'] else 'VIOLATED'}")
    report = gm.evaluate.report(plant, case, results)
    show("Heat delivered", report["heat_delivered"], "MWh")
    show("Cold delivered", report["cold_delivered"], "MWh")
    show("LCTS", report["lcts"], "EUR/MWh")
    show("CO2", report["co2"], "t")


if __name__ == "__main__":
    main()
