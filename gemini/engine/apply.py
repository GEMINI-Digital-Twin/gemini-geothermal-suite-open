"""The values of a case reach the modules of a plant by class, on a copy of the plant.

``apply_case`` sets, for a run, what the plant dict does not hold: the ground on every
``Formation``, the reservoir and the fluid on every reservoir and ``Doublet`` (at the depth of the
doublet), the air on every ``Atmosphere``, the grid gas on every ``GasGrid``, the supply
temperature plus the margin on every unit of a supply line, and, for the consumers
(``HeatingGrid``, ``CoolingGrid``), the desander (``site.fluid``) and the grid connection
(``utilities.electricity``), every parameter and boundary that declares a case path (``case=``),
and checks the states a stateful module starts from (``initial_state``); ``started`` hands them
to the run.
One private function does each kind. A value the plant needs and the case lacks raises
``missing_value`` naming its path in the case.
"""

import weakref
from copy import deepcopy

import numpy as np

from gemini._utils.strings import join_path
from gemini.case._utils.access import require
from gemini.errors import ValidationError
from gemini.modules.environment import Atmosphere, Formation
from gemini.modules.grids import CoolingGrid, ElectricityGrid, GasGrid, HeatingGrid
from gemini.modules.states import nested
from gemini.modules.subsurface import InjectionReservoir, ProductionReservoir
from gemini.modules.treatment import Desander
from gemini.plants.doublet import Doublet
from gemini.plants.roles import SUPPLY_CLASSES, supply_service
from gemini.streams.fluid import Fluid

RESERVOIRS = (ProductionReservoir, InjectionReservoir)
"""The classes that are a reservoir."""

_APPLIED = weakref.WeakKeyDictionary()
"""Each plant ``applied_in_place`` made, with a weak reference to the case it carries."""


def apply_case(plant, case):
    """Return a copy of ``plant`` with the values of ``case`` set by class.

    The plant of the user never changes. A plant without a module of a class needs none of its
    values, so a case may leave them out. A plant that ``applied_in_place`` or this function
    already made for the same ``case`` object is returned as it is, so a run and the metrics read
    from it share one copy.
    """
    if _carries(plant, case):
        return plant
    return applied_in_place(deepcopy(plant), case)


def _carries(plant, case):
    """Return whether ``plant`` is a copy that already has the values of this ``case`` object."""
    found = _APPLIED.get(plant)
    return found is not None and found() is case


def started(case):
    """Return the ``state=`` of ``Engine.simulate``: the initial states of ``case``, else ``None``.

    The states are the nested dict of the states of the plant's modules, by child name, in SI.
    """
    if not case.initial_state:
        return None
    values = {
        path: {name: leaf.si for name, leaf in states.items()}
        for path, states in case.initial_state.items()
    }
    return {"position": None, "module_states": {"": nested(values)}}


def applied_in_place(plant, case):
    """Set the values of ``case`` by class on ``plant`` itself and return it.

    For a copy the caller owns, such as the working copy of one trial of a study: it saves the
    second copy ``apply_case`` makes. The plant is then known to carry ``case``, so ``apply_case``
    of the same case returns it without copying; set no value of the case on it afterwards.
    """
    applied = plant
    doublets = [path for path, module in applied.named_modules() if isinstance(module, Doublet)]
    _formations(applied, case, doublets)
    _reservoirs(applied, case, doublets)
    _doublets(applied, case, doublets)
    _air(applied, case)
    _gas(applied, case)
    _owned(applied, case, ((HeatingGrid, "demand.heating."), (CoolingGrid, "demand.cooling.")))
    _owned(applied, case, ((Desander, "site.fluid."), (ElectricityGrid, "utilities.electricity.")))
    _supply(applied, case)
    _states(applied, case)
    _APPLIED[applied] = weakref.ref(case)
    return applied


def remember_case(plant, case):
    """Record that ``plant`` carries the values of ``case``, as ``applied_in_place`` does.

    For a plant whose state was put back after a run, such as the shared plant of a study.
    """
    _APPLIED[plant] = weakref.ref(case)


def _outside(path, doublets):
    """Return whether the module at ``path`` is no part of a doublet."""
    return not any(path.startswith(f"{doublet}.") for doublet in doublets)


def _fluid(case):
    """Return the ``Fluid`` of the reservoir brine from ``site.fluid``."""
    fluid = case.site.fluid if case.site else None
    density = require(fluid, "density", "site.fluid")
    viscosity = require(fluid, "viscosity", "site.fluid")
    given = {"gas_liquid_ratio": fluid.gas_liquid_ratio, "gas_composition": fluid.dissolved_gas}
    return Fluid._si(
        kind="brine",
        density=density,
        viscosity=viscosity,
        **{name: value for name, value in given.items() if value is not None},
    )


def _formations(plant, case, doublets):
    """Set the surface temperature and the gradient on every ``Formation`` outside a doublet."""
    for path, module in plant.named_modules():
        if isinstance(module, Formation) and _outside(path, doublets):
            plant._set_si_params(
                path,
                {
                    "geothermal_gradient": require(case, "site.ground.gradient"),
                    "surface_temperature": require(case, "site.ground.surface_temperature"),
                },
            )


def _reservoirs(plant, case, doublets):
    """Set the permeability, thickness, pressure and fluid on every reservoir outside a doublet."""
    for path, module in plant.named_modules():
        if isinstance(module, RESERVOIRS) and _outside(path, doublets):
            reference = require(case, "site.reservoir.reference_depth")
            module.fluid = _fluid(case)
            plant._set_si_params(
                path,
                {
                    "permeability": require(case, "site.reservoir.permeability"),
                    "aquifer_thickness": require(case, "site.reservoir.thickness"),
                    "pressure": case.site.pressure_at(reference),
                },
            )


def _doublets(plant, case, doublets):
    """Set the ground, the reservoir and the fluid on every ``Doublet``, at its own depth."""
    for path in doublets:
        doublet = plant.get_submodule(path)
        doublet.fluid = _fluid(case)
        values = {
            "gradient": require(case, "site.ground.gradient"),
            "surface_temperature": require(case, "site.ground.surface_temperature"),
            "thickness": require(case, "site.reservoir.thickness"),
            "permeability": require(case, "site.reservoir.permeability"),
        }
        if doublet.depth is not None:
            temperature = case.site.temperature_at(doublet.depth)
            pressure = case.site.pressure_at(doublet.depth)
            for limb in ("reservoir", "sink"):
                values[f"{limb}.temperature"] = temperature
                values[f"{limb}.pressure"] = pressure
        plant._set_si_params(path, values)


def _air(plant, case):
    """Set the air pressure and temperature on every ``Atmosphere``; a profile is the plan's."""
    paths = [path for path, module in plant.named_modules() if isinstance(module, Atmosphere)]
    if not paths:
        return
    pressure = require(case, "site.air.pressure")
    for path in paths:
        plant._set_si_params(path, {"pressure": pressure})
    air = require(case, "site.air.temperature")
    if isinstance(air, np.ndarray):
        return
    plant._set_si_inputs({join_path(path, "temperature"): air for path in paths})


def _gas(plant, case):
    """Set the grid gas composition of ``utilities.gas`` on every ``GasGrid``; it must be given."""
    for path, module in plant.named_modules():
        if isinstance(module, GasGrid):
            composition = require(case, "utilities.gas.composition")
            plant._set_si_params(path, {"composition": dict(composition)})


def _given(case, path):
    """Return the value at the dotted ``path`` of the case, or ``None`` when it has none."""
    value = case
    for name in path.split("."):
        value = getattr(value, name, None)
        if value is None:
            return None
    return value


def _owned(plant, case, owners):
    """Set on every module of a class of ``owners`` the values its declarations take from the case.

    ``owners`` is ``((class, prefix), ...)``: a parameter or boundary of the class that declares a
    case path under ``prefix`` takes the value there when the case has one. A parameter that has
    none stays empty (the module says what it needs), and a boundary the plan gives at each step
    wins over it.
    """
    for cls, prefix in owners:
        for path, module in plant.named_modules():
            if isinstance(module, cls):
                _set_owned(plant, case, path, module, prefix)


def _set_owned(plant, case, path, module, prefix):
    """Set the case values of the declarations of one ``module`` under the case path ``prefix``."""
    params, inputs = {}, {}
    for name, declaration in [*module.named_parameters(), *module.inputs().items()]:
        where = getattr(declaration, "case", None)
        value = _given(case, where) if where and where.startswith(prefix) else None
        if value is not None:
            target = params if declaration.section == "parameter" else inputs
            target[name] = value
    if params:
        plant._set_si_params(path, params)
    if inputs:
        plant._set_si_inputs({join_path(path, name): value for name, value in inputs.items()})


def _supply(plant, case):
    """Set the setpoint of each unit on a supply line: the supply temperature plus its margin.

    A heating unit regulates to the supply temperature of ``demand.heating`` plus ``supply_margin``,
    a cooling unit to the one of ``demand.cooling`` minus it. A unit without a margin keeps the
    setpoint the plant or the plan gives; a margin on a unit that is on no supply line raises
    ``invalid_design``.
    """
    for path, module in plant.named_modules():
        if not isinstance(module, SUPPLY_CLASSES) or module.supply_margin is None:
            continue
        service = supply_service(plant, path, module)
        if service is None:
            raise ValidationError(
                f"{path}: supply_margin is set but the unit feeds neither the heating nor the "
                "cooling grid; expected a unit on a supply line",
                path=join_path(path, "supply_margin"),
                code="invalid_design",
            )
        supply = require(case, f"demand.{service}.supply_temperature")
        margin = module.supply_margin if service == "heating" else -module.supply_margin
        plant._set_si_inputs({join_path(path, "temperature_setpoint"): supply + margin})


def _states(plant, case):
    """Refuse each module or state named in ``initial_state`` that the plant lacks.

    The error is ``unknown_name`` (``gm.check`` lists it first). The states themselves reach the
    run through ``started``.
    """
    for path, states in (case.initial_state or {}).items():
        module = plant.get_submodule(path)
        missing = sorted(set(states) - set(module._states))
        if missing:
            raise ValidationError(
                f"initial_state.{path}.{missing[0]}: {path or 'plant'} has no such state; "
                f"expected one of {sorted(module._states)}",
                path=f"initial_state.{path}.{missing[0]}",
                code="unknown_name",
            )
