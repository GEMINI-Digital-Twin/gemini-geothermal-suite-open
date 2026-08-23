"""Surface separator model.

Estimates the pressure and temperature drop across a surface separator
vessel, given a linear flow-dependent pressure resistance and a fixed
temperature drop.
"""

from gemini_model.model_abstract import StaticModel


class Separator(StaticModel):
    """Surface separator pressure/temperature drop model."""

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
        computes the inlet state from the outlet state.
        """
        pressure = u["pressure"]
        temperature = u["temperature"]
        flow_rate = u["flow_rate"]
        direction = u["direction"]

        flow_resistance = self.parameters["flow_resistance"]
        temperature_drop = self.parameters["temperature_drop"]

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
        self.output["power_el"] = 0.0
        self.output["power_th"] = 0.0
        self.output["emission"] = 0.0

    def get_output(self):
        """Get output of the model."""
        return self.output
