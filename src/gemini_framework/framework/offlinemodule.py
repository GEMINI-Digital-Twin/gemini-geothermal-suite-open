"""Offline module organizing pre/model/post processors per loop."""

from gemini_framework.framework.loop import Loop


class OfflineModule:
    """Coordinates reading data and executing all unit modules per category."""

    plant = None
    modules = dict()
    loop = dict()

    def __init__(self, plant):
        """Initialize offline module with plant."""
        self.plant = plant

        self.modules["preprocessor"] = plant.find_modules("preprocessor")
        self.modules["model"] = plant.find_modules("model")
        self.modules["postprocessor"] = plant.find_modules("postprocessor")

        self.loop["filtered"] = Loop()
        self.loop["calculated"] = Loop()

    def set_date(self, start_date, end_date):
        """Initiliaze loop with start and end date."""
        timestep = self.plant.parameters["database"]["filtered"]["interval"]
        self.loop["filtered"].initialize(start_date, end_date, timestep)

        timestep = self.plant.parameters["database"]["calculated"]["interval"]
        self.loop["calculated"].initialize(start_date, end_date, timestep)

    def import_raw_data(self):
        """Import raw data from external database."""
        self.plant.database.import_raw_data()

    def module_calculate(self):
        """Execute module calculation."""
        for module in self.modules["preprocessor"]:
            module.logger.info(
                "Timestamps: "
                + self.loop["filtered"].end_time
                + ". Running preprocessor module: "
                + module.__class__.__name__
            )
            module.step(self.loop["filtered"])

        for module in self.modules["model"]:
            module.logger.info(
                "Timestamps: "
                + self.loop["calculated"].end_time
                + ". Running calculation module: "
                + module.__class__.__name__
            )
            module.step(self.loop["calculated"])

        for module in self.modules["postprocessor"]:
            module.logger.info(
                "Timestamps: "
                + self.loop["calculated"].end_time
                + ". Running postprocessor module: "
                + module.__class__.__name__
            )
            module.step(self.loop["calculated"])
