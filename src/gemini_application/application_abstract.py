"""Abstract base class for end-user applications with plant and unit management."""

from abc import ABC, abstractmethod

from gemini_framework.framework.boot_plant import setup


class ApplicationAbstract(ABC):
    """Abstract base class for end-user applications."""

    def __init__(self):
        """Initialize application abstract."""
        self.plant = None
        self.unit = None

        self.parameters = dict()
        self.inputs = dict()
        self.outputs = dict()

    def load_plant(self, project_path, plant_name):
        """Load plant configuration and initialize framework plant."""
        self.plant = setup(project_path, plant_name)

    def select_unit(self, unit_name):
        """Select unit in the plant by name for calculations."""
        for unit in self.plant.units:
            if unit.name == unit_name:
                self.unit = unit

    def set_input(self, inputs):
        """Set the input."""
        self.inputs = inputs

    def get_input(self):
        """Set application inputs."""
        return self.inputs

    def get_output(self):
        """Return application outputs."""
        return self.outputs

    @abstractmethod
    def init_parameters(self, initial_parameters):
        """Initialize application-specific parameters."""
        pass

    @abstractmethod
    def calculate(self):
        """Run application computation model."""
        pass
