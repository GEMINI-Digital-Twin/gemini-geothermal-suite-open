"""Hot-water driven single-effect absorption chiller (LiBr-H2O).

Lets a geothermal (or any hot-water) source produce cooling. Capacity follows
the characteristic-equation method, which expresses the cooling capacity of a
sorption chiller as a linear function of the characteristic temperature
difference of its three external mean temperatures:

    dDt = t_G - a * t_AC + e * t_E
    Q_E,max = Q_E,nom * (dDt - dDt_min) / (dDt_nom - dDt_min)

with t_G the mean hot-water (generator) temperature, t_AC the mean cooling-water
(absorber/condenser) temperature and t_E the mean chilled-water (evaporator)
temperature, all in degC. Thermal COP is nearly constant for single-effect
machines once well above the driving threshold and drops close to it.

References
----------
- Hellmann, H.-M., Ziegler, F. (1999). "Simple absorption heat pump modules for
  system simulation programs." ASHRAE Transactions 105(1).
- Kuehn, A., Ziegler, F. (2005). "Operational results of a 10 kW absorption
  chiller and adaptation of the characteristic equation." Proc. 1st Int. Conf.
  Solar Air Conditioning, Bad Staffelstein.
- Herold, K. E., Radermacher, R., Klein, S. A. (2016). "Absorption Chillers and
  Heat Pumps", 2nd ed., CRC Press (single-effect COP ~0.65-0.8).
"""

from gemini_model.model_abstract import StaticModel


class AbsorptionChiller(StaticModel):
    """Single-effect hot-water driven absorption chiller with cooling tower."""

    DEFAULTS = {
        "nominal_cooling_capacity": 1.0e6,  # W, at the nominal temperatures below
        "cop_nominal": 0.75,  # thermal COP Q_E / Q_G at nominal conditions
        "a": 2.5,  # characteristic-equation coefficient on t_AC
        "e": 1.5,  # characteristic-equation coefficient on t_E
        "nominal_generator_mean_temperature": 80.0,  # degC (85/75 hot water)
        "nominal_cooling_water_mean_temperature": 30.0,  # degC (27/33)
        "nominal_chilled_water_mean_temperature": 23.0,  # degC (26/20 high-temp cooling)
        "ddt_min": 10.0,  # K, characteristic temperature difference at zero capacity
        "cooling_water_range": 6.0,  # K, cooling-water temperature rise
        "aux_power_fraction_of_rejected_heat": 0.02,  # cooling tower fans + pumps
        "aux_power_fraction_of_cooling": 0.01,  # solution pump, controls
        "hot_water_density": 1030.0,  # kg/m3
        "hot_water_specific_heat": 4000.0,  # J/(kg K)
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

    def _ddt(self, t_g, t_ac, t_e):
        p = self.parameters
        return t_g - p["a"] * t_ac + p["e"] * t_e

    def capacity(self, t_g_mean, t_ac_mean, t_e_mean):
        """Maximum cooling capacity (W) at the given external mean temperatures."""
        p = self.parameters
        ddt = self._ddt(t_g_mean, t_ac_mean, t_e_mean)
        ddt_nom = self._ddt(
            p["nominal_generator_mean_temperature"],
            p["nominal_cooling_water_mean_temperature"],
            p["nominal_chilled_water_mean_temperature"],
        )
        frac = (ddt - p["ddt_min"]) / (ddt_nom - p["ddt_min"])
        return max(0.0, frac) * p["nominal_cooling_capacity"], frac

    def cop(self, load_fraction_of_driving):
        """Thermal COP; degrades smoothly when the driving potential is small."""
        f = max(0.0, min(1.0, load_fraction_of_driving))
        return self.parameters["cop_nominal"] * (0.6 + 0.4 * f**0.5)

    def calculate_output(self, u, x=None):
        """Load-following operation.

        Inputs ``u``
        ------------
        cooling_demand: W, requested cooling.
        hot_water_temperature_in: degC, driving hot-water (e.g. brine) inlet.
        hot_water_flow_rate: m3/s, hot water available to the generator.
        chilled_water_supply_temperature: degC (e.g. 20).
        chilled_water_return_temperature: degC (e.g. 26).
        cooling_water_temperature_in: degC (cooling tower outlet, e.g. 27).

        Outputs
        -------
        cooling_power (W), generator_heat (W), rejected_heat (W), COP (-),
        hot_water_temperature_out (degC), power_el (W, auxiliaries),
        unmet_cooling (W), capacity (W), emission (0, electricity counted at plant level).
        """
        p = self.parameters
        demand = max(0.0, u["cooling_demand"])
        t_hin = u["hot_water_temperature_in"]
        flow = u["hot_water_flow_rate"]
        t_e_mean = 0.5 * (
            u["chilled_water_supply_temperature"] + u["chilled_water_return_temperature"]
        )
        t_ac_mean = u["cooling_water_temperature_in"] + 0.5 * p["cooling_water_range"]
        c_hot = flow * p["hot_water_density"] * p["hot_water_specific_heat"]  # W/K

        q_e, q_g, t_hout, cop, cap, frac = 0.0, 0.0, t_hin, 0.0, 0.0, 0.0
        if demand > 0 and c_hot > 1e-6:
            # fixed point: generator mean temperature depends on the heat drawn
            t_g_mean = t_hin
            for _ in range(30):
                cap, frac = self.capacity(t_g_mean, t_ac_mean, t_e_mean)
                q_e = min(demand, cap)
                cop = self.cop(frac)
                q_g = q_e / cop if cop > 0 else 0.0
                t_hout = t_hin - q_g / c_hot
                t_new = 0.5 * (t_hin + t_hout)
                if abs(t_new - t_g_mean) < 1e-4:
                    break
                t_g_mean = 0.5 * (t_g_mean + t_new)

        q_rej = q_e + q_g
        self.output["cooling_power"] = q_e
        self.output["generator_heat"] = q_g
        self.output["rejected_heat"] = q_rej
        self.output["COP"] = cop if q_e > 0 else 0.0
        self.output["capacity"] = cap
        self.output["hot_water_temperature_out"] = t_hout
        self.output["hot_water_flow_rate"] = flow
        self.output["unmet_cooling"] = demand - q_e
        self.output["power_el"] = (
            p["aux_power_fraction_of_rejected_heat"] * q_rej
            + p["aux_power_fraction_of_cooling"] * q_e
        )
        self.output["power_th"] = -q_g  # heat consumed
        self.output["emission"] = 0.0

    def get_output(self):
        """Get output of the model."""
        return self.output
