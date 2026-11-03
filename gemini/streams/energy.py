"""The forms of power a power port carries, as ``Fluid`` gives the fluids of a stream port.

``gm.units.Energy`` is the quantity of an amount of energy and ``gm.case.Energy`` the prices of
the economics; this is neither.
"""

from gemini.errors import ValidationError


class Energy:
    """The form of the power of a power port: ``Energy.ELECTRICITY``, ``HEAT`` or ``FUEL``.

    ``Energy.ANY`` is the energy of a port that takes any.

    A form is its ``name``, with the ``unit`` of its power (W); two forms are equal by name.
    ``Energy.of`` returns the preset of a name.
    """

    ELECTRICITY = HEAT = FUEL = ANY = None

    def __init__(self, name, unit="W"):
        """Make the form called ``name``; gemini's presets are the class attributes."""
        self.name, self.unit = name, unit

    def __eq__(self, other):
        """Return whether ``other`` is this form, or its name."""
        if isinstance(other, Energy):
            return other.name == self.name
        return isinstance(other, str) and other == self.name

    def __hash__(self):
        """Return the hash of the name."""
        return hash(self.name)

    def __repr__(self):
        """Return ``Energy.NAME``."""
        return f"Energy.{self.name.upper()}"

    def to_dict(self):
        """Return the form as plain JSON."""
        return {"name": self.name, "unit": self.unit}

    @classmethod
    def presets(cls):
        """Return the forms gemini knows, by name."""
        return {item.name: item for item in (cls.ELECTRICITY, cls.HEAT, cls.FUEL, cls.ANY)}

    @classmethod
    def of(cls, value):
        """Return the preset of a form or of its name; an unknown one is ``invalid_value``."""
        name = value.name if isinstance(value, cls) else value
        found = cls.presets().get(name)
        if found is None:
            raise ValidationError(
                f"energy = {value!r}; expected one of {sorted(cls.presets())}",
                code="invalid_value",
            )
        return found


Energy.ELECTRICITY = Energy("electricity")
Energy.HEAT = Energy("heat")
Energy.FUEL = Energy("fuel")
Energy.ANY = Energy("any")
