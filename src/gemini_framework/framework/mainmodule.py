"""Main execution module organizing pre/model/post processors per loop."""

from gemini_framework.framework.loop import Loop


class MainModule:
    """Coordinates reading data and executing all unit modules per category."""

    plant = None
    modules = dict()
    loop = dict()

    def __init__(self, plant):
        """Initialize main module with plant."""
        self.plant = plant

        self.modules["preprocessor"] = plant.find_modules("preprocessor")
        self.modules["model"] = plant.find_modules("model")
        self.modules["postprocessor"] = plant.find_modules("postprocessor")

        self.loop["filtered"] = Loop()
        end_time = self.plant.database.get_current_time_str()
        timestep = self.plant.parameters["database"]["filtered"]["interval"]
        # start time will be set inside the module based on the latest available calculated value
        self.loop["filtered"].initialize(end_time=end_time, timestep=timestep)

        self.loop["calculated"] = Loop()
        end_time = self.plant.database.get_current_time_str()
        timestep = self.plant.parameters["database"]["calculated"]["interval"]
        # start time will be set inside the module based on the latest available calculated value
        self.loop["calculated"].initialize(end_time=end_time, timestep=timestep)

    def step(self):
        """Execute one simulation step."""
        # self.plant.database.delete(self.plant.name)
        self.plant.database.import_raw_data()

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
