"""Electric vapour-compression chiller with cooling tower.

COP from a Carnot fraction between evaporating and condensing temperatures:

    COP = eta_carnot * T_evap / (T_cond - T_evap)        (temperatures in K)
    T_evap = chilled-water supply - evaporator approach
    T_cond = cooling-water inlet + cooling-water range + condenser approach

capped at ``cop_max``. Capacity is limited to ``nominal_cooling_capacity``.

References
----------
- Cengel, Y. A., Boles, M. A. (2015). "Thermodynamics: An Engineering Approach",
  8th ed., ch. 11 (refrigeration cycles, Carnot COP).
- ASHRAE Handbook - HVAC Systems and Equipment (2020), ch. 43 (liquid chilling
  systems): Carnot efficiencies of 0.45-0.6 for centrifugal/screw chillers.
"""

from gemini_model.model_abstract import StaticModel


class ElectricChiller(StaticModel):
    """Electric compression chiller (water-cooled)."""

    DEFAULTS = {
        "nominal_cooling_capacity": 1.0e6,  # W
        "eta_carnot": 0.5,
        "cop_max": 9.0,
        "evaporator_approach": 3.0,  # K
        "condenser_approach": 3.0,  # K
        "cooling_water_range": 6.0,  # K
        "aux_power_fraction_of_rejected_heat": 0.02,  # cooling tower fans + pumps
    }

    def __init__(self):
        """Model initialization with default parameters."""
        self.parameters = dict(self.DEFAULTS)
        self.output = {}

    def update_parameters(self, parameters):
        """Update model parameters."""
        for key, value in parameters.items():
            self.parameters[key] = value

    def initialize_state(self, x):
        """Static model: no state."""
        pass

    def update_state(self, u, x):
        """Static model: no state."""
        pass

    def cop(self, chilled_supply_c, cooling_water_in_c):
        """Electric COP at the given chilled-water supply and cooling-water inlet."""
        p = self.parameters
        t_ev = chilled_supply_c - p["evaporator_approach"] + 273.15
        t_co = cooling_water_in_c + p["cooling_water_range"] + p["condenser_approach"] + 273.15
        if t_co <= t_ev:
            return p["cop_max"]
        return min(p["cop_max"], p["eta_carnot"] * t_ev / (t_co - t_ev))

    def calculate_output(self, u, x=None):
        """Load-following operation.

        Inputs ``u``: cooling_demand (W), chilled_water_supply_temperature (degC),
        cooling_water_temperature_in (degC).
        Outputs: cooling_power, power_el (compressor + auxiliaries), COP,
        rejected_heat, unmet_cooling (all W except COP).
        """
        p = self.parameters
        demand = max(0.0, u["cooling_demand"])
        q_e = min(demand, p["nominal_cooling_capacity"])
        cop = self.cop(u["chilled_water_supply_temperature"], u["cooling_water_temperature_in"])
        w = q_e / cop if q_e > 0 else 0.0
        q_rej = q_e + w
        self.output["cooling_power"] = q_e
        self.output["compressor_power"] = w
        self.output["power_el"] = w + p["aux_power_fraction_of_rejected_heat"] * q_rej
        self.output["COP"] = cop
        self.output["rejected_heat"] = q_rej
        self.output["unmet_cooling"] = demand - q_e
        self.output["power_th"] = 0.0
        self.output["emission"] = 0.0

    def get_output(self):
        """Get output of the model."""
        return self.output
