"""A plant built from its class: what it needs, fill it, size it, run it, see why steps failed.

Starts from the bare class ``HeatingHeatPumpCoolingPlant`` and asks ``check`` what it
still needs. The design values of the shallow district sample stand in for the user's own
decisions; the sizes that ``size`` computes from the case are left out. ``size`` returns the plant
with notes on what it sized, what it left and what the sized design breaks. The plant then runs,
and ``failures`` groups the steps that failed.

A value with a dimension is a ``Quantity``: ``set_params`` refuses a bare number for it.

Shows ``check``, ``set_params`` with a quantity,
``gm.study.size`` with its ``sizing`` notes, ``gm.simulate`` and ``gm.evaluate.failures``.

Run with ``python examples/plant.py``.
"""

import json
from pathlib import Path

import gemini as gm

SAMPLE = Path(__file__).resolve().parents[1] / "inputs/examples/shallow_district"
SIZED = ("capacity", "nominal_flow", "nominal_head")
"""Name endings of the values ``size`` computes from the case."""
COOLER = gm.units.Quantity(1.0, "MW")
"""The cooler capacity, a design value ``size`` does not compute: an assumption of this example."""


def leaves(tree, prefix=""):
    """Yield ``(path, leaf)`` of the nested ``params`` of a plant file, in file order."""
    for key, node in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        if {"value", "unit"} & set(node):
            yield path, node
        else:
            yield from leaves(node, path)


def value_of(leaf):
    """Return the value of a leaf: a ``Quantity`` if it has a unit, else the value."""
    return gm.units.Quantity(leaf["value"], leaf["unit"]) if "unit" in leaf else leaf["value"]


def build(stored):
    """Return the plant class with the stored design values, except those ``size`` computes."""
    size = stored["size"]["doublets"]["value"]
    plant = gm.plants.HeatingHeatPumpCoolingPlant(doublets=size)
    spread = stored["size"]["doublets"]["range"]
    plant.set_range("size.doublets", min=spread["min"], max=spread["max"])
    missing = [item for item in plant.check() if item.kind == "missing"]
    first = plant.get(missing[0].path.removeprefix("params."))
    print(f"Bare class: {len(missing)} values missing, the first {missing[0].path[7:]}:")
    print(f"  {first.description} [{first.unit}]")
    designed = {
        path.replace("control.", ""): value_of(leaf)
        for path, leaf in leaves(stored["params"])
        if "value" in leaf and not path.endswith(SIZED)
    }
    controls = plant.inputs()
    plant.set_params("", {key: v for key, v in designed.items() if key not in controls})
    plant.set_params("compression_cooler", {"capacity": COOLER})
    plant.set_inputs({key: v for key, v in designed.items() if key in controls})
    left = len([item for item in plant.check() if item.kind == "missing"])
    print(f"Filled: {left} left: the reservoir and well of the case, the sizes")
    print(f"Problems found by check: {len([i for i in plant.check() if i.kind != 'missing'])}")
    return plant


def main():
    """Fill the plant, size it, read the notes, simulate and group the failed steps."""
    stored = json.loads((SAMPLE / "plant.json").read_text())
    case = gm.Case.from_json(SAMPLE / "case.json")
    plant = build(stored)
    sized = gm.study.size(plant, case)
    for size in sized.sizing["sized"]:
        print(f"  sized {size['path']} = {size['value'].to_dict()}")
    print(f"Left unchanged: {[item['path'] for item in sized.sizing['unchanged']]}")
    print(f"Constraints broken by the start: {len(sized.sizing['broken'])}")
    print(f"Simulation of the start: {sized.sizing['simulation']}")
    results = gm.simulate(sized, case)
    print(f"Failed steps: {gm.evaluate.failures(results).to_dict()['total']}")
    report = gm.evaluate.report(sized, case, results)
    print(f"Heat delivered: {report['heat_delivered'].to('MWh').value:.1f} MWh")


if __name__ == "__main__":
    main()
