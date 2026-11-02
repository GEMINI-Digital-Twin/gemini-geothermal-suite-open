"""Hot-water LiBr absorption chiller model, following GEMINI's model interface.

COP is a fraction of the ideal three-temperature COP, capped at a published
value. Parameters are assumptions; see the defaults below and their notes.
"""

from gemini_model.model_abstract import StaticModel

CELSIUS_TO_KELVIN = 273.15


class AbsorptionChiller(StaticModel):
    """Absorption chiller driven by a hot-water stream."""

    DEFAULTS = {
        "second_law_fraction": 0.5,  # gives COP 0.67 at 85 C drive, 6 C evaporator, 35 C rejection
        "cop_cap": 0.67,  # cascaded geothermal chillers, El Haj Assad et al. 2021
        "evaporator_approach_c": 5.0,
        "rejection_temperature_c": 35.0,  # absorber and condenser, 30 C cooling water
        "minimum_lift_margin_c": 10.0,  # margin above the Duhring limit
        "hot_water_outlet_c": 70.0,  # lower end of the published 70-80 C generator outlet
        "parasitic_fraction": 0.04,  # electricity per unit cooling, chiller and cooling tower
    }

    def __init__(self):
        """Model initialization."""
        self.parameters = dict(self.DEFAULTS)
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

    def minimum_generator_temperature(self, chilled_supply_c):
        """Return the lowest mean generator temperature (C) the cycle can use."""
        evaporator = chilled_supply_c - self.parameters["evaporator_approach_c"]
        rejection = self.parameters["rejection_temperature_c"]
        return 2 * rejection - evaporator + self.parameters["minimum_lift_margin_c"]

    def calculate_cop(self, hot_water_in_c, chilled_supply_c):
        """Return COP for a hot-water inlet and chilled supply temperature (C)."""
        generator_c = (hot_water_in_c + self.parameters["hot_water_outlet_c"]) / 2.0
        if generator_c < self.minimum_generator_temperature(chilled_supply_c):
            return 0.0
        generator = generator_c + CELSIUS_TO_KELVIN
        rejection = self.parameters["rejection_temperature_c"] + CELSIUS_TO_KELVIN
        evaporator = (
            chilled_supply_c - self.parameters["evaporator_approach_c"] + CELSIUS_TO_KELVIN
        )
        ideal = (1 - rejection / generator) * evaporator / (rejection - evaporator)
        return min(self.parameters["cop_cap"], self.parameters["second_law_fraction"] * ideal)

    def calculate_output(self, u, x=None):
        """Calculate output based on input u.

        Inputs are ``cooling_w``, ``hot_water_in_c`` and ``chilled_supply_c``.
        Outputs are ``cop``, ``drive_heat_w``, ``heat_rejected_w`` and
        ``power_el``. Raises ``ValueError`` if the hot water is too cold.
        """
        cooling_w = u["cooling_w"]
        cop = self.calculate_cop(u["hot_water_in_c"], u["chilled_supply_c"])
        if cop <= 0.0:
            raise ValueError(f"Hot water at {u['hot_water_in_c']} C cannot drive this chiller.")
        drive_heat_w = cooling_w / cop
        self.output["cop"] = cop
        self.output["drive_heat_w"] = drive_heat_w
        self.output["heat_rejected_w"] = cooling_w + drive_heat_w
        self.output["power_el"] = self.parameters["parasitic_fraction"] * cooling_w

    def get_output(self):
        """Get output of the model."""
        return self.output
