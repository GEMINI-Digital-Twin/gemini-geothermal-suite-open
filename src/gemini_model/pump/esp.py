"""Electrical submersible pump (ESP) model.

Implements simple correlations to predict pump head, power, and efficiency
as a function of flow rate and frequency.
Reference: TNO 2022 R11363 "Model-based monitoring of geothermal assets,
case study: electrical submersible pumps".
"""

import os

from gemini_model.model_abstract import Model

path = os.path.dirname(__file__)


class ESP(Model):
    """ESP performance model (head, power, efficiency)."""

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

    def calculate_output(self, u, x):
        """Calculate output based on input u and state x."""
        # get input
        pump_freq = u["pump_freq"]
        pump_flow = u["pump_flow"]

        # calculate model
        pump_head = self.head_function(pump_flow, pump_freq)
        pump_power = self.power_function(pump_flow, pump_freq)
        pump_eff = self.efficiency_function(pump_flow, pump_head, pump_power)

        # write output
        self.output["pump_head"] = pump_head
        self.output["pump_power"] = pump_power
        self.output["pump_eff"] = pump_eff

    def get_output(self):
        """Get output of the model."""
        return self.output

    def head_function(self, pump_flow, freq):
        """Calculate ESP head from flow and frequency (uses US-unit correlation)."""
        pump_flow = pump_flow * 543439.650564  # m3/s to bbl/d

        head = (
            self.parameters["no_stages"]
            * ((freq / 60) ** 2)
            * (
                self.parameters["head_coeff"][0]
                + self.parameters["head_coeff"][1] * pump_flow
                + self.parameters["head_coeff"][2] * (pump_flow**2)
                + self.parameters["head_coeff"][3] * (pump_flow**3)
                + self.parameters["head_coeff"][4] * (pump_flow**4)
                + self.parameters["head_coeff"][5] * (pump_flow**5)
            )
        )
        return head * 2988.30167  # feet of head to Pa

    def power_function(self, pump_flow, freq):
        """Calculate ESP power from flow and frequency (US-unit correlation)."""
        pump_flow = pump_flow * 543439.650564  # m3/s to bbl/d

        pump_power = (
            self.parameters["no_stages"]
            * ((freq / 60) ** 3)
            * (
                self.parameters["power_coeff"][0]
                + self.parameters["power_coeff"][1] * pump_flow
                + self.parameters["power_coeff"][2] * (pump_flow**2)
                + self.parameters["power_coeff"][3] * (pump_flow**3)
                + self.parameters["power_coeff"][4] * (pump_flow**4)
                + self.parameters["power_coeff"][5] * (pump_flow**5)
            )
        )

        return pump_power * 745.7  # brake horsepower to Watts

    def efficiency_function(self, pump_flow, pump_head, pump_power):
        """Calculate ESP efficiency from flow, head, and power (US-unit correlation)."""
        pump_flow = pump_flow * 543439.650564  # m3/s to bbl/d

        if pump_power < 0.1:
            pump_eff = 0
        else:
            pump_eff = 100 * pump_flow / 135773 * (pump_head / pump_power) * (745.7 / 2988.30167)

        return pump_eff
