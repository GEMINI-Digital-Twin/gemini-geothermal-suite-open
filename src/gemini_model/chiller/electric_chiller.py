"""Electric vapour-compression chiller model.

Full-load COP
-------------
The refrigerant evaporates ``evaporator_approach`` below the chilled-water
supply temperature and condenses ``condenser_approach`` above the
cooling-water (or dry-cooler air) inlet temperature; the latter includes
the cooling-water temperature rise across the condenser. The full-load
COP is a fixed fraction ``eta_carnot`` of the reversible COP between
those two refrigerant temperatures (K), capped at ``cop_max``::

    Te = T_chw_supply - evaporator_approach
    Tc = T_cooling_water + condenser_approach
    COP_full = min(cop_max, eta_carnot * Te / (Tc - Te))

Part load
---------
Compressor power at part-load ratio ``PLR = cooling / capacity`` follows
the DOE-2 part-load curve ``f(PLR) = a + b PLR + c PLR^2``
(``part_load_coefficients``): the fraction of full-load compressor power
drawn at that load, equal to 1 at full load. Below
``plr_min`` the compressor cycles, so power is taken at ``plr_min`` and
scaled by the on-time fraction ``PLR / plr_min``::

    P_comp = capacity / COP_full * f(max(PLR, plr_min)) * min(1, PLR / plr_min)

With ``units`` > 1 the capacity is split into equal modules and only as
many run as the load needs, each at the same part-load ratio (staging).

Heat rejection fans and pumps draw ``aux_power_fraction`` of the heat
rejected. The reported ``COP`` is the system COP (cooling / all
electricity); ``compressor_cop`` excludes the auxiliaries.

References
----------
Cengel, Y. A., & Boles, M. A. (2015). "Thermodynamics: An Engineering
Approach" (8th ed.), McGraw-Hill, Chapter 11 (Refrigeration Cycles).
Hydeman, M., et al. (2002). "Development and Testing of a Reformulated
Regression-Based Electric Chiller Model", ASHRAE Transactions 108(2).
DOE-2.2 Volume 3, "Electric chillers" (EIR-fPLR curve).
"""

import math

from gemini_model.model_abstract import StaticModel


class ElectricChiller(StaticModel):
    """Electric vapour-compression chiller with part-load and heat-rejection losses."""

    CELSIUS_TO_KELVIN = 273.15

    def __init__(self):
        """Model initialization with typical dry-cooler / tower-cooled screw chiller defaults."""
        self.parameters = {
            "capacity_nominal": 5e6,  # W cooling, all units together
            "units": 1,  # equal modules, staged on as the load rises
            "eta_carnot": 0.40,
            "cop_max": 7.0,
            "evaporator_approach": 4.0,  # K below chilled-water supply
            "condenser_approach": 8.0,  # K above cooling-water inlet (incl. its rise)
            "part_load_coefficients": [0.222, 0.313, 0.465],  # DOE-2 EIR(PLR)
            "plr_min": 0.15,
            "aux_power_fraction": 0.02,  # W_el per W heat rejected (fans, pumps)
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
        """Return the full-load compressor COP for a cooling-water temperature (degC)."""
        p = self.parameters
        te = (
            p["chilled_temperature_out_target"]
            - p.get("evaporator_approach", 0.0)
            + self.CELSIUS_TO_KELVIN
        )
        tc = cooling_water_temperature + p["condenser_approach"] + self.CELSIUS_TO_KELVIN
        if tc <= te:
            return p["cop_max"]
        return min(p["cop_max"], p["eta_carnot"] * te / (tc - te))

    def part_load_power_fraction(self, plr):
        """Return compressor power as a fraction of full-load power at part-load ratio ``plr``."""
        p = self.parameters
        if plr <= 0.0:
            return 0.0
        a, b, c = p.get("part_load_coefficients", [0.0, 1.0, 0.0])
        plr_min = p.get("plr_min", 0.0)
        plr_eff = max(plr, plr_min)
        eir = a + b * plr_eff + c * plr_eff**2
        on_fraction = min(1.0, plr / plr_min) if plr_min > 0.0 else 1.0
        return eir * on_fraction

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
        capacity = p["capacity_nominal"]

        cop_full = self.cop(u["cooling_water_temperature"])
        cooling_requested = max(0.0, cap_chw * (t_chw_in - p["chilled_temperature_out_target"]))
        cooling = min(cooling_requested, capacity)
        units = max(1, int(p.get("units", 1)))
        unit_capacity = capacity / units
        units_on = min(units, math.ceil(cooling / unit_capacity - 1e-9)) if cooling > 0 else 0
        plr = cooling / (units_on * unit_capacity) if units_on else 0.0
        if cooling > 0.0 and cop_full > 0.0:
            compressor_power = (
                units_on * unit_capacity / cop_full * self.part_load_power_fraction(plr)
            )
        else:
            compressor_power = 0.0
        heat_rejected = cooling + compressor_power
        aux_power = p.get("aux_power_fraction", 0.0) * heat_rejected
        power_el = compressor_power + aux_power

        self.output["COP"] = cooling / power_el if power_el > 0.0 else 0.0
        self.output["compressor_cop"] = cooling / compressor_power if compressor_power > 0 else 0.0
        self.output["full_load_cop"] = cop_full
        self.output["part_load_ratio"] = plr
        self.output["units_on"] = units_on
        self.output["cooling_power"] = cooling
        self.output["cooling_requested"] = cooling_requested
        self.output["unmet_cooling"] = cooling_requested - cooling
        self.output["heat_rejected"] = heat_rejected
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
