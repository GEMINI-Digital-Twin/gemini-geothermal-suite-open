"""Multi-stage gas compressor model.

Estimates the shaft power required to compress a gas mass flow from an
inlet to an outlet pressure, assuming ideal intercooling (gas is
cooled back to inlet temperature between stages) and an equal
pressure ratio across every stage.
"""

from gemini_model.model_abstract import StaticModel


class Compressor(StaticModel):
    """Multi-stage gas compressor power model."""

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
        mass_flow = u["mass_flow"]  # kg/s
        compressor_power = self._power_calculation(mass_flow)

        self.output["compressor_power"] = compressor_power
        self.output["mass_flow"] = mass_flow  # mass_flow is not altered

    def _power_calculation(self, mass_flow):
        """Compute compressor shaft power assuming ideal intercooling.

        Assumptions:
        - ideal intercooling: after each stage, the gas is cooled back
          to the inlet temperature T1.
        - equal pressure ratio: each stage compresses the gas with the
          same pressure ratio.
        """
        e_m = self.parameters["mechanical_efficiency"]
        e_c = self.parameters["compressor_efficiency"]
        k = self.parameters["specific_heat_ratio"]
        gas_constant = self.parameters["gas_constant"]
        t1 = self.parameters["inlet_temperature"]
        p1 = self.parameters["inlet_pressure"]
        p2 = self.parameters["outlet_pressure"]
        n = self.parameters["number_of_stages"]
        stage_pressure_ratio = (p2 / p1) ** (1 / n)

        compressor_power = (n * mass_flow * gas_constant * t1 / (k - 1)) * (
            stage_pressure_ratio ** ((k - 1) / k) - 1
        )

        # correcting for efficiency factors
        compressor_power = compressor_power / (e_m * e_c)

        return compressor_power

    def get_output(self):
        """Get output of the model."""
        return self.output
