"""Splitter model.

Splits a single input into an arbitrary number of numbered outputs by
fixed fractions, e.g. secondary flow routed to both a Boiler and a
CHP, or a single production header feeding several parallel branches.
Generalizes the fixed 2-output splitter used in earlier doublet models
to N outputs.
"""

from gemini_model.model_abstract import StaticModel


class Splitter(StaticModel):
    """Splits a single input into N outputs by fixed fractions."""

    def __init__(self):
        """Model initialization."""
        self.parameters = {"split_fractions": [0.5, 0.5]}
        self.output = {}

    def update_parameters(self, parameters):
        """Update model parameters.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model. ``split_fractions``
            is a list of N fractions (summing to 1) defining how the
            input is divided across ``output_0`` .. ``output_{N-1}``.
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

        Splits ``u["input"]`` into ``output_0`` .. ``output_{N-1}``
        using ``split_fractions``. Fractions must sum to 1 (within a
        small tolerance).
        """
        value = u["input"]
        fractions = self.parameters["split_fractions"]

        total_fraction = sum(fractions)
        if abs(total_fraction - 1.0) > 1e-6:
            raise ValueError(
                f"split_fractions must sum to 1, got {total_fraction} for {fractions}."
            )

        for i, fraction in enumerate(fractions):
            self.output[f"output_{i}"] = value * fraction

    def get_output(self):
        """Get output of the model."""
        return self.output
