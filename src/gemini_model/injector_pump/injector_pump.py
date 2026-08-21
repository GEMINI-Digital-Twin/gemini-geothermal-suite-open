"""Surface injector pump model.

Estimates the electrical power and associated CO2 emissions required
by an injector pump to boost flow from an inlet to a (higher) outlet
pressure.
"""

from gemini_model.model_abstract import StaticModel


class InjectorPump(StaticModel):
    """Surface injector pump power/emission model."""

    JOULE_PER_KWH = 3.6e6

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
        """Calculate output based on input u."""
        pressure_in = u["pressure_in"]
        pressure_out = u["pressure_out"]
        flow_rate = u["flow_rate"]

        efficiency_factor = self.parameters["efficiency_factor"]
        emission_factor = self.parameters["electricity_emission_factor"]

        power_el = flow_rate * max(0.0, pressure_out - pressure_in) / efficiency_factor
        emission = emission_factor / self.JOULE_PER_KWH * power_el

        self.output["pressure_in"] = pressure_in
        self.output["pressure_out"] = pressure_out
        self.output["power_el"] = power_el
        self.output["power_th"] = 0.0
        self.output["emission"] = emission

    def get_output(self):
        """Get output of the model."""
        return self.output
