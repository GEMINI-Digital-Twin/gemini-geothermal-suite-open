"""The economics of a case: all money conditions and the reporting conventions."""

from pathlib import Path

import numpy as np

from gemini import units
from gemini._utils.strings import join_path
from gemini.case._utils import schema
from gemini.case._utils.access import require
from gemini.case._utils.kinds import CAPEX_BASES, EQUIPMENT_KINDS
from gemini.case._utils.node import Field, Frozen, Node, issue, load, write
from gemini.case.site import FRACTION, POSITIVE
from gemini.errors import ValidationError
from gemini.units import inputs

HEADER = ("format", "kind", "name")
TABLE_KEYS = ("depth", "cost_per_metre")
EXAMPLE_UNITS = {
    "money": "EUR",
    "money_per_power": "EUR/W",
    "money_per_length": "EUR/m",
    "money_per_conductance": "EUR/(W/K)",
    "money_per_volume": "EUR/m3",
    "money_per_energy": "EUR/MWh",
}
"""A unit of each cost basis, named in the descriptions of the schema; ``x-units`` lists all."""


def _capex_text(kind, quantity, basis):
    """Return the description of ``capex.<kind>``: its bases, each with a unit of it."""
    bases = {quantity: basis} | CAPEX_BASES.get(kind, {})
    text = f"Investment in the equipment kind {kind}: " + ", or ".join(
        f"{told} ({EXAMPLE_UNITS[name]})" for name, told in bases.items()
    )
    if kind == "drilling":
        text += ", or a table of the cost per metre by measured depth"
    return text + ("; the unit tells the basis" if len(bases) > 1 else "")


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
    ``{"value", "unit"}`` in ``currency``. Some kinds accept another basis
    (``gemini.case._utils.kinds.CAPEX_BASES``: a heat exchanger per W of nominal duty, a storage
    per J stored, a production pump per unit), and the unit of the factor tells which.
    ``drilling`` may instead be a table by depth, ``{"depth": {"value": [...], "unit": "m"},
    "cost_per_metre": {"value": [...], "unit": "EUR/m"}}``, which
    ``Economics.drilling_cost_per_metre`` interpolates.
    """

    where = "economics.capex"
    description = (
        "The capex factor of each equipment kind: the investment per unit of the size the kind "
        "is priced by; a kind a plant uses and the economics lacks raises missing_assumption"
    )
    fields = {
        kind: Field(
            quantity,
            bounds=POSITIVE,
            description=_capex_text(kind, quantity, basis),
            alternatives=tuple(CAPEX_BASES.get(kind, ())),
        )
        for kind, (quantity, basis) in EQUIPMENT_KINDS.items()
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
    description = (
        "The consumables priced by the market, per kg; the names accepted are chemical and "
        "waste_disposal and no other"
    )
    fields = {
        "chemical": Field(
            "money_per_mass",
            series=True,
            bounds=POSITIVE,
            description=(
                "Price of the chemical products a plant draws from its ChemicalGrid, per kg of "
                "product (EUR/kg, EUR/t): every dosed product, a scale or a corrosion inhibitor "
                "of an InhibitorDosing alike; constant or a series"
            ),
        ),
        "waste_disposal": Field(
            "money_per_mass",
            series=True,
            bounds=POSITIVE,
            description=(
                "Cost of disposing of the waste a plant sends to its WasteGrid (sand, scale, "
                "blowdown), per kg (EUR/kg, EUR/t); constant or a series"
            ),
        ),
    }


class Opex(Node):
    """Operating costs.

    ``fixed`` is a dict of the yearly share [1/yr] of the capex of each kind; ``variable`` holds the
    consumables.
    """

    where = "economics.opex"
    description = "The operating costs besides the energy bought: fixed per kind, and consumables"
    fields = {
        "fixed": Field(
            "annual_rate",
            keys=tuple(EQUIPMENT_KINDS),
            bounds=POSITIVE,
            description=(
                "Fixed operation and maintenance of each equipment kind, a share of its capex "
                "per year (%/yr, 1/yr); a kind a plant uses and the map lacks raises "
                "missing_assumption"
            ),
        )
    }
    sections = {"variable": Variable}


class Energy(Node):
    """The price of what is bought: ``electricity`` and ``gas`` [currency/J], constant or series."""

    where = "economics.energy"
    description = "The price of the energy a plant buys"
    fields = {
        "electricity": Field(
            "money_per_energy",
            series=True,
            bounds=POSITIVE,
            description=(
                "Price of the electricity bought from the grid (EUR/MWh, EUR/kWh); constant or a "
                "series"
            ),
        ),
        "gas": Field(
            "money_per_energy",
            series=True,
            bounds=POSITIVE,
            description=(
                "Price of the gas bought from the grid, per energy of its lower heating value "
                "(EUR/MWh, EUR/kWh); constant or a series. Co-produced gas costs nothing"
            ),
        ),
    }


class Carbon(Node):
    """The ``price`` of a mass of CO2-equivalent [currency/kg], constant or series."""

    where = "economics.carbon"
    description = "The price of the CO2-equivalent a plant emits"
    fields = {
        "price": Field(
            "money_per_mass",
            series=True,
            bounds=POSITIVE,
            description=(
                "Price of a mass of CO2-equivalent emitted, added to the opex (EUR/t, EUR/kg); "
                "constant or a series"
            ),
        )
    }


class Subsidy(Node):
    """A subsidy: the ``amount`` paid per year [currency/yr] for a ``duration`` [s]."""

    where = "economics.revenue.subsidy"
    description = (
        "A subsidy paid on top of the revenue from the first year; it earns nothing unless both "
        "amount and duration are given"
    )
    fields = {
        "amount": Field(
            "annual_money",
            bounds=POSITIVE,
            description="The subsidy paid per year (EUR/yr, MEUR/yr)",
        ),
        "duration": Field(
            "duration",
            bounds=POSITIVE,
            description="How long the subsidy is paid (yr), within the analysis period",
        ),
    }


class Revenue(Node):
    """What a unit of delivered ``heat`` and ``cold`` earns [currency/J], and the ``subsidy``."""

    where = "economics.revenue"
    description = "What the energy a plant delivers earns, and a subsidy"
    fields = {
        "heat": Field(
            "money_per_energy",
            series=True,
            bounds=POSITIVE,
            description=(
                "Price of the useful heat delivered (EUR/MWh, EUR/kWh); constant or a series"
            ),
        ),
        "cold": Field(
            "money_per_energy",
            series=True,
            bounds=POSITIVE,
            description=(
                "Price of the useful cold delivered (EUR/MWh, EUR/kWh); constant or a series"
            ),
        ),
    }
    sections = {"subsidy": Subsidy}


class Allocation(Node):
    """How a plant that delivers heat and cold shares its cost: ``heat_cost_share`` [-]."""

    where = "economics.accounting.allocation"
    description = "How the cost of a plant that delivers heat and cold is split between them"
    fields = {
        "heat_cost_share": Field(
            bounds=FRACTION,
            description=(
                "Share of the cost charged to the heat, between 0 and 1 (no unit); lcoc gets "
                "the rest"
            ),
        )
    }


class Gwp(Node):
    """The global warming potentials: the ``standard`` that names the set, and ``CH4`` [-]."""

    where = "economics.accounting.gwp"
    description = "The global warming potentials of the CO2-equivalent, and the set they come from"
    fields = {
        "standard": Field(
            text=True, description="The name of the set of global warming potentials (text)"
        ),
        "CH4": Field(
            bounds=POSITIVE,
            description="Global warming potential of methane, kg CO2 per kg CH4 (no unit)",
        ),
    }


class Accounting(Node):
    """The conventions of the report: the cost ``allocation`` and the ``gwp`` set."""

    where = "economics.accounting"
    description = "The conventions a report cannot be built without"
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
    description = (
        "All money conditions of a case and the conventions of its report; nothing has a default"
    )
    fields = {
        "currency": Field(
            text=True,
            description="A label of the currency of every amount (text); nothing converts it",
        ),
        "price_year": Field(
            integer=True, description="The year the prices are in (a whole number, no unit)"
        ),
        "discount_rate": Field(
            bounds=POSITIVE,
            description="Real discount rate per year, as a fraction (0.05 is 5 %; no unit)",
        ),
        "analysis_period": Field(
            "duration", bounds=POSITIVE, description="The years of the analysis (yr)"
        ),
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
        """Return the economics of ``data`` (an object or a file path) or ``None`` with issues."""
        data, source = inputs.from_section(data, path, ctx.source, ctx.issues)
        if data is None:
            return None
        head = inputs.from_header(data, "economics", path, ctx.issues)
        if head is None:
            return None
        found = super().read(data, path, ctx.at(source), HEADER)
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
