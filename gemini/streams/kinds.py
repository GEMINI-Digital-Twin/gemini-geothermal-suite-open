"""What a port carries, field by field: the enums of a ``Port`` and the labels they replace.

A port states its ``Direction`` and either a fluid (``gm.Fluid``) or an energy
(``gm.streams.Energy``). A stream port also has a ``Phase`` and a ``Level`` (the temperature role
of the circuit), ``ANY`` when not given; gemini's own modules state every field. ``NAMES`` are the
labels of the ports before 0.6.0 (``kind``), which a port still reports and which the descriptions
of modules keep.
"""

from enum import StrEnum

__all__ = ["names", "Direction", "Phase", "Level", "Flow"]

NAMES = (
    "brine",
    "hot_water",
    "chilled_water",
    "gas",
    "electricity",
    "fuel",
    "heat",
    "air",
    "waste",
    "chemical",
)
"""Every port label; ``electricity`` and ``heat`` label ports that carry a ``Power`` value."""


class Direction(StrEnum):
    """Whether a port takes (``IN``) or gives (``OUT``)."""

    IN = "in"
    OUT = "out"


class Phase(StrEnum):
    """The phase of the fluid of a stream port."""

    LIQUID = "liquid"
    GAS = "gas"
    TWO_PHASE = "two_phase"
    ANY = "any"


class Level(StrEnum):
    """The temperature role of the circuit of a stream port."""

    HOT = "hot"
    WARM = "warm"
    COOL = "cool"
    CHILLED = "chilled"
    AMBIENT = "ambient"
    GEOTHERMAL = "geothermal"
    ANY = "any"


class Flow(StrEnum):
    """Who sets what a port carries: the giver (``IMPOSED``) or the taker (``DRAWN``)."""

    IMPOSED = "imposed"
    DRAWN = "drawn"


def names():
    """Return the stream types."""
    return list(NAMES)


def label(stream, phase, fluid, level, energy):
    """Return the label of a port before 0.6.0 (``kind``), or ``None`` for one of any fluid.

    ``fluid`` is the family of the port's fluid (``Fluid.family``) or ``"any"``.
    """
    if not stream:
        return None if energy == "any" else energy
    if fluid == "water":
        return "chilled_water" if level is Level.CHILLED else "hot_water"
    found = {"brine": "brine", "air": "air", "waste": "waste", "chemical": "chemical"}.get(fluid)
    if found is not None:
        return found
    if phase is Phase.GAS or fluid in ("steam", "flue_gas", "natural_gas"):
        return "gas"
    return {Level.HOT: "hot_water", Level.WARM: "hot_water", Level.CHILLED: "chilled_water"}.get(
        level
    )
