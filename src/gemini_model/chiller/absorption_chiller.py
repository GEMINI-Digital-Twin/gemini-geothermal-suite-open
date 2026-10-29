"""Hot-water-fired single-effect absorption chiller model (LiBr/water).

The chiller takes heat from a hot-water (e.g. geothermal brine) stream in
its generator, takes heat from the chilled-water return in its
evaporator, and rejects both to a cooling-water circuit (dry cooler or
cooling tower).

COP model
---------
The reversible (Carnot) COP of a heat-driven chiller working between a
heat source at ``Tg``, a heat sink at ``Tc`` and a cold space at ``Te``
(all in K) is::

    COP_rev = (1 - Tc / Tg) * Te / (Tc - Te)

The real COP is a fixed fraction ``eta_rev`` of that, capped at
``cop_max`` (single-effect LiBr machines rarely exceed ~0.8)::

    COP = min(cop_max, eta_rev * COP_rev)

``Tg`` is the hot-water inlet temperature, ``Te`` the chilled-water supply
temperature and ``Tc`` the cooling-water temperature.

Capacity model
--------------
Below ``generator_temperature_min`` the machine cannot fire. Between that
and ``generator_temperature_nominal`` the available cooling capacity is
derated linearly from 0 to ``capacity_nominal``. The cooling delivered is
the smallest of: the cooling the chilled-water stream asks for (to reach
``chilled_temperature_out_target``), the derated capacity, and what the
hot-water stream can drive while it cools by at most
``hot_temperature_drop_max``.

References
----------
Herold, K. E., Radermacher, R., & Klein, S. A. (2016). "Absorption
Chillers and Heat Pumps" (2nd ed.), CRC Press, Chapters 1 and 6.
ASHRAE Handbook - Refrigeration, chapter "Absorption Equipment".
"""

from gemini_model.model_abstract import StaticModel


class AbsorptionChiller(StaticModel):
    """Single-effect, hot-water-fired absorption chiller."""

    CELSIUS_TO_KELVIN = 273.15
    _MIN_FLOW = 1e-9  # m3/s

    def __init__(self):
        """Model initialization with typical single-effect LiBr defaults."""
        self.parameters = {
            "capacity_nominal": 5e6,  # W cooling
            "eta_rev": 0.2,  # fraction of reversible COP
            "cop_max": 0.8,  # practical single-effect limit
            "generator_temperature_nominal": 85.0,  # degC
            "generator_temperature_min": 65.0,  # degC
            "hot_temperature_drop_max": 15.0,  # K, max hot-water cooling in generator
            "chilled_temperature_out_target": 20.0,  # degC
            "aux_power_fraction": 0.02,  # W_el per W heat rejected (pumps, fans)
            "rho_hot": 1030.0,  # kg/m3
            "cp_hot": 4180.0,  # J/(kg.K)
            "rho_chilled": 1000.0,  # kg/m3
            "cp_chilled": 4186.0,  # J/(kg.K)
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

    def cop(self, hot_temperature_in, cooling_water_temperature):
        """Return the COP for given generator and cooling-water temperatures (degC)."""
        p = self.parameters
        tg = hot_temperature_in + self.CELSIUS_TO_KELVIN
        tc = cooling_water_temperature + self.CELSIUS_TO_KELVIN
        te = p["chilled_temperature_out_target"] + self.CELSIUS_TO_KELVIN
        if tg <= tc or tc <= te:
            return 0.0
        cop_rev = (1.0 - tc / tg) * te / (tc - te)
        return min(p["cop_max"], p["eta_rev"] * cop_rev)

    def capacity(self, hot_temperature_in):
        """Return the derated cooling capacity (W) at a generator inlet temperature (degC)."""
        p = self.parameters
        t_min = p["generator_temperature_min"]
        t_nom = p["generator_temperature_nominal"]
        fraction = (hot_temperature_in - t_min) / (t_nom - t_min)
        return p["capacity_nominal"] * min(1.0, max(0.0, fraction))

    def calculate_output(self, u, x=None):
        """Calculate output based on input u.

        Parameters
        ----------
        u: dict
            ``hot_temperature_in`` (degC) and ``hot_flow_rate`` (m3/s) of the
            driving hot water; ``chilled_temperature_in`` (degC, network
            return) and ``chilled_flow_rate`` (m3/s); ``cooling_water_temperature``
            (degC, heat-rejection circuit).
        """
        p = self.parameters
        t_hot_in = u["hot_temperature_in"]
        hot_flow = u["hot_flow_rate"]
        t_chw_in = u["chilled_temperature_in"]
        chw_flow = u["chilled_flow_rate"]
        t_cw = u["cooling_water_temperature"]

        cap_hot = hot_flow * p["rho_hot"] * p["cp_hot"]  # W/K
        cap_chw = chw_flow * p["rho_chilled"] * p["cp_chilled"]  # W/K

        cop = self.cop(t_hot_in, t_cw)
        cooling_requested = max(0.0, cap_chw * (t_chw_in - p["chilled_temperature_out_target"]))
        cooling_by_heat = cop * cap_hot * p["hot_temperature_drop_max"]
        cooling = min(cooling_requested, self.capacity(t_hot_in), cooling_by_heat)
        if cop <= 0.0 or hot_flow < self._MIN_FLOW:
            cooling = 0.0

        heat_in = cooling / cop if cooling > 0.0 else 0.0
        heat_rejected = heat_in + cooling
        t_hot_out = t_hot_in - heat_in / cap_hot if cap_hot > 0.0 else t_hot_in
        t_chw_out = t_chw_in - cooling / cap_chw if cap_chw > 0.0 else t_chw_in

        self.output["COP"] = cop
        self.output["cooling_power"] = cooling  # W
        self.output["cooling_requested"] = cooling_requested  # W
        self.output["unmet_cooling"] = cooling_requested - cooling  # W
        self.output["heat_consumed"] = heat_in  # W from hot water
        self.output["heat_rejected"] = heat_rejected  # W to cooling water
        self.output["hot_temperature_out"] = t_hot_out
        self.output["hot_flow_rate"] = hot_flow
        self.output["chilled_temperature_out"] = t_chw_out
        self.output["chilled_flow_rate"] = chw_flow
        self.output["power_el"] = p["aux_power_fraction"] * heat_rejected
        self.output["power_th"] = -heat_in
        self.output["emission"] = 0.0

    def get_output(self):
        """Get output of the model."""
        return self.output
