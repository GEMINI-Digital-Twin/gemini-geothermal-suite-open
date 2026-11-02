"""What a study may vary: a value of the plant, or a value of the case named ``case.<path>``."""

import numpy as np

from gemini import units
from gemini._utils.strings import join_names
from gemini.case._utils.node import si_unit_of
from gemini.errors import ValidationError
from gemini.modules.declarations import Parameter

CASE_PREFIX = "case."
"""A name that starts with it is a value of the case, by its path in ``case.json``."""


def is_case_name(name):
    """Whether ``name`` is a value of the case: ``case.`` and the path of the value."""
    return name.startswith(CASE_PREFIX)


def _missing(name):
    return ValidationError(
        f"{name} is missing; expected a value in the case (it has no default)",
        path=name,
        code="missing_value",
    )


def _present(case, path, name):
    """Raise ``missing_value`` when a section above the value at ``path`` is absent."""
    parts = path.split(".")
    node = getattr(case, parts[0], None)
    for part in parts[1:-1]:
        if node is None:
            break
        if part not in getattr(node, "sections", ()):
            return
        node = getattr(node, part)
    if node is None:
        raise _missing(name)


def _not_a_number(name, detail):
    """Return the error of a path that holds no number of the case."""
    return ValidationError(
        f"{name} is not a number of the case; expected the path of a quantity, such as "
        f"case.economics.energy.electricity{detail}",
        path=name,
        code="invalid_value",
    )


def case_field(case, name):
    """Return ``(field, current)`` of the value ``case.<path>``: its field and its SI value.

    ``field`` is the ``Field`` of the value (its quantity and bounds); ``current`` is ``None`` when
    the value is absent and the mean of the steps for a series. A section above it that is absent
    raises ``missing_value``. A path that is no number of the case (a text, a table, a date)
    raises ``invalid_value``; an unknown part raises ``unknown_name``.
    """
    path = name.removeprefix(CASE_PREFIX)
    try:
        field = case.field(path)
    except ValidationError as error:
        raise ValidationError(
            str(error).replace(path, name, 1), path=name, code=error.code
        ) from error
    _present(case, path, name)
    if field.text:
        raise _not_a_number(name, "")
    if field.keys and path.rpartition(".")[2] not in field.keys:
        raise _not_a_number(name, f" (a table of {join_names(field.keys)}: name one of them)")
    leaf = case.leaf(path)
    return field, None if leaf is None else _number(leaf.si)


def _number(value):
    """Return ``value`` as a float, the mean of an array."""
    return float(np.mean(value))


def with_case_values(case, values):
    """Return a copy of ``case`` with the SI numbers ``{case.<path>: number}`` set.

    A profile becomes the constant. A number that breaks the bounds of its field raises
    ``out_of_bounds``.
    """
    for name, number in values.items():
        case_field(case, name)
        case = case.with_value(name.removeprefix(CASE_PREFIX), number)
    return case


def _declaration(plant, name):
    """Return the parameter declaration of ``name``, or raise for a name that is no parameter."""
    declaration = plant.get(name)
    if not isinstance(declaration, Parameter):
        raise ValidationError(
            f"study: {name} is not a parameter of the plant; expected a parameter, or a value of "
            f"the case as {CASE_PREFIX}<path>",
            path=name,
            code="invalid_value",
        )
    return declaration


def check_name(plant, case, name):
    """Raise unless ``name`` is a parameter of the plant or a number of the case."""
    if is_case_name(name):
        case_field(case, name)
        return
    _declaration(plant, name)


def unit_of(plant, case, name):
    """Return the SI unit of the value ``name`` as text, ``-`` for a number without a dimension."""
    if is_case_name(name):
        return _case_unit(case, name) or "-"
    return _declaration(plant, name).unit or "-"


def value_si(plant, case, name, bound, difference=False):
    """Return ``bound``, a ``Quantity`` or its dict, in the SI unit of the value ``name``.

    A plain number is accepted only for a value without a dimension. A ``difference`` is a spread
    such as a standard deviation, which a unit offset does not move.
    """
    if is_case_name(name):
        field, _ = case_field(case, name)
        unit, quantity, what = _case_unit(case, name), field.quantity, "the value"
    else:
        declaration = _declaration(plant, name)
        unit, quantity, what = declaration.unit, declaration.quantity, "the parameter"
    if isinstance(bound, dict):
        bound = units.Quantity.from_dict(bound)
    if isinstance(bound, units.Quantity):
        number = units.value_in_si(bound, unit, name, quantity)
        return number - units.to_si(0, bound.unit) if difference else number
    if unit not in (None, "-"):
        raise ValidationError(
            f"study: {name} = {bound!r}; expected {units.QUANTITY_FORM}, because {what} "
            f"has the unit {unit!r}",
            path=name,
            code="invalid_value",
        )
    return bound


def _case_unit(case, name):
    """Return the SI unit of the number ``name`` of the case, ``None`` without a dimension."""
    quantity = case_field(case, name)[0].quantity
    return None if quantity is None else si_unit_of(quantity)


def quantities(plant, case, values):
    """Return ``{name: Quantity}`` for SI values, each in the SI unit of its value."""
    return {
        name: units.Quantity(number, unit_of(plant, case, name)) for name, number in values.items()
    }


def quantity_of(plant, case, name):
    """Return the quantity (``"temperature"``, ``"temperature_difference"``, ...) of ``name``."""
    if is_case_name(name):
        return case_field(case, name)[0].quantity
    return _declaration(plant, name).quantity
