"""Abstract base interface for Gemini simulation models.

All concrete models should inherit from :class:`Model` and implement the
parameter update, state initialization/update, output calculation, and
output retrieval methods shown below.
"""

from abc import ABC, abstractmethod


class Model(ABC):
    """Abstract base class for discrete state-space models."""

    @abstractmethod
    def __init__(self):
        """Model initialization."""
        self.parameters = {}
        self.output = {}

    @abstractmethod
    def update_parameters(self, parameters):
        """Update model parameters.

        Parameters
        ----------
        parameters : dict
            Parameters dict as defined by the model.
        """
        pass

    @abstractmethod
    def initialize_state(self, x):
        """Generate an initial state based on user parameters."""
        pass

    @abstractmethod
    def update_state(self, u, x):
        """Update the state based on input u and state x."""
        pass

    @abstractmethod
    def calculate_output(self, u, x):
        """Calculate output based on input u and state x."""
        pass

    @abstractmethod
    def get_output(self):
        """Get output of the model."""
        return self.output
