"""The utilities of a case: the physics of the electricity grid and of the gas grid."""

from gemini.case._utils.kinds import GRID_GAS_SPECIES
from gemini.case._utils.node import Field, Node
from gemini.case.site import FRACTION, POSITIVE


class Electricity(Node):
    """The electricity grid.

    ``co2_intensity`` [kg/J] (constant or series), the ``import_limit`` and ``export_limit`` [W] of
    the connection.
    """

    where = "utilities.electricity"
    description = "The electricity grid the plant buys from and sells to."
    fields = {
        "co2_intensity": Field(
            "mass_per_energy",
            series=True,
            bounds=POSITIVE,
            description=(
                "The CO2-equivalent emitted per energy of electricity bought, a constant or a "
                "series."
            ),
        ),
        "import_limit": Field(
            "power",
            bounds=POSITIVE,
            description="The largest power the grid connection can import.",
        ),
        "export_limit": Field(
            "power",
            bounds=POSITIVE,
            description="The largest power the grid connection can export.",
        ),
    }


class Gas(Node):
    """The gas grid.

    ``composition`` (mole fractions of the species, adding up to 1; a number, or a value with a
    unit of a fraction such as ``{"value": 20, "unit": "mol%"}``) and the ``heating_value``
    [J/kg].
    """

    where = "utilities.gas"
    description = "The gas grid the plant buys from."
    fields = {
        "composition": Field(
            keys=GRID_GAS_SPECIES,
            bounds=FRACTION,
            total=1.0,
            unit_of="fraction",
            description="The mole fraction of each species of the grid gas, adding up to 1.",
        ),
        "heating_value": Field(
            "specific_enthalpy",
            bounds=POSITIVE,
            description="The heating value of the grid gas per mass.",
        ),
    }


class Utilities(Node):
    """The electricity and the gas grid; every part is optional."""

    where = "utilities"
    description = "The electricity and the gas grid; every part optional."
    sections = {"electricity": Electricity, "gas": Gas}
