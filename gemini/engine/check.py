"""``gm.check``: what only the plant and the case together can say is missing or wrong."""

from dataclasses import replace

from gemini import units
from gemini._utils.strings import join_path
from gemini.case._utils.kinds import BASIS_SIZES, EQUIPMENT_KINDS, is_priced
from gemini.engine.apply import apply_case
from gemini.errors import ValidationError
from gemini.errors.base import Issue, raise_issues
from gemini.modules.module import Module
from gemini.plants._utils import form
from gemini.plants.roles import remembered, units_of

SUPPLY_ROLES = ("heating_supply", "cooling_supply")
"""The roles a requirement may name that a plant need not have: the case judges any plant (P2).

A plant without them is judged infeasible for the service by the verdict, not refused."""
ECONOMICS = "economics"
"""The path of the economics in a case."""
GAS_ROLES = ("boiler", "chp")
"""The roles that burn grid gas, whose price a least-cost dispatch needs."""


def check(plant, case):
    """Return the issues that prevent ``plant`` from running on ``case``; it never raises.

    An empty list means ready. The issues are those of ``Issue`` with a ``path`` in the files; a
    warning (``Issue.is_warning``, kind ``deprecated``) comes last and does not make the plant
    unready, so a caller that judges readiness reads the issues that are no warning:

    - a parameter of the plant without a value (``missing``, path ``params.<path>``);
    - for every equipment kind the plant contains, a capex and a fixed opex in the economics
      (``missing``, ``economics.capex.<kind>``, ``economics.opex.fixed.<kind>``, code
      ``missing_assumption``); a case without economics is a pure physics case and has none of
      these issues, and a kind priced only when given (``PRICED_WHEN_GIVEN``: an ice store)
      without its capex has none either;
    - for a capex given on another basis than that of its kind (a heat exchanger per W), or a
      fixed opex per W and year, the design value of each module of the kind that sizes it
      (``missing``, path ``params.<path>.<name>``, code ``missing_value``);
    - every role a requirement names must exist in the plant (``incompatible``, path
      ``requirements[<n>].on``), except ``heating_supply`` and ``cooling_supply``: a plant without
      a supply is judged infeasible for that service by ``gm.evaluate.verdict``, so that one case
      judges any plant;
    - an initial state for every state of every stateful module (``missing``, path
      ``initial_state.<module>.<state>``), a state or a module the plant lacks
      (``unknown_key``), a unit of another dimension (``unit``);
    - when the plant states the dispatch ``least_cost``, the electricity price and, for a plant with
      a gas unit, the gas price in the economics (``missing``);
    - a ``range`` on a value of the case or of its economics (``deprecated``): a search range
      belongs on the plant leaf.

    A case that is wrong by itself (``case.check()``, for example a value set with ``with_value`` of
    another type than the quantity) is reported with its own issues and not applied to the plant.

    Parameters
    ----------
    plant : Module
        The plant.
    case : Case or None
        The case. With ``None`` only the parameters of the plant are checked.

    Returns
    -------
    list of Issue
        What is missing or wrong, an empty list when the plant is ready for the case.
    """
    if case is None:
        return _parameters(plant) + _rules(plant)
    own = case.check()
    if any(not item.is_warning for item in own):
        return own
    try:
        applied = apply_case(plant, _known_states(plant, case))
    except ValidationError as error:
        return _refused(error) + own
    return issues_of(applied, case) + own


def _known_states(plant, case):
    """Return ``case`` without the initial states the plant lacks, which ``_states`` reports."""
    if not case.initial_state:
        return case
    modules = dict(plant.named_modules())
    known = {
        path: {name: leaf for name, leaf in states.items() if name in modules[path]._states}
        for path, states in case.initial_state.items()
        if path in modules
    }
    return case._copy(initial_state=known)


def issues_of(applied, case):
    """Return the issues of ``check`` for a plant that already carries the values of ``case``."""
    with remembered():
        depths = _depths(applied)
        named = {item.path for item in depths}
        return [
            *depths,
            *(item for item in _parameters(applied) if item.path not in named),
            *_rules(applied),
            *_pump_setpoints(applied),
            *_closed_coolers(applied),
            *_split_paths(applied),
            *_frozen_paths(applied),
            *_kinds(applied, case),
            *_sizes(applied, case),
            *_roles(applied, case),
            *_states(applied, case),
            *_prices(applied, case),
        ]


def checked(applied, case):
    """Raise the ``ValidationError`` carrying every issue of ``issues_of``, if there are any."""
    raise_issues(issues_of(applied, case))


def _refused(error):
    """Return the issues of a ``ValidationError`` that ``apply_case`` raised for the plant."""
    problems = error.problems
    return [
        Issue(
            item["path"] or "",
            (
                "missing"
                if item["code"] in ("missing_value", "missing_assumption")
                else "incompatible"
            ),
            item["message"],
            code=item["code"],
        )
        for item in problems
    ]


def _parameters(plant):
    """Return the ``missing`` issues of the parameters of the plant, with the paths of the file."""
    return [
        replace(item, path=join_path("params", form.file_path(item.path)))
        for item in Module.check(plant)
    ]


PLANT_RULES = {
    "control.dispatch": "'least_cost'",
    "control.outages": "'lowest_demand'",
    "backup": "'peak' or 'none'",
}
"""The plant options a schedule or a sizing stops on when unset, with the values they take."""


def _rules(plant):
    """Return the ``missing`` issues of the plant options and split wells a run needs.

    ``params.control.dispatch`` and ``params.control.outages`` (the schedule's rules),
    ``params.backup`` (the sizing's policy) and the ``esp_depth`` of a well split at its pump
    have no default and stop a schedule, a sizing or a run, so ``check`` names them (gemini
    requests 33 and 36).
    """
    from gemini.modules.wells.productionwell import ProductionWell

    issues = []
    for name, expected in PLANT_RULES.items():
        attribute = name.rsplit(".", 1)[-1]
        if _declares(plant, attribute) and _set_value(plant, attribute) is None:
            path = f"params.{name}"
            issues.append(
                Issue(
                    path, "missing", f"{path} is missing; expected {expected}", code="missing_value"
                )
            )
    for path, module in plant.named_modules():
        split = _set_value(module, "segment") in ("below_esp", "above_esp")
        if isinstance(module, ProductionWell) and split and _set_value(module, "esp_depth") is None:
            where = join_path("params", form.file_path(join_path(path, "esp_depth")))
            issues.append(
                Issue(
                    where,
                    "missing",
                    f"{where} is missing; a well split at its pump ({module.segment}) needs it",
                    code="missing_value",
                )
            )
    return issues


def _pump_setpoints(plant):
    """Return a ``missing`` issue for each injection pump that has no way to set its head.

    A pump without head curves (``head_coefficients`` with ``stage_count``) raises its water to its
    ``pressure_setpoint``; without one every step of a run failed with a head of NaN (geomind
    QA-250), so ``check`` names the setpoint.
    """
    from gemini.modules.pumps import InjectionPump

    issues = []
    for path, module in plant.named_modules():
        if not isinstance(module, InjectionPump):
            continue
        curves = _set_value(module, "head_coefficients") is not None
        issues += _pump_drive(plant, path, module, curves)
        if curves or plant.input_value(join_path(path, "pressure_setpoint")) is not None:
            continue
        where = join_path("params", form.file_path(join_path(path, "pressure_setpoint")))
        issues.append(
            Issue(
                where,
                "missing",
                f"{where} is missing; expected the discharge pressure the injection pump "
                "delivers (the injection well's need), or head_coefficients and stage_count; "
                "gm.study.size sets it from the doublets the pump serves (derived by size)",
                code="missing_value",
            )
        )
    return issues


def _pump_drive(plant, path, module, curves):
    """Return ``missing`` issues for an injection pump's ``frequency`` and ``efficiency`` (QA-343).

    Both were found one run at a time after sizing: the frequency is a control with no default
    (an ``invalid_binding`` at the run), and a pump without both curves needs its efficiency.
    """
    issues = []
    if plant.input_value(join_path(path, "frequency")) is None:
        where = join_path("params", form.file_path(join_path(path, "frequency")))
        issues.append(
            Issue(
                where,
                "missing",
                f"{where} is missing; expected the pump motor's frequency; gm.study.size sets "
                "gemini's reference frequency for a pump without curves",
                code="missing_value",
            )
        )
    power = curves and _set_value(module, "power_coefficients") is not None
    if not power and module.efficiency is None:
        where = join_path("params", form.file_path(join_path(path, "efficiency")))
        issues.append(
            Issue(
                where,
                "missing",
                f"{where} is missing; expected the pump's efficiency, or head and power curves; "
                "gm.study.size takes the pump_efficiency of the doublets it serves",
                code="missing_value",
            )
        )
    return issues


def _closed_coolers(plant):
    """Return a ``missing`` issue for each air cooler on a closed loop without its first guess.

    A cooler whose outlet comes back to its own inlet (a chiller's condenser loop) offers the
    loop's first guess from ``loop_pressure`` and ``flow``; without them the run stopped with an
    ``invalid_design`` after every other value was fixed (QA-343). No size derives them.
    """
    from gemini.modules.exchangers.cooler import Cooler

    issues = []
    for path, module in plant.named_modules():
        if not isinstance(module, Cooler) or path not in plant.feeds(f"{path}.fluid_out"):
            continue
        absent = [
            name
            for name, value in (
                ("loop_pressure", module.loop_pressure),
                ("flow", plant.input_value(join_path(path, "flow"))),
            )
            if value is None
        ]
        for name in absent:
            where = join_path("params", form.file_path(join_path(path, name)))
            issues.append(
                Issue(
                    where,
                    "missing",
                    f"{where} is missing; expected the closed loop's {name.replace('_', ' ')}: "
                    "the cooler offers the loop's first guess from loop_pressure and flow",
                    code="missing_value",
                )
            )
    return issues


PATH_LISTS = ("section_length", "section_inclination", "section_diameter", "section_roughness")
"""The lists of a well path; a producer's ``well`` and ``riser`` share all of them."""


def _split_paths(plant):
    """Return an ``incompatible`` issue for each producer whose riser and well paths differ.

    A producer with a pump inside is one path cut at ``esp_depth``: its ``well`` reads the part
    below the pump (``segment`` ``below_esp``) and its ``riser`` the part above (``above_esp``),
    both on the WHOLE path. A riser given only its own part and a well only the rest ran a
    shorter producer than the doublet's depth and drilled less than was meant (geomind QA-321:
    riser [1500] m and well [2000] m with the pump at 1500 m simulated and costed a 2000 m
    producer, 5500 m drilled for 7000 m meant).
    """
    from gemini.modules.wells import ProductionWell

    modules = dict(plant.named_modules())
    issues = []
    for path, module in modules.items():
        if not isinstance(module, ProductionWell) or _set_value(module, "segment") != "below_esp":
            continue
        riser_path = join_path(path.rsplit(".", 1)[0], "riser") if "." in path else "riser"
        riser = modules.get(riser_path)
        if not isinstance(riser, ProductionWell) or _set_value(riser, "segment") != "above_esp":
            continue
        differing = [
            name
            for name in PATH_LISTS
            if None not in (_set_value(module, name), _set_value(riser, name))
            and list(_set_value(module, name)) != list(_set_value(riser, name))
        ]
        if not differing:
            continue
        where = join_path("params", form.file_path(join_path(riser_path, differing[0])))
        issues.append(
            Issue(
                where,
                "incompatible",
                f"{where}: the riser and the well of one producer are the two segments of ONE "
                f"path cut at esp_depth, but their {', '.join(differing)} differ (riser "
                f"{list(_set_value(riser, differing[0]))}, well "
                f"{list(_set_value(module, differing[0]))}); expected both to hold the whole "
                "path, from the wellhead to the reservoir: the run and the drilling cost read "
                "only the part of each path on its side of the pump",
                code="invalid_design",
            )
        )
    return issues


def _frozen_paths(plant):
    """Return an ``incompatible`` issue for each doublet whose stated well paths miss its depth.

    A doublet derives its ``well``, ``riser`` and ``injector`` section lists from ``depth``, but a
    list stated by hand is kept as it is: a search of ``depth`` then moved the reservoir and not
    the wells (geomind QA-357: paths of 2500 m stated, the search chose 2875 m, 10000 m drilled for
    11500 m, the hydraulics at 2500 m). Named when the depth is searched (a range) while a path is
    stated, and when a stated path's true vertical extent (with ``section_inclination``) differs
    from the depth by more than a metre; a deviated well reaching the depth passes.
    """
    import math

    from gemini.plants._utils.doublet_design import WELLS
    from gemini.plants.doublet import Doublet

    ranges = plant.ranges
    issues = []
    for path, module in plant.named_modules():
        if not isinstance(module, Doublet):
            continue
        stated = [well for well in WELLS if f"{well}.section_length" in module._stated_child_params]
        if not stated:
            continue
        own = join_path(path, "depth")
        where = join_path("params", form.file_path(join_path(path, f"{stated[0]}.section_length")))
        if own in ranges or (path and "depth" in ranges and own not in module._stated_child_params):
            issues.append(
                Issue(
                    where,
                    "incompatible",
                    f"{where}: the depth of {path or 'the doublet'} is searched, but its well "
                    f"paths ({', '.join(stated)}) are stated by hand and do not follow it: a "
                    "search moves "
                    "the reservoir and not the wells. Expected the section lists left out (gemini "
                    "derives the vertical path from depth), or no range on depth",
                    code="invalid_design",
                )
            )
            continue
        depth = _set_value(module, "depth")
        if depth is None:
            continue
        for well in stated:
            child = getattr(module, well)
            lengths = _set_value(child, "section_length")
            angles = _set_value(child, "section_inclination")
            if lengths is None or angles is None:
                continue
            vertical = sum(
                float(length) * math.sin(float(angle)) for length, angle in zip(lengths, angles)
            )
            if abs(vertical - float(depth)) <= 1.0:
                continue
            spot = join_path("params", form.file_path(join_path(path, f"{well}.section_length")))
            issues.append(
                Issue(
                    spot,
                    "incompatible",
                    f"{spot}: the {well} path reaches {vertical:.1f} m true vertical depth, but "
                    f"the doublet's depth is {float(depth):.1f} m; expected the path to reach the "
                    "depth, "
                    "or the section lists left out so gemini derives them from depth",
                    code="invalid_design",
                )
            )
    return issues


def _depths(plant):
    """Return a ``missing`` issue for each doublet without a depth, before its other values.

    A doublet takes its reservoir temperature and pressure from the case only at its own depth
    (``apply_case``); without one, those values are listed as missing although the case has them
    (geomind QA-049, QA-082), so the depth is named first, as the one value to give. A doublet
    that states both by hand (``_stated``) needs no depth.
    """
    from gemini.plants.doublet import Doublet

    issues = []
    for path, module in plant.named_modules():
        if not isinstance(module, Doublet):
            continue
        if _set_value(module, "depth") is None and not _stated(module):
            where = join_path("params", form.file_path(join_path(path, "depth")))
            issues.append(
                Issue(
                    where,
                    "missing",
                    f"{where} is missing; with it the doublet takes its reservoir temperature and "
                    "pressure from the case (site.ground, site.reservoir)",
                    code="missing_value",
                )
            )
    return issues


def _stated(doublet):
    """Return whether a doublet states its reservoir's temperature and pressure by hand.

    A measured doublet (``DoubletHeatPlant``) gives its reservoir directly and takes nothing from
    the case, so it needs no depth.
    """
    reservoir = getattr(doublet, "reservoir", None)
    if reservoir is None:
        return False
    return all(_set_value(reservoir, name) is not None for name in ("temperature", "pressure"))


def _declares(module, name):
    """Return whether ``module`` has a parameter or attribute ``name``, without reading it."""
    if name in module.__dict__.get("_parameters", {}):
        return True
    try:
        return hasattr(module, name)
    except ValidationError:
        return True


def _set_value(module, name):
    """Return the value of a parameter, or ``None`` when it is unset or absent.

    Reading an unset parameter (``module.segment``) raises ``uninitialized parameters`` for the
    whole plant, so a check of an incomplete plant raised instead of returning its issues
    (geomind QA-076, gemini 0.6.5).
    """
    parameter = module.__dict__.get("_parameters", {}).get(name)
    if parameter is not None:
        return parameter.value if parameter.initialized else None
    try:
        return getattr(module, name, None)
    except ValidationError:
        return None


def _missing(path, message):
    """Return the ``missing`` issue of a value of the economics."""
    return Issue(path, "missing", message, code="missing_assumption")


def _absent(where, kind):
    """Return the ``missing`` issue of the economics value ``where`` of an equipment ``kind``."""
    path = join_path(ECONOMICS, where)
    return _missing(path, f"{path} is missing; the plant has equipment of kind {kind}")


def _kinds(plant, case):
    """Return the issues of a capex or a fixed opex that the economics lacks for a kind.

    A module with a parameter still unset is skipped: its kind may depend on that parameter, and
    ``_parameters`` already reports the missing value once. A kind the economics does not price
    (``is_priced``) needs nothing.
    """
    economics = case.economics
    if economics is None:
        return []
    kinds = sorted(
        {
            module.equipment_kind
            for _, module in plant.named_modules()
            if module.is_initialized
            and is_priced(getattr(module, "equipment_kind", None), economics)
        }
    )
    fixed = (economics.opex.fixed if economics.opex is not None else None) or {}
    found = []
    for kind in kinds:
        if getattr(economics.capex, kind, None) is None:
            found.append(_absent(f"capex.{kind}", kind))
        if fixed.get(kind) is None:
            found.append(_absent(f"opex.fixed.{kind}", kind))
    return found


def _bases(economics, kind):
    """Return the cost bases of ``kind`` that need a size other than ``cost_size()``.

    The unit of ``economics.capex.<kind>`` tells its basis, and a fixed opex per W and year needs
    the size in power; a basis per unit needs no size.
    """
    capex = None if economics.capex is None else economics.capex.leaf(kind)
    fixed = None if economics.opex is None else economics.opex.leaf(f"fixed.{kind}")
    found = {getattr(capex, "quantity", None)}
    if getattr(fixed, "quantity", None) == "annual_money_per_power":
        found.add("money_per_power")
    found.discard(EQUIPMENT_KINDS[kind][0])
    return sorted(BASIS_SIZES[quantity] for quantity in found if quantity in BASIS_SIZES)


def _sizes(plant, case):
    """Return the issues of a size that a cost on another basis needs and a module lacks."""
    if case.economics is None:
        return []
    found = {}
    for _, module in plant.named_modules():
        kind = getattr(module, "equipment_kind", None) if module.is_initialized else None
        if not is_priced(kind, case.economics):
            continue
        for size in _bases(case.economics, kind):
            found |= {item.path: item for item in _size_issues(module, size)}
    return list(found.values())


def _size_issues(module, size):
    """Return the ``missing`` issues of the size ``size`` of ``module``, in the plant file paths."""
    try:
        module.cost_size_of(size)
    except ValidationError as error:
        return [
            Issue(
                join_path("params", form.file_path(item["path"])),
                "missing",
                item["message"],
                code=item["code"],
            )
            for item in error.problems
        ]
    return []


def _roles(plant, case):
    """Return the issues of a requirement on a role the plant has no unit of."""
    found = []
    for number, requirement in enumerate(case.requirements or ()):
        if requirement.on in SUPPLY_ROLES or units_of(plant, requirement.on):
            continue
        path = f"requirements[{number}].on"
        message = (
            f"{path} = {requirement.on!r}: the plant has no unit of that role; expected a plant "
            f"with one, or no requirement {requirement.name!r}"
        )
        found.append(Issue(path, "incompatible", message))
    return found


def _states(plant, case):
    """Return the issues of the initial state: a state the case lacks, or states it misnames."""
    given = case.initial_state or {}
    found = []
    for path, module in plant.named_modules():
        found += _missing_states(path, module, given)
    for path, states in given.items():
        found += _given_states(plant, path, states)
    return found


def _missing_states(path, module, given):
    """Return the ``missing`` issues of the states of ``module`` that the case does not give."""
    wanted = module._states if module.stateful else {}
    return [
        Issue(
            join_path(join_path("initial_state", path), name),
            "missing",
            f"initial_state.{path}.{name} is missing; the plant has a stateful module there",
        )
        for name in wanted
        if name not in given.get(path, {})
    ]


def _given_states(plant, path, states):
    """Return the issues of the states the case gives to the module at ``path``."""
    where = join_path("initial_state", path)
    module = dict(plant.named_modules()).get(path)
    if module is None or not module.stateful:
        message = f"{where}: the plant has no stateful module at {path!r}"
        return [Issue(where, "unknown_key", message)]
    found = []
    for name, leaf in states.items():
        declaration = module._states.get(name)
        state = join_path(where, name)
        if declaration is None:
            message = f"{state}: no such state; expected one of {sorted(module._states)}"
            found.append(Issue(state, "unknown_key", message))
        elif units.si_unit(leaf.unit) != (declaration.unit or "-") and leaf.unit is not None:
            message = f"{state}: unit {leaf.unit!r}; expected a unit of {declaration.unit!r}"
            found.append(Issue(state, "unit", message, quantity=declaration.quantity))
    return found


def _prices(plant, case):
    """Return the issues of the prices a least-cost dispatch reads and the economics lacks."""
    economics = case.economics
    if economics is None or _dispatch(plant) != "least_cost":
        return []
    energy = economics.energy
    wanted = ["electricity"]
    if any(units_of(plant, role) for role in GAS_ROLES):
        wanted.append("gas")
    return [
        _missing(
            join_path(ECONOMICS, f"energy.{carrier}"),
            f"economics.energy.{carrier} is missing; the dispatch least_cost prices the sources",
        )
        for carrier in wanted
        if getattr(energy, carrier, None) is None
    ]


def _dispatch(plant):
    """Return the dispatch rule the plant states, or ``None``."""
    try:
        return plant.dispatch
    except (AttributeError, ValidationError):
        return None
