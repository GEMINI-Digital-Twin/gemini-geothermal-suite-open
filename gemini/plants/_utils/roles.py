"""What a module is for in a plant, found from its class and its wiring, never from its name."""

from gemini._utils.strings import join_path
from gemini.errors import ValidationError
from gemini.modules.cooling import AbsorptionUnit, AdsorptionChiller
from gemini.modules.exchangers import HeatExchanger
from gemini.modules.grids import CoolingGrid, HeatingGrid
from gemini.modules.heating import CHP, Boiler, ElectricBoiler, HeatPump
from gemini.plants.doublet import Doublet

CLASSES = {
    "doublet": Doublet,
    "boiler": Boiler,
    "chp": CHP,
    "heat_exchanger": HeatExchanger,
    "heating_supply": HeatingGrid,
    "cooling_supply": CoolingGrid,
}
"""The roles that the class of a module alone decides."""
PLANT = "plant"
"""The role of the plant itself, at the root path ``""``."""
ROLES = (*CLASSES, "heat_pump", "chiller", PLANT)
"""Every role a module can have."""
DELIVERY = {
    "heat_pump": {HeatPump: ("sink_out", "sink_in")},
    "boiler": {Boiler: ("fluid_out", "fluid_in")},
    "chp": {CHP: ("fluid_out", "fluid_in")},
    "chiller": {
        HeatPump: ("source_in", "source_out"),
        AbsorptionUnit: ("chilled_in", "chilled_out"),
        AdsorptionChiller: ("chilled_in", "chilled_out"),
    },
}
"""For each role and class, the two ports whose enthalpy flows, first less second, give the power
the unit delivers: heat to its water, or cold from its chilled water."""


def _reaches(plant, path, port, grid):
    """Return whether the outlet ``path.port`` feeds a module of class ``grid``."""
    fed = plant.feeds(join_path(path, port))
    return any(isinstance(plant.get_submodule(item), grid) for item in fed)


def roles_of(plant, path, module):
    """Return the roles of ``module`` at ``path`` in ``plant``.

    A heat pump is a ``heat_pump`` when its ``sink_out`` reaches a ``HeatingGrid`` and a
    ``chiller`` when its ``source_out`` reaches a ``CoolingGrid``; an absorption or adsorption
    unit is a ``chiller`` when its ``chilled_out`` reaches a ``CoolingGrid``. The root is also
    the ``plant``.
    """
    found = [module.plant_role] if module.plant_role else []
    if not path:
        found.append(PLANT)
    if isinstance(module, HeatPump):
        if _reaches(plant, path, "sink_out", HeatingGrid):
            found.append("heat_pump")
        if _reaches(plant, path, "source_out", CoolingGrid):
            found.append("chiller")
    if isinstance(module, (AbsorptionUnit, AdsorptionChiller)):
        if _reaches(plant, path, "chilled_out", CoolingGrid):
            found.append("chiller")
    return found


SUPPLY = (
    (HeatPump, "sink_out", HeatingGrid, "heating"),
    (Boiler, "fluid_out", HeatingGrid, "heating"),
    (ElectricBoiler, "fluid_out", HeatingGrid, "heating"),
    (HeatPump, "source_out", CoolingGrid, "cooling"),
    (AbsorptionUnit, "chilled_out", CoolingGrid, "cooling"),
    (AdsorptionChiller, "chilled_out", CoolingGrid, "cooling"),
)
"""The units that regulate a supply temperature: class, outlet that carries it, grid it must reach
and the service."""


SUPPLY_CLASSES = tuple(dict.fromkeys(cls for cls, *_ in SUPPLY))
"""The classes of ``SUPPLY``."""


def supply_service(plant, path, module):
    """Return ``"heating"`` or ``"cooling"`` when ``module`` at ``path`` is on a supply line.

    A unit is on a supply line when the outlet that carries its useful stream reaches the
    ``HeatingGrid`` or the ``CoolingGrid`` (``plant.feeds``, the rule the schedule uses for its
    roles). ``None`` for a unit on neither; a unit on both raises ``invalid_design``, because it
    has one setpoint.
    """
    found = {
        service
        for cls, port, grid, service in SUPPLY
        if isinstance(module, cls) and _reaches(plant, path, port, grid)
    }
    if len(found) > 1:
        raise ValidationError(
            f"{path or 'plant'} feeds both the heating and the cooling grid; expected one supply "
            "line, because a unit has one setpoint",
            path=path,
            code="invalid_design",
        )
    return found.pop() if found else None


def units_of(plant, role):
    """Return the paths of the modules of ``role`` in ``plant``; the root is the path ``""``."""
    return [path for path, module in plant.named_modules() if role in roles_of(plant, path, module)]


def delivery_ports(module, role):
    """Return ``(first, second)``, the ports whose enthalpy flows give the power ``module`` gives.

    The power is the flow of ``first`` less that of ``second``. ``None`` for a class of the role
    with no such pair.
    """
    for cls, ports in DELIVERY[role].items():
        if isinstance(module, cls):
            return ports
    return None
