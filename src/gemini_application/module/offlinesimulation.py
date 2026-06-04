"""Production well performance analysis with IPR, VLP, and ESP calculations."""

from gemini_application.application_abstract import ApplicationAbstract
from gemini_framework.framework.offlinemodule import OfflineModule


class OfflineModuleSimulation(ApplicationAbstract):
    """Class for application offline simulation calculation."""

    def __init__(self):
        """Initialize offline module simulation application."""
        super().__init__()

        self.offlinemodule = None

    def init_parameters(self, parameters):
        """Initialize application-specific parameters."""
        self.offlinemodule = OfflineModule(self.plant)

        self.offlinemodule.set_date(parameters["start_date"], parameters["end_date"])

    def calculate(self):
        """Run an application computation model."""
        self.offlinemodule.module_calculate()

    def import_raw_data(self):
        """Import raw data."""
        self.offlinemodule.import_raw_data()
