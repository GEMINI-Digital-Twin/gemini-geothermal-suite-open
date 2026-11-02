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
    fields = {
        "surface_temperature": Field("temperature", bounds=POSITIVE),
        "gradient": Field("temperature_gradient"),
    }


class Reservoir(Node):
    """The reservoir at its ``reference_depth`` [m].

    ``thickness`` [m], ``permeability`` [m2], ``pressure`` [Pa] and, if measured, ``temperature``
    [K] at the reference depth. Without a temperature the ground gives it.
    """

    where = "site.reservoir"
    fields = {
        "reference_depth": Field("length"),
        "thickness": Field("length", bounds=POSITIVE),
        "permeability": Field("permeability", bounds=POSITIVE),
        "pressure": Field("pressure", bounds=POSITIVE),
        "temperature": Field("temperature", bounds=POSITIVE),
    }


class Fluid(Node):
    """The brine the reservoir delivers.

    ``density`` [kg/m3], ``viscosity`` [Pa s], ``gas_liquid_ratio`` [-], ``dissolved_gas`` (a dict
    of the mole fraction of each species of ``GAS_SPECIES``, adding up to 1) and
    ``sand_concentration`` [kg/m3].
    """

    where = "site.fluid"
    fields = {
        "density": Field("density"),
        "viscosity": Field("viscosity"),
        "gas_liquid_ratio": Field("gas_liquid_ratio"),
        "dissolved_gas": Field(keys=GAS_SPECIES, bounds=FRACTION, total=1.0),
        "sand_concentration": Field("mass_concentration", bounds=POSITIVE),
    }


class Air(Node):
    """The outside air.

    ``temperature`` [K] and ``relative_humidity`` [-], each a constant or a series, and ``pressure``
    [Pa].
    """

    where = "site.air"
    fields = {
        "temperature": Field("temperature", series=True, bounds=POSITIVE),
        "relative_humidity": Field(series=True, bounds=FRACTION),
        "pressure": Field("pressure", bounds=POSITIVE),
    }


class Site(Node):
    """Ground, reservoir, fluid and air; every part is optional.

    ``temperature_at`` and ``pressure_at`` apply the two rules of ``gemini.physics.ground``.
    """

    where = "site"
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
