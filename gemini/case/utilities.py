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
    fields = {
        "co2_intensity": Field("mass_per_energy", series=True, bounds=POSITIVE),
        "import_limit": Field("power", bounds=POSITIVE),
        "export_limit": Field("power", bounds=POSITIVE),
    }


class Gas(Node):
    """The gas grid.

    ``composition`` (mole fractions of the species, adding up to 1; a number, or a value with a
    unit of a fraction such as ``{"value": 20, "unit": "mol%"}``) and the ``heating_value``
    [J/kg].
    """

    where = "utilities.gas"
    fields = {
        "composition": Field(keys=GRID_GAS_SPECIES, bounds=FRACTION, total=1.0, unit_of="fraction"),
        "heating_value": Field("specific_enthalpy", bounds=POSITIVE),
    }


class Utilities(Node):
    """The electricity and the gas grid; every part is optional."""

    where = "utilities"
    sections = {"electricity": Electricity, "gas": Gas}
