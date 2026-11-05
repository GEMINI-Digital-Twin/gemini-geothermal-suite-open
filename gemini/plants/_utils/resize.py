"""A plant on another number of doublets: its plant file with the doublets renumbered."""

import re
from copy import deepcopy

from gemini.errors import ValidationError

PATH_SECTIONS = ("params", "fluids")
"""The sections of a plant file whose keys start with a module path."""
_DOUBLET = re.compile(r"d(\d+)(?=\.|$)")


def _index(key):
    """Return the number of the doublet a key starts with, or ``None``."""
    found = _DOUBLET.match(key)
    return None if found is None else int(found.group(1))


def _renumbered(section, old, new):
    """Return ``section`` without the doublets from ``new`` on, and with the new ones as ``d0``.

    A new doublet that the section already names (a range stated for a doublet the plant did not
    have yet, geomind QA-253) takes ``d0``'s values with what it states on top.
    """
    kept = {
        key: value for key, value in section.items() if _index(key) is None or _index(key) < new
    }
    for key, value in section.items():
        if _index(key) == 0:
            for number in range(old, new):
                copy = _DOUBLET.sub(f"d{number}", key, count=1)
                kept[copy] = _overlaid(deepcopy(value), kept.get(copy))
    return kept


def _overlaid(base, stated):
    """Return ``base`` with the nodes of ``stated`` on top; a leaf keeps its value and unit."""
    if not isinstance(stated, dict) or not isinstance(base, dict):
        return base if stated is None else stated
    if "value" in base:
        return base | _in_unit(stated, base.get("unit"))
    for key, item in stated.items():
        base[key] = _overlaid(base[key], item) if key in base else item
    return base


def _in_unit(stated, unit):
    """Return the ``range`` and ``options`` of a stated leaf, a range in ``unit``."""
    from gemini.units import Quantity

    found = {key: stated[key] for key in ("range", "options") if key in stated}
    given = stated.get("unit")
    if "range" in found and given is not None and unit is not None and given != unit:
        found["range"] = {
            side: Quantity(value, given).to(unit).value for side, value in found["range"].items()
        }
    return found


def resized(plant, doublets):
    """Return a new plant of the same class and values on ``doublets`` doublets.

    The values stated on ``d0`` repeat on each added doublet; those of a removed doublet go. A
    plant whose class takes no structural size ``doublets`` raises ``invalid_design``, and a
    number its class does not allow raises the same from the class.
    """
    from gemini.plants.plant import Plant

    if type(plant) is Plant and free_doublets(plant) is not None:
        return _free_resized(plant, doublets)
    data = plant.to_dict()
    old = plant.size.get("doublets")
    if old is None:
        raise ValidationError(
            f"study: {type(plant).__name__} has no structural size 'doublets'; expected a plant "
            "class that takes it (see gm.plants.capabilities())",
            path="size.doublets",
            code="invalid_design",
        )
    data["size"] = {**data["size"], "doublets": {**data["size"]["doublets"], "value": doublets}}
    for name in PATH_SECTIONS:
        data[name] = _renumbered(data.get(name, {}), old, doublets)
    return type(plant).from_dict(data)


FREE_MAXIMUM = 3
"""The most doublets a plant without a class is resized to, as the doublet plant classes allow."""
MIXERS, SPLITTERS = "production_mixers", "injection_splitters"
"""The module lists that join the added doublets, named as on the doublet plant classes."""


def free_doublets(plant):
    """Return 1 when a plant without a class can vary its number of doublets, else ``None``.

    That is a plant with one ``Doublet`` named ``d0`` at its top, no ``d1`` and none of the
    filled module lists that would join more (geomind QA-129): its ``size.doublets`` can then take a
    range, and ``resized`` copies ``d0`` and joins the copies in parallel.
    """
    from gemini.plants import Doublet

    children = dict(plant.named_children())
    if not isinstance(children.get("d0"), Doublet) or "d1" in children:
        return None
    if any(
        len(list(children[name].children())) for name in (MIXERS, SPLITTERS) if name in children
    ):
        return None
    return 1


def _free_resized(plant, doublets):
    """Return a plant without a class on ``doublets`` doublets: ``d0`` copied and joined."""
    from gemini.plants.plant import Plant

    if not 1 <= doublets <= FREE_MAXIMUM:
        raise ValidationError(
            f"study: doublets = {doublets}; expected 1 to {FREE_MAXIMUM}",
            path="size.doublets",
            code="invalid_design",
        )
    data = plant.to_dict()
    data.pop("size", None)
    if doublets == 1:
        return Plant.from_dict(data)
    modules = data["modules"]
    for number in range(1, doublets):
        modules[f"d{number}"] = deepcopy(modules["d0"])
    joins = doublets - 1
    modules[MIXERS] = {
        "type": "ModuleList",
        "modules": {str(i): {"type": "Mixer"} for i in range(joins)},
    }
    modules[SPLITTERS] = {
        "type": "ModuleList",
        "modules": {str(i): {"type": "Splitter"} for i in range(joins)},
    }
    data["connections"] = _free_connections(data["connections"], doublets)
    for name in PATH_SECTIONS:
        data[name] = _renumbered(data.get(name, {}), 1, doublets)
    return Plant.from_dict(data)


def _free_connections(connections, doublets):
    """Return the connections with the doublets in parallel, as a doublet plant class wires them.

    The supply of ``d0`` and the copies joins through a chain of mixers into the module ``d0`` fed,
    the brine to ``d0`` divides over a chain of splitters, and every other connection of ``d0``
    (its electricity, a signal) repeats for each copy.
    """
    found = []
    for item in connections:
        source, target = item["source"], item["target"]
        if source == "d0.supply_out":
            found += _mix_chain(item, doublets)
        elif target == "d0.return_in":
            found += _split_chain(item, doublets)
        else:
            found += [item, *_repeated(item, doublets)]
    return found


def _repeated(item, doublets):
    """Return a connection of ``d0`` repeated for each copy ``d1`` ...; ``[]`` for any other."""
    source, target = item["source"], item["target"]
    if _index(source) != 0 and _index(target) != 0:
        return []
    found = []
    for number in range(1, doublets):
        copy = deepcopy(item)
        if _index(source) == 0:
            copy["source"] = _DOUBLET.sub(f"d{number}", source, count=1)
        if _index(target) == 0:
            copy["target"] = _DOUBLET.sub(f"d{number}", target, count=1)
        found.append(copy)
    return found


def _mix_chain(item, doublets):
    """Return the connections that join each doublet's supply, in order, into ``item``'s target."""
    found = [
        {**item, "source": "d0.supply_out", "target": f"{MIXERS}.0.branch1_in"},
        {**item, "source": "d1.supply_out", "target": f"{MIXERS}.0.branch2_in"},
    ]
    for index in range(1, doublets - 1):
        found += [
            {
                **item,
                "source": f"{MIXERS}.{index - 1}.fluid_out",
                "target": f"{MIXERS}.{index}.branch1_in",
            },
            {
                **item,
                "source": f"d{index + 1}.supply_out",
                "target": f"{MIXERS}.{index}.branch2_in",
            },
        ]
    found.append({**item, "source": f"{MIXERS}.{doublets - 2}.fluid_out", "target": item["target"]})
    return found


def _split_chain(item, doublets):
    """Return the connections that divide ``item``'s source over the doublets, one splitter each."""
    found = []
    running = item["source"]
    for index in range(doublets - 1):
        splitter = f"{SPLITTERS}.{index}"
        found += [
            {**item, "source": running, "target": f"{splitter}.fluid_in"},
            {**item, "source": f"{splitter}.branch1_out", "target": f"d{index}.return_in"},
        ]
        running = f"{splitter}.branch2_out"
    found.append({**item, "source": running, "target": f"d{doublets - 1}.return_in"})
    return found
