"""Adder model.

Sums an arbitrary number of numbered inputs into a single output, e.g.
several production wells merging into one header, or several secondary
loops recombining before a shared component. Generalizes the 2-input
adder used in earlier doublet models to N inputs.
"""

from gemini_model.model_abstract import StaticModel


class Adder(StaticModel):
    """Sums N numbered inputs into a single output."""

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
            how many numbered inputs (``input_0`` .. ``input_{n-1}``)
            are summed.
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

        Sums ``u["input_0"]`` through ``u["input_{num_inputs-1}"]``
        into a single ``output`` value.
        """
        num_inputs = self.parameters["num_inputs"]

        total = 0.0
        for i in range(num_inputs):
            key = f"input_{i}"
            if key not in u:
                raise KeyError(f"Adder with num_inputs={num_inputs} requires input '{key}'.")
            total += u[key]

        self.output["output"] = total

    def get_output(self):
        """Get output of the model."""
        return self.output
