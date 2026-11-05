"""AbsorptionChiller model.

Hot-water driven single-effect LiBr absorption chiller. The COP is a fraction
of the ideal three-temperature (generator, rejection, evaporator) COP, capped
at a published value, and is zero when the hot water is too cold for the
cycle (Duhring limit).

The model can be used in two ways:
- demand driven: give ``cooling_w`` and get the hot-water heat it needs;
- flow driven, for plant JSON files: give ``temperature_in`` and
  ``water_flow_rate`` of the hot water. The water leaves at
  ``hot_water_outlet_c`` and the heat it gives up drives the chiller.

References
----------
Ideal absorption COP:
    COP_ideal = (1 - T_rejection / T_generator) * T_evaporator / (T_rejection - T_evaporator)
    Herold, K. E., Radermacher, R., & Klein, S. A. (2016). "Absorption
    Chillers and Heat Pumps" (2nd ed.), CRC Press, Chapter 1.
Published COP of geothermal hot-water absorption chillers (about 0.7) and
70-80 C generator outlet: El Haj Assad, M. et al. (2021), "Space cooling
using geothermal single-effect water/lithium bromide absorption chiller",
Energy Science & Engineering 9(10).
"""

from gemini_model.model_abstract import StaticModel

CELSIUS_TO_KELVIN = 273.15


class AbsorptionChiller(StaticModel):
    """AbsorptionChiller model."""

    DEFAULTS = {
        "second_law_fraction": 0.5,  # gives COP 0.67 at 85 C drive, 6 C evaporator, 35 C rejection
        "cop_cap": 0.67,  # published geothermal single-effect chillers
        "evaporator_approach_c": 5.0,
        "rejection_temperature_c": 35.0,  # absorber and condenser, 30 C cooling water
        "minimum_lift_margin_c": 10.0,  # margin above the Duhring limit
        "hot_water_outlet_c": 70.0,  # lower end of the published 70-80 C generator outlet
        "chilled_supply_c": 20.0,
        "parasitic_fraction": 0.04,  # electricity per unit cooling, chiller and cooling tower
        "fluid_density": 1000.0,  # kg/m3, hot water
        "specific_heat": 4181.0,  # J/kg.K, hot water
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
        """Not applicable: the chiller is a static model with no internal state."""
        pass

    def update_state(self, u, x):
        """Not applicable: the chiller is a static model with no internal state."""
        pass

    def minimum_generator_temperature(self, chilled_supply_c):
        """Return the lowest mean generator temperature (degC) the cycle can use."""
        evaporator = chilled_supply_c - self.parameters["evaporator_approach_c"]
        rejection = self.parameters["rejection_temperature_c"]
        return 2 * rejection - evaporator + self.parameters["minimum_lift_margin_c"]

    def calculate_cop(self, hot_water_in_c, chilled_supply_c):
        """Return the COP for a hot-water inlet and chilled supply temperature (degC), or 0.

        The COP is 0 if the hot water is not hotter than its outlet temperature or
        too cold for the cycle.
        """
        if hot_water_in_c <= self.parameters["hot_water_outlet_c"]:
            return 0.0
        generator_c = (hot_water_in_c + self.parameters["hot_water_outlet_c"]) / 2.0
        if generator_c < self.minimum_generator_temperature(chilled_supply_c):
            return 0.0
        generator = generator_c + CELSIUS_TO_KELVIN
        rejection = self.parameters["rejection_temperature_c"] + CELSIUS_TO_KELVIN
        evaporator = chilled_supply_c - self.parameters["evaporator_approach_c"] + CELSIUS_TO_KELVIN
        ideal = (1 - rejection / generator) * evaporator / (rejection - evaporator)
        return min(self.parameters["cop_cap"], self.parameters["second_law_fraction"] * ideal)

    def calculate_output(self, u, x=None):
        """Calculate output based on input u.

        Parameters
        ----------
        u: dict
            Demand driven: ``cooling_w`` (W), ``hot_water_in_c`` (degC) and
            optional ``chilled_supply_c`` (degC). Raises ``ValueError`` if
            the hot water is too cold to drive the chiller.
            Flow driven: ``temperature_in`` (degC) and ``water_flow_rate``
            (m3/s) of the hot water. Hot water too cold to drive the chiller
            passes through unchanged and gives no cooling.
        x: state
            Model state (unused, model is static).
        """
        chilled_supply_c = u.get("chilled_supply_c", self.parameters["chilled_supply_c"])
        if "cooling_w" in u:
            hot_water_in_c = u["hot_water_in_c"]
            cop = self.calculate_cop(hot_water_in_c, chilled_supply_c)
            if cop <= 0.0:
                raise ValueError(f"Hot water at {hot_water_in_c} C cannot drive this chiller.")
            cooling_w = u["cooling_w"]
            drive_heat_w = cooling_w / cop
            temperature_out = self.parameters["hot_water_outlet_c"]
            water_flow_rate = None
        else:
            hot_water_in_c = u["temperature_in"]
            water_flow_rate = u["water_flow_rate"]
            cop = self.calculate_cop(hot_water_in_c, chilled_supply_c)
            if cop <= 0.0:
                temperature_out = hot_water_in_c
                drive_heat_w = 0.0
            else:
                temperature_out = self.parameters["hot_water_outlet_c"]
                mass_flow = self.parameters["fluid_density"] * water_flow_rate
                drive_heat_w = mass_flow * self.parameters["specific_heat"] * (hot_water_in_c - temperature_out)
            cooling_w = cop * drive_heat_w

        self.output["cop"] = cop
        self.output["cooling_w"] = cooling_w
        self.output["drive_heat_w"] = drive_heat_w
        self.output["heat_rejected_w"] = cooling_w + drive_heat_w
        self.output["power_el"] = self.parameters["parasitic_fraction"] * cooling_w
        self.output["temperature_in"] = hot_water_in_c
        self.output["temperature_out"] = temperature_out
        self.output["water_flow_rate"] = water_flow_rate

    def get_output(self):
        """Get output of the model."""
        return self.output
