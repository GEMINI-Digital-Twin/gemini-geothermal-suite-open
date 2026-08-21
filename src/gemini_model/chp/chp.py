"""Gas-fired combined heat and power (CHP) model.

Estimates the electrical power, heat output and CO2 emissions of a
gas-fired CHP unit that burns a mixture of gas co-produced with a
doublet's flow and gas supplied from the grid. Typically operated
alongside a ``Boiler`` (see :mod:`gemini_model.boiler.boiler`), sharing
the same gas and secondary flow streams via complementary fractions.
"""

from gemini_model.model_abstract import StaticModel


class CHP(StaticModel):
    """Gas-fired CHP electrical/heat output and emission model."""

    DEFAULT_GAS_DENSITY = 0.7  # kg/Nm3
    DEFAULT_FLUID_DENSITY = 1050.0  # kg/m3
    DEFAULT_SPECIFIC_HEAT = 4200.0  # J/(kg.K)
    JOULE_PER_GJ = 1e9
    ELECTRICAL_POWER_FRACTION = 1 / 3  # fraction of fuel power converted to electricity
    _MIN_MASS_FLOW = 1e-9  # kg/s, guards against division by zero

    def __init__(self):
        """Model initialization."""
        self.parameters = {}
        self.output = {}

    def update_parameters(self, parameters):
        """Update model parameters.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model.
        """
        for key, value in parameters.items():
            self.parameters[key] = value

    def initialize_state(self, x):
        """Generate an initial state based on user parameters."""
        pass

    def update_state(self, u, x):
        """Update the state based on input u and state x."""
        pass

    def calculate_output(self, u, x=None):
        """Calculate output based on input u.

        ``u["burner_modulation"]`` is the fraction (0-1) of the available
        gas burned by a co-located boiler; the CHP unit burns the
        remainder, ``1 - burner_modulation``. Similarly,
        ``u["secondary_valve_position"]`` is the fraction (0-1) of the
        secondary-side flow routed through the boiler; the CHP unit
        receives the remainder, ``1 - secondary_valve_position``.
        """
        temperature_in = u["temperature_in"]
        primary_flow_rate = u["primary_flow_rate"]
        secondary_flow_rate = u["secondary_flow_rate"]
        chp_gas_fraction = 1 - u["burner_modulation"]
        chp_flow_fraction = 1 - u["secondary_valve_position"]
        grid_gas_flow_rate = u["grid_gas_flow_rate"]

        gas_density = self.parameters.get("gas_density", self.DEFAULT_GAS_DENSITY)
        fluid_density = self.parameters.get("fluid_density", self.DEFAULT_FLUID_DENSITY)
        cw = self.parameters.get("specific_heat", self.DEFAULT_SPECIFIC_HEAT)

        # gas flow co-produced with the doublet flow, plus grid-supplied gas
        co_produced_gas = self.parameters["gas_water_ratio"] * primary_flow_rate
        total_gas_flow = (co_produced_gas + grid_gas_flow_rate) * gas_density  # kg/s

        gas_energy_flow = self.parameters["caloric_value"] * chp_gas_fraction * total_gas_flow  # W
        fuel_power = self.parameters["efficiency_factor"] * gas_energy_flow
        power_el = self.ELECTRICAL_POWER_FRACTION * fuel_power
        power_th = (1 - self.ELECTRICAL_POWER_FRACTION) * fuel_power

        mass_flow_secondary = chp_flow_fraction * fluid_density * secondary_flow_rate  # kg/s
        if mass_flow_secondary < self._MIN_MASS_FLOW:
            temperature_out = temperature_in
        else:
            temperature_out = temperature_in + power_th / (cw * mass_flow_secondary)

        emission = self.parameters["gas_emission_factor"] / self.JOULE_PER_GJ * gas_energy_flow

        self.output["temperature_in"] = temperature_in
        self.output["temperature_out"] = temperature_out
        self.output["power_el"] = power_el
        self.output["power_th"] = power_th
        self.output["emission"] = emission

    def get_output(self):
        """Get output of the model."""
        return self.output
