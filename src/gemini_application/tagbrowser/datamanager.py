"""Tabg browser to browser external database and manual csv upload."""

from gemini_application.application_abstract import ApplicationAbstract


class DataManager(ApplicationAbstract):
    """Class for application data management in tag browser."""

    def __init__(self):
        """Initialize data manager class."""
        super().__init__()

    def init_parameters(self, initial_parameters):
        """Initialize application-specific parameters."""
        pass

    def calculate(self):
        """Run application computation model."""
        pass
