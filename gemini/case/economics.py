"""The economics of a case: all money conditions and the reporting conventions."""

from pathlib import Path

import numpy as np

from gemini import units
from gemini._utils.strings import join_path
from gemini.case._utils import schema
from gemini.case._utils.access import require
from gemini.case._utils.kinds import EQUIPMENT_KINDS
from gemini.case._utils.node import Field, Frozen, Node, issue, load, write
from gemini.case.site import FRACTION, POSITIVE
from gemini.errors import ValidationError
from gemini.units import inputs

HEADER = ("format", "kind", "name")
TABLE_KEYS = ("depth", "cost_per_metre")


class DepthTable(Frozen):
    """Drilling cost per metre by measured depth: ``depth`` [m] rising, ``cost`` [currency/m].

    ``at`` interpolates linearly and never extrapolates. ``to_json`` writes the table as given.
    """

    def __init__(self, given, depth, cost):
        """Build from what ``Capex`` read."""
        self._set(_given=given, depth=depth, cost=cost)

    def at(self, length):
        """Return the cost per metre [currency/m] at the measured ``length`` [m].

        Raises ``out_of_bounds`` for a length outside the table.
        """
        if length < self.depth[0] or length > self.depth[-1]:
            raise ValidationError(
                f"economics.capex.drilling: length = {length} m is outside the table of "
                f"{self.depth[0]} to {self.depth[-1]} m; expected a length inside it (no "
                "extrapolation)",
                path="economics.capex.drilling",
                code="out_of_bounds",
            )
        return float(np.interp(length, self.depth, self.cost))

    def to_json(self):
        """Return the table as it was read."""
        return {key: dict(value) for key, value in self._given.items()}

    @classmethod
    def read(cls, data, path, issues):
        """Return the table of ``data`` or ``None`` with issues appended."""
        before = len(issues)
        inputs.check_keys(data, TABLE_KEYS, path, issues)
        columns = {
            key: _column(data.get(key), join_path(path, key), quantity, issues)
            for key, quantity in zip(TABLE_KEYS, ("length", "money_per_length"))
        }
        if len(issues) > before:
            return None
        depth, cost = columns["depth"], columns["cost_per_metre"]
        if len(depth) != len(cost) or len(depth) < 2 or np.any(np.diff(depth) <= 0):
            issue(
                issues,
                path,
                "incompatible",
                f"{path}: depth and cost_per_metre need the same number of at least 2 values, "
                "with depth rising",
            )
            return None
        return cls({key: data[key] for key in TABLE_KEYS}, depth, cost)


def _column(data, path, quantity, issues):
    """Return the SI array of a list of numbers with a unit, or ``None`` with issues."""
    if not isinstance(data, dict) or not isinstance(data.get("value"), list) or not data["value"]:
        issue(
            issues,
            path,
            "incompatible",
            f"{path} = {data!r}; expected {{'value': [...], 'unit': ...}}",
        )
        return None
    before = len(issues)
    leaves = [
        inputs.from_leaf(
            {**data, "value": number}, path, issues, quantity=quantity, bounds=POSITIVE
        )
        for number in data["value"]
    ]
    if any(not isinstance(n, (int, float)) or isinstance(n, bool) for n in data["value"]):
        issue(issues, path, "incompatible", f"{path}.value: expected numbers")
    if len(issues) > before:
        return None
    return np.asarray(
        units.array_to_si(np.asarray(data["value"], dtype=float), leaves[0].unit, quantity)
    )


class Capex(Node):
    """One capex factor per equipment kind, each per capacity, per metre or a fixed amount.

    The fields are the equipment kinds of ``gemini.case._utils.kinds.EQUIPMENT_KINDS``, each with
    its cost basis: per W of capacity, per metre, per W/K, per m3, or a fixed amount, as a
    ``{"value", "unit"}`` in ``currency``. ``drilling`` may instead be a table by depth,
    ``{"depth": {"value": [...], "unit": "m"}, "cost_per_metre": {"value": [...], "unit":
    "EUR/m"}}``, which ``Economics.drilling_cost_per_metre`` interpolates.
    """

    where = "economics.capex"
    fields = {
        kind: Field(quantity, bounds=POSITIVE) for kind, (quantity, _) in EQUIPMENT_KINDS.items()
    }

    @classmethod
    def _field_from(cls, name, field, data, path, ctx):
        """Read a field; ``drilling`` may be a depth table."""
        raw = data.get(name)
        if name == "drilling" and isinstance(raw, dict) and "depth" in raw:
            table = DepthTable.read(raw, path, ctx.issues)
            return None if table is None else (table, table)
        return super()._field_from(name, field, data, path, ctx)


class Variable(Node):
    """Consumables priced by the market: ``chemical`` and ``waste_disposal`` [currency/kg]."""

    where = "economics.opex.variable"
    fields = {
        "chemical": Field("money_per_mass", series=True, bounds=POSITIVE),
        "waste_disposal": Field("money_per_mass", series=True, bounds=POSITIVE),
    }


class Opex(Node):
    """Operating costs.

    ``fixed`` is a dict of the yearly share [1/yr] of the capex of each kind; ``variable`` holds the
    consumables.
    """

    where = "economics.opex"
    fields = {"fixed": Field("annual_rate", keys=tuple(EQUIPMENT_KINDS), bounds=POSITIVE)}
    sections = {"variable": Variable}


class Energy(Node):
    """The price of what is bought: ``electricity`` and ``gas`` [currency/J], constant or series."""

    where = "economics.energy"
    fields = {
        "electricity": Field("money_per_energy", series=True, bounds=POSITIVE),
        "gas": Field("money_per_energy", series=True, bounds=POSITIVE),
    }


class Carbon(Node):
    """The ``price`` of a mass of CO2-equivalent [currency/kg], constant or series."""

    where = "economics.carbon"
    fields = {"price": Field("money_per_mass", series=True, bounds=POSITIVE)}


class Subsidy(Node):
    """A subsidy: the ``amount`` paid per year [currency/yr] for a ``duration`` [s]."""

    where = "economics.revenue.subsidy"
    fields = {
        "amount": Field("annual_money", bounds=POSITIVE),
        "duration": Field("duration", bounds=POSITIVE),
    }


class Revenue(Node):
    """What a unit of delivered ``heat`` and ``cold`` earns [currency/J], and the ``subsidy``."""

    where = "economics.revenue"
    fields = {
        "heat": Field("money_per_energy", series=True, bounds=POSITIVE),
        "cold": Field("money_per_energy", series=True, bounds=POSITIVE),
    }
    sections = {"subsidy": Subsidy}


class Allocation(Node):
    """How a plant that delivers heat and cold shares its cost: ``heat_cost_share`` [-]."""

    where = "economics.accounting.allocation"
    fields = {"heat_cost_share": Field(bounds=FRACTION)}


class Gwp(Node):
    """The global warming potentials: the ``standard`` that names the set, and ``CH4`` [-]."""

    where = "economics.accounting.gwp"
    fields = {"standard": Field(text=True), "CH4": Field(bounds=POSITIVE)}


class Accounting(Node):
    """The conventions of the report: the cost ``allocation`` and the ``gwp`` set."""

    where = "economics.accounting"
    sections = {"allocation": Allocation, "gwp": Gwp}


class Economics(Node):
    """All money: currency label, rates, analysis period, prices, revenue and conventions.

    Usable alone (``Economics.from_json``) and held by ``Case.economics``. Nothing has a default:
    a value that is absent is ``None``.

    Attributes
    ----------
    name : str
        The name of the file; metadata.
    currency : str or None
        A label for every amount; nothing converts between currencies.
    price_year : int or None
        The year the prices are in.
    discount_rate : float or None
        Real discount rate per year [-].
    analysis_period : float or None
        Years of the analysis, in seconds.
    """

    where = "economics"
    fields = {
        "currency": Field(text=True),
        "price_year": Field(integer=True),
        "discount_rate": Field(bounds=POSITIVE),
        "analysis_period": Field("duration", bounds=POSITIVE),
    }
    sections = {
        "capex": Capex,
        "opex": Opex,
        "energy": Energy,
        "carbon": Carbon,
        "revenue": Revenue,
        "accounting": Accounting,
    }

    @classmethod
    def read(cls, data, path, ctx, header=()):
        """Return the economics of ``data`` (an object or a file path) or ``None`` with issues.

        A wrong ``name`` or ``format`` does not stop the read: the values are still judged.
        """
        data, source = inputs.from_section(data, path, ctx.source, ctx.issues)
        if data is None:
            return None
        head = inputs.from_header(data, "economics", path, ctx.issues)
        if head is None and not (isinstance(data, dict) and data.get("kind") == "economics"):
            return None
        found = super().read(data, path, ctx.at(source), HEADER)
        if head is None:
            return None
        if found is not None:
            found._set(name=head.name)
        return found

    def to_dict(self):
        """Return the economics as it was read, the header first."""
        head = {"format": inputs.FORMAT, "kind": "economics", "name": self.name}
        return head | super().to_dict()

    @classmethod
    def from_json(cls, path, time=None):
        """Return the economics of a JSON file, its CSV files read from the same folder.

        ``time`` is the ``Time`` of a case, needed only for a price given as a series.
        Raises ``ValidationError`` carrying every issue found.
        """
        path = Path(path)
        return cls._load(load(path), None, path.parent, time)

    def to_json(self, path):
        """Write the file and, next to it, the CSV files of its series."""
        write(path, self.to_dict(), self.files())

    @classmethod
    def schema(cls):
        """Return the JSON Schema (draft 2020-12) of ``economics.json``."""
        return {"$schema": schema.DRAFT, "title": cls.__name__} | schema.section(cls, "economics")

    def drilling_cost_per_metre(self, length):
        """Return the drilling cost per metre [currency/m] for a well of measured ``length`` [m].

        A constant ``capex.drilling`` is returned as it is; a depth table is interpolated linearly
        and a length outside it raises ``out_of_bounds``. Raises ``missing_assumption`` when the
        economics has no drilling cost.
        """
        drilling = require(self, "capex.drilling", "economics")
        return drilling.at(length) if isinstance(drilling, DepthTable) else drilling
