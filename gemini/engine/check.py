"""``gm.check``: what only the plant and the case together can say is missing or wrong."""

from dataclasses import replace

from gemini import units
from gemini._utils.strings import join_path
from gemini.engine.apply import apply_case
from gemini.errors import ValidationError
from gemini.errors.base import Issue, raise_issues
from gemini.modules.module import Module
from gemini.plants._utils import form
from gemini.plants.roles import units_of

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
      these issues;
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
        return _parameters(plant)
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
    return [
        *_parameters(applied),
        *_kinds(applied, case),
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
    ``_parameters`` already reports the missing value once.
    """
    economics = case.economics
    if economics is None:
        return []
    kinds = sorted(
        {
            module.equipment_kind
            for _, module in plant.named_modules()
            if module.is_initialized and getattr(module, "equipment_kind", None) is not None
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
