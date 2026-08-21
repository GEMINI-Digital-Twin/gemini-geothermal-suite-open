"""Surface filter model.

Estimates the pressure and temperature drop across a surface filter,
where the flow resistance increases with flow rate to approximate
fouling/clogging behaviour.
"""

import math

from gemini_model.model_abstract import StaticModel


class Filter(StaticModel):
    """Surface filter pressure/temperature drop model with fouling."""

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

        ``u["direction"]`` selects the calculation direction: ``"forward"``
        computes the outlet state from the inlet state, ``"backward"``
        computes the inlet state from the outlet state. The flow resistance
        increases with flow rate as R = a*(1 - exp(-b*Q)) + R0, approximating
        fouling/clogging of the filter element.
        """
        pressure = u["pressure"]
        temperature = u["temperature"]
        flow_rate = u["flow_rate"]
        direction = u["direction"]

        base_resistance = self.parameters["base_resistance"]
        fouling_coeff_a = self.parameters["fouling_coeff_a"]
        fouling_coeff_b = self.parameters["fouling_coeff_b"]
        temperature_drop = self.parameters["temperature_drop"]

        flow_resistance = (
            fouling_coeff_a * (1 - math.exp(-fouling_coeff_b * flow_rate)) + base_resistance
        )

        if direction == "forward":
            pressure_in = pressure
            pressure_out = pressure_in - flow_rate * flow_resistance
            temperature_in = temperature
            temperature_out = temperature_in - temperature_drop
        elif direction == "backward":
            pressure_out = pressure
            pressure_in = pressure_out + flow_rate * flow_resistance
            temperature_out = temperature
            temperature_in = temperature_out + temperature_drop
        else:
            raise ValueError(f"Unsupported direction '{direction}'. Use 'forward' or 'backward'.")

        self.output["pressure_in"] = pressure_in
        self.output["pressure_out"] = pressure_out
        self.output["temperature_in"] = temperature_in
        self.output["temperature_out"] = temperature_out
        self.output["flow_resistance"] = flow_resistance
        self.output["power_el"] = 0.0
        self.output["power_th"] = 0.0
        self.output["emission"] = 0.0

    def get_output(self):
        """Get output of the model."""
        return self.output
