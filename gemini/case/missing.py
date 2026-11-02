"""What a case still lacks, read from a case or from a document that is not complete yet."""

from gemini import units
from gemini._utils.strings import join_names, join_path
from gemini.case.case import SECTIONS, Case
from gemini.case.economics import Economics
from gemini.errors.base import Issue
from gemini.units import inputs

HEADER = ("format", "kind", "name")
TIME = ("start", "end", "step")
REQUIREMENT = ("name", "on", "quantity")


def _absent(path, quantity=None, expected=None, code=None):
    """Return the ``missing`` issue of the value at ``path``, with its quantity and its units."""
    accepted = () if quantity is None else tuple(units.names(quantity))
    message = f"{path} is missing"
    if expected is not None:
        message += f"; expected {expected}"
    if quantity is not None:
        message += f"; a {quantity} in one of {join_names(accepted)}"
    return Issue(path, "missing", message, quantity=quantity, accepted=accepted, code=code)


def _header(data, kind, path=""):
    """Return the issues of the keys every file starts with: ``format``, ``kind`` and ``name``."""
    expected = {"format": str(inputs.FORMAT), "kind": f'"{kind}"', "name": "a text"}
    return [
        _absent(join_path(path, key), expected=expected[key]) for key in HEADER if key not in data
    ]


def _time(data):
    """Return the issues of the ``time`` section: its three keys, the step in a duration."""
    given = data if isinstance(data, dict) else {}
    return [
        _absent(join_path("time", key), "duration" if key == "step" else None)
        for key in TIME
        if key not in given
    ]


def _section(cls, data, path, code=None):
    """Return the issues of the required leaves of a section and of the children it holds."""
    found = [
        _absent(join_path(path, name), field.quantity, code=code)
        for name, field in cls.fields.items()
        if field.required and name not in data
    ]
    for name, sub in cls.sections.items():
        if isinstance(data.get(name), dict):
            found += _section(sub, data[name], join_path(path, name), code)
    return found


def _requirements(data):
    """Return the issues of the keys a requirement cannot do without."""
    return [
        _absent(f"requirements[{number}].{key}")
        for number, item in enumerate(data if isinstance(data, list) else ())
        if isinstance(item, dict)
        for key in REQUIREMENT
        if key not in item
    ]


def missing(case):
    """Return what a case does not have yet: the paths a form still has to ask for.

    It reads a ``Case`` or a plain dict that is not complete, which ``Case.from_dict`` would
    refuse, and never raises. It lists what the file needs by itself: the header (``format``,
    ``kind``, ``name``), the three keys of ``time``, the leaves that a section requires when the
    section is given (the ``power`` of a service), the header of an economics given in the case,
    and the keys of each requirement. What a plant needs from the case (a ground temperature, a
    price) depends on the plant: ``gm.check(plant, case)`` lists it once the case reads.

    Parameters
    ----------
    case : Case or dict
        A case, or a case document, possibly without parts. A part given as the path of a file
        is not looked into; anything that is not a mapping counts as an empty document.

    Returns
    -------
    list of Issue
        One ``Issue`` of kind ``missing`` per value, in the order of ``case.json``: ``path`` the
        place in the document, ``quantity`` and ``accepted`` the quantity and the units of a value
        with a dimension (``time.step`` is a duration), the other two empty. The same shape as
        ``Case.check()``; an empty list means that nothing the file itself needs is absent.
    """
    data = case.to_dict() if isinstance(case, Case) else case
    data = data if isinstance(data, dict) else {}
    found = _header(data, "case") + _time(data.get("time"))
    for name, cls in SECTIONS.items():
        if isinstance(data.get(name), dict):
            found += _section(cls, data[name], name)
    economics = data.get("economics")
    if isinstance(economics, dict):
        found += _header(economics, "economics", "economics")
        found += _section(Economics, economics, "economics", "missing_assumption")
    return found + _requirements(data.get("requirements"))
