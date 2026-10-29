"""Electric vapour-compression chiller model.

COP is a fixed fraction ``eta_carnot`` of the reversible (Carnot)
refrigeration COP between the chilled-water supply temperature ``Te`` and
the condensing temperature ``Tc = cooling_water_temperature +
condenser_approach`` (K), capped at ``cop_max``::

    COP = min(cop_max, eta_carnot * Te / (Tc - Te))

References
----------
Cengel, Y. A., & Boles, M. A. (2015). "Thermodynamics: An Engineering
Approach" (8th ed.), McGraw-Hill, Chapter 11 (Refrigeration Cycles).
"""

from gemini_model.model_abstract import StaticModel


class ElectricChiller(StaticModel):
    """Electric vapour-compression chiller."""

    CELSIUS_TO_KELVIN = 273.15

    def __init__(self):
        """Model initialization with typical water-cooled chiller defaults."""
        self.parameters = {
            "capacity_nominal": 5e6,  # W cooling
            "eta_carnot": 0.5,
            "cop_max": 7.0,
            "condenser_approach": 5.0,  # K above cooling-water temperature
            "chilled_temperature_out_target": 20.0,  # degC
            "rho_chilled": 1000.0,  # kg/m3
            "cp_chilled": 4186.0,  # J/(kg.K)
            "electricity_emission_factor": 0.0,  # kg CO2/kWh
        }
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

    def cop(self, cooling_water_temperature):
        """Return the COP for a given cooling-water temperature (degC)."""
        p = self.parameters
        te = p["chilled_temperature_out_target"] + self.CELSIUS_TO_KELVIN
        tc = cooling_water_temperature + p["condenser_approach"] + self.CELSIUS_TO_KELVIN
        if tc <= te:
            return p["cop_max"]
        return min(p["cop_max"], p["eta_carnot"] * te / (tc - te))

    def calculate_output(self, u, x=None):
        """Calculate output based on input u.

        Parameters
        ----------
        u: dict
            ``chilled_temperature_in`` (degC, network return),
            ``chilled_flow_rate`` (m3/s) and ``cooling_water_temperature`` (degC).
        """
        p = self.parameters
        t_chw_in = u["chilled_temperature_in"]
        chw_flow = u["chilled_flow_rate"]
        cap_chw = chw_flow * p["rho_chilled"] * p["cp_chilled"]  # W/K

        cop = self.cop(u["cooling_water_temperature"])
        cooling_requested = max(0.0, cap_chw * (t_chw_in - p["chilled_temperature_out_target"]))
        cooling = min(cooling_requested, p["capacity_nominal"])
        power_el = cooling / cop if cop > 0.0 else 0.0

        self.output["COP"] = cop
        self.output["cooling_power"] = cooling
        self.output["cooling_requested"] = cooling_requested
        self.output["unmet_cooling"] = cooling_requested - cooling
        self.output["heat_rejected"] = cooling + power_el
        self.output["chilled_temperature_out"] = (
            t_chw_in - cooling / cap_chw if cap_chw > 0.0 else t_chw_in
        )
        self.output["chilled_flow_rate"] = chw_flow
        self.output["power_el"] = power_el
        self.output["power_th"] = 0.0
        self.output["emission"] = p["electricity_emission_factor"] / 3.6e6 * power_el

    def get_output(self):
        """Get output of the model."""
        return self.output
