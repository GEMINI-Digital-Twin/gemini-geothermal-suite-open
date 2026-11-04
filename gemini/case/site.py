"""The site of a case: ground, reservoir, brine and air, the nature outside the plant boundary."""

from gemini.case._utils.access import require
from gemini.case._utils.kinds import GAS_SPECIES
from gemini.case._utils.node import Field, Node
from gemini.physics import ground
from gemini.units import inputs

POSITIVE = inputs.Range(min=0.0)
"""SI bounds of a value that is zero or more."""
FRACTION = inputs.Range(min=0.0, max=1.0)
"""SI bounds of a share."""


class Ground(Node):
    """The undisturbed ground: ``surface_temperature`` [K] and the geothermal ``gradient`` [K/m]."""

    where = "site.ground"
    description = "The undisturbed ground."
    fields = {
        "surface_temperature": Field(
            "temperature",
            bounds=POSITIVE,
            description="The undisturbed ground temperature at the surface.",
        ),
        "gradient": Field(
            "temperature_gradient",
            description=(
                "The geothermal gradient: the rise of the undisturbed rock temperature with depth."
            ),
        ),
    }


class Reservoir(Node):
    """The reservoir at its ``reference_depth`` [m].

    ``thickness`` [m], ``permeability`` [m2], ``pressure`` [Pa] and, if measured, ``temperature``
    [K] at the reference depth. Without a temperature the ground gives it.
    """

    where = "site.reservoir"
    description = "The reservoir the wells produce from and inject into."
    fields = {
        "reference_depth": Field(
            "length",
            description=(
                "The depth at which the pressure and the temperature of the reservoir are given."
            ),
        ),
        "thickness": Field(
            "length", bounds=POSITIVE, description="The thickness of the reservoir layer."
        ),
        "permeability": Field(
            "permeability", bounds=POSITIVE, description="The permeability of the reservoir rock."
        ),
        "pressure": Field(
            "pressure",
            bounds=POSITIVE,
            description="The reservoir pressure at the reference depth.",
        ),
        "temperature": Field(
            "temperature",
            bounds=POSITIVE,
            description=(
                "The measured reservoir temperature at the reference depth; without it the ground "
                "gives it."
            ),
        ),
    }


class Fluid(Node):
    """The brine the reservoir delivers.

    ``density`` [kg/m3], ``viscosity`` [Pa s], ``gas_liquid_ratio`` [-], ``dissolved_gas`` (a dict
    of the mole fraction of each species of ``GAS_SPECIES``, adding up to 1; a number, or a value
    with a unit of a fraction such as ``{"value": 20, "unit": "mol%"}``) and
    ``sand_concentration`` [kg/m3].
    """

    where = "site.fluid"
    description = "The brine the reservoir delivers."
    fields = {
        "density": Field("density", description="The density of the brine."),
        "viscosity": Field("viscosity", description="The dynamic viscosity of the brine."),
        "gas_liquid_ratio": Field(
            "gas_liquid_ratio",
            description="The free gas produced with the brine: normal m3 of gas per m3 of liquid.",
        ),
        "dissolved_gas": Field(
            keys=GAS_SPECIES,
            bounds=FRACTION,
            total=1.0,
            unit_of="fraction",
            description=(
                "The mole fraction of each species of the gas in the brine, adding up to 1."
            ),
        ),
        "sand_concentration": Field(
            "mass_concentration",
            bounds=POSITIVE,
            description="The mass of sand per volume of produced brine.",
        ),
    }


class Air(Node):
    """The outside air.

    ``temperature`` [K] and ``relative_humidity`` [-], each a constant or a series, and ``pressure``
    [Pa].
    """

    where = "site.air"
    description = "The outside air."
    fields = {
        "temperature": Field(
            "temperature",
            series=True,
            bounds=POSITIVE,
            description="The outside air temperature, a constant or a series.",
        ),
        "relative_humidity": Field(
            series=True,
            bounds=FRACTION,
            description=(
                "The relative humidity of the outside air, between 0 and 1, a constant or a "
                "series."
            ),
        ),
        "pressure": Field("pressure", bounds=POSITIVE, description="The outside air pressure."),
    }


class Site(Node):
    """Ground, reservoir, fluid and air; every part is optional.

    ``temperature_at`` and ``pressure_at`` apply the two rules of ``gemini.physics.ground``.
    """

    where = "site"
    description = (
        "The nature outside the plant boundary: ground, reservoir, brine and air; every part "
        "optional."
    )
    sections = {"ground": Ground, "reservoir": Reservoir, "fluid": Fluid, "air": Air}

    def temperature_at(self, depth):
        """Return the reservoir temperature [K] at ``depth`` [m].

        The given ``reservoir.temperature`` shifted by the gradient from the reference depth, or
        ``ground.surface_temperature + gradient * depth``. Raises ``missing_value`` naming what is
        absent.
        """
        gradient = require(self, "ground.gradient", "site")
        reference = require(self, "reservoir.reference_depth", "site")
        given = self.reservoir.temperature
        surface = None if given is not None else require(self, "ground.surface_temperature", "site")
        return float(ground.reservoir_temperature(surface, gradient, depth, reference, given))

    def pressure_at(self, depth):
        """Return the reservoir pressure [Pa] at ``depth`` [m].

        ``reservoir.pressure + fluid.density * g * (depth - reference_depth)``. Raises
        ``missing_value`` naming what is absent.
        """
        pressure = require(self, "reservoir.pressure", "site")
        reference = require(self, "reservoir.reference_depth", "site")
        density = require(self, "fluid.density", "site")
        return float(ground.reservoir_pressure(pressure, density, depth, reference))
