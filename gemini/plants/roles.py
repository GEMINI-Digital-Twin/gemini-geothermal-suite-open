"""The roles of a plant: what each unit is for, its quantities, and how to find its units.

A module class declares its ``plant_role`` when its class alone decides it (a ``Doublet``, a
``Boiler``, a ``CHP``, a ``HeatExchanger``, a ``HeatingGrid``, a ``CoolingGrid``). The rest is read
from the wiring: a heat pump is a ``heat_pump`` when its ``sink_out`` reaches a ``HeatingGrid`` and
a ``chiller`` when its ``source_out`` reaches a ``CoolingGrid``, never from a module name. This file
is the one owner of roles: ``roles()`` lists the closed table, ``roles_of`` and ``units_of`` find
the roles of a plant, and the private table below says, for each quantity of a role, its dimension,
the result field or parameter it reads below the unit, and how it is read: ``result`` (an output or
port field of the unit), ``parameter``, ``delivery`` (the power the unit gives its circuit, from the
enthalpy flows of its ports) or ``plant`` (a figure of the plant as a whole, read from the edge
modules as ``gm.evaluate.totals`` and ``gm.evaluate.co2`` read them). A requirement of ``gm.case``
names a role and a quantity of it.
"""

from collections import namedtuple

from gemini import units
from gemini._utils.strings import close_matches, did_you_mean, join_names, join_path
from gemini.errors import ValidationError
from gemini.modules.cooling import AbsorptionUnit, AdsorptionChiller
from gemini.modules.grids import CoolingGrid, HeatingGrid
from gemini.modules.heating import CHP, Boiler, ElectricBoiler, HeatPump

Reads = namedtuple("Reads", "dimension path source over")
"""One quantity of a role: the dimension of its bounds (``None`` without one), the path below the
unit (the name of the figure for ``delivery``, ``plant``, ``share`` and ``count``), how it is read
(``result``, ``parameter``, ``delivery``, ``plant``, ``share`` or ``count``) and whether it takes
``over``: a per-step quantity does, a window quantity (a total or share over the period) or a
property of the plant does not."""

TABLE = {
    "doublet": {
        "production_flow": Reads("volume_flow", "reservoir.liquid_flow", "result", True),
        "brine_cooling": Reads("temperature_difference", "brine_cooling", "result", True),
        "production_temperature": Reads(
            "temperature", "riser.wellhead_out.temperature", "result", True
        ),
        "injection_temperature": Reads(
            "temperature", "injector.wellhead_in.temperature", "result", True
        ),
        "pump_power": Reads("power", "esp.power_in", "result", True),
        "pump_efficiency": Reads("efficiency", "pump_efficiency", "parameter", False),
        "intake_pressure": Reads("pressure", "esp.intake_pressure", "result", True),
        "intake_gas_fraction": Reads("fraction", "esp.gas_volume_fraction", "result", True),
        "reinjection_ratio": Reads("ratio", "reinjection_ratio", "result", True),
        "count": Reads("count", "doublets", "count", False),
        "wellhead_pressure": Reads("pressure", "riser.wellhead_out.pressure", "result", True),
    },
    "heat_pump": {
        "cop": Reads("ratio", "cop", "result", True),
        "lift": Reads("temperature_difference", "temperature_lift", "result", True),
        "heat_output": Reads("power", "heat_output", "delivery", True),
    },
    "boiler": {
        "fuel_input": Reads("power", "fuel", "result", True),
        "heat_output": Reads("power", "heat_output", "delivery", True),
    },
    "chp": {
        "power_output": Reads("power", "power_out", "result", True),
        "heat_output": Reads("power", "heat_output", "delivery", True),
    },
    "chiller": {
        "cop": Reads("ratio", "cop", "result", True),
        "cold_output": Reads("power", "cold_output", "delivery", True),
    },
    "heat_exchanger": {
        "duty": Reads("power", "duty", "result", True),
        "approach": Reads("temperature_difference", "approach_temperature", "result", True),
    },
    "heating_supply": {
        "temperature": Reads("temperature", "supply_in.temperature", "result", True),
        "unmet": Reads("power", "unmet_demand", "result", True),
        "unmet_share": Reads("fraction", "unmet_demand", "share", False),
    },
    "cooling_supply": {
        "temperature": Reads("temperature", "supply_in.temperature", "result", True),
        "unmet": Reads("power", "unmet_sensible", "result", True),
        "unmet_share": Reads("fraction", "unmet_sensible", "share", False),
    },
    "plant": {
        "electricity_bought": Reads("power", "electricity_bought", "plant", True),
        "gas_bought": Reads("power", "gas_bought", "plant", True),
        "heat_surplus": Reads("power", "heat_surplus", "plant", True),
        "co2": Reads("mass", "co2", "plant", True),
    },
}
"""``{role: {quantity: Reads}}``: the one table of roles."""


def roles():
    """Return the closed table of roles as ``{role: {quantity: {"dimension", "over"}}}``.

    A requirement is on a role and a quantity of it. The roles are ``doublet``, ``heat_pump``,
    ``boiler``, ``chp``, ``chiller`` (absorption, adsorption and compression), ``heat_exchanger``,
    ``heating_supply``, ``cooling_supply`` and ``plant``. ``dimension`` is the quantity of the
    bounds, ``None`` for a number without one; ``over`` says whether the quantity is read per step
    and takes ``over``, or is a window quantity or a property that takes none.

    ``heat_output`` of ``heat_pump``, ``boiler`` and ``chp`` is the heat the unit gives its water
    and ``cold_output`` of ``chiller`` the cold it takes from its chilled water, in W, from the
    enthalpy flows of its ports (the source side for a heat pump in cooling mode).
    ``reinjection_ratio`` of ``doublet`` is the injected over the produced liquid volume flow.
    ``count`` of ``doublet`` is the number of doublets of the plant and ``unmet_share`` of a supply
    the unmet energy over the energy demanded by the service, both over the whole period. The role
    ``plant`` is the plant itself (``unit_path`` ``""``): ``electricity_bought``, ``gas_bought``
    and ``heat_surplus`` are powers in W as ``gm.evaluate.totals`` sums them; ``co2`` is the mass
    in kg of CO2-equivalent emitted in each step, as ``gm.evaluate.co2`` sums it, so ``over:
    sum`` of it is the mass of the run (``over: each`` judges the mass of a step, which depends
    on its length). ``sum`` of a power adds the step values, as for every other power.
    """
    return {
        role: {
            quantity: {"dimension": dimension(read.dimension), "over": read.over}
            for quantity, read in quantities.items()
        }
        for role, quantities in TABLE.items()
    }


def dimension(name):
    """Return ``name``, the dimension of a quantity, or ``None`` when its SI unit is ``-``."""
    return None if units.si_unit(units.names(name)[0]) == "-" else name


def check_role(role):
    """Return ``role`` or raise ``unknown_name`` listing the roles."""
    if role not in TABLE:
        raise ValidationError(
            f"role {role!r} is unknown; expected one of {join_names(TABLE)}"
            f"{did_you_mean(role, TABLE)}",
            suggestions=close_matches(role, TABLE),
            code="unknown_name",
        )
    return role


def reads(role, quantity):
    """Return the ``Reads`` of ``quantity`` of ``role``, or raise saying what the role has."""
    check_role(role)
    if quantity not in TABLE[role]:
        raise ValidationError(
            f"{quantity!r} is not a quantity of {role!r}; expected one of "
            f"{join_names(TABLE[role])}{did_you_mean(quantity, TABLE[role])}",
            suggestions=close_matches(quantity, TABLE[role]),
            code="invalid_value",
        )
    return TABLE[role][quantity]


PLANT = "plant"
"""The role of the plant itself, at the root path ``""``."""
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
