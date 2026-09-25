"""Mixer model.

Combines an arbitrary number of numbered flow/temperature branches into
a single flow/temperature junction, e.g. a boiler's and a CHP's water
outlets recombining before being routed onward. Unlike ``Adder`` (which
sums a plain scalar such as power or a single flow), a ``Mixer`` handles
paired flow/temperature branches: the outlet flow is the sum of the
branch flows, and the outlet temperature is a flow-weighted average of
the branch temperatures (mass-and-energy balance of the mixing point).
"""

from gemini_model.model_abstract import StaticModel


class Mixer(StaticModel):
    """Combines N numbered (flow, temperature) branches into one outlet."""

    _MIN_TOTAL_FLOW = 1e-9  # guards against division by zero when all branch flows are ~0

    def __init__(self):
        """Model initialization."""
        self.parameters = {"num_inputs": 2}
        self.output = {}

    def update_parameters(self, parameters):
        """Update model parameters.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model. ``num_inputs`` sets
            how many numbered branches (``input_0_flow``/
            ``input_0_temperature`` .. ``input_{n-1}_flow``/
            ``input_{n-1}_temperature``) are mixed.
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

        Combines ``u["input_0_flow"]``/``u["input_0_temperature"]``
        through ``u["input_{num_inputs-1}_flow"]``/
        ``u["input_{num_inputs-1}_temperature"]`` into a single
        ``flow``/``temperature`` output: ``flow = sum(flow_i)``,
        ``temperature = sum(flow_i * temperature_i) / flow``. If the
        total flow is (near) zero, ``temperature`` falls back to the
        plain average of the branch temperatures.
        """
        num_inputs = self.parameters["num_inputs"]

        total_flow = 0.0
        weighted_temperature = 0.0
        temperatures = []
        for i in range(num_inputs):
            flow_key = f"input_{i}_flow"
            temperature_key = f"input_{i}_temperature"
            if flow_key not in u:
                raise KeyError(f"Mixer with num_inputs={num_inputs} requires input '{flow_key}'.")
            if temperature_key not in u:
                raise KeyError(
                    f"Mixer with num_inputs={num_inputs} requires input '{temperature_key}'."
                )
            flow_i = u[flow_key]
            temperature_i = u[temperature_key]
            total_flow += flow_i
            weighted_temperature += flow_i * temperature_i
            temperatures.append(temperature_i)

        if total_flow < self._MIN_TOTAL_FLOW:
            temperature = sum(temperatures) / len(temperatures)
        else:
            temperature = weighted_temperature / total_flow

        self.output["flow"] = total_flow
        self.output["temperature"] = temperature

    def get_output(self):
        """Get output of the model."""
        return self.output
