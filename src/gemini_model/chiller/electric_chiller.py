"""Electric (vapour-compression) chiller, Carnot-fraction model.

Same approach as GEMINI's ``HeatpumpBasic`` (Carnot mode), applied to cooling:

    COP_cool = eta * T_evap / (T_cond - T_evap)        [K]
    T_evap = chilled-water supply - approach
    T_cond = cooling-water temperature + approach

eta ~0.45-0.55 for modern screw/centrifugal machines. COP is capped
(``cop_max``) because real machines do not follow Carnot at very small lifts.
Auxiliary electricity for dry-cooler fans is a fraction of the rejected heat.
"""

import numpy as np

from gemini_model.model_abstract import StaticModel

K0 = 273.15
DEFAULTS = {"capacity_w": 5e6, "eta_carnot": 0.45, "approach_k": 3.0, "condenser_approach_k": 5.0,
            "cop_max": 9.0, "aux_fraction": 0.02}


def electric_chiller_cop(t_chilled_supply_c, t_cooling_water_c, p=None):
    p = {**DEFAULTS, **(p or {})}
    te = np.asarray(t_chilled_supply_c, float) - p["approach_k"] + K0
    tc = np.asarray(t_cooling_water_c, float) + p["condenser_approach_k"] + K0
    return np.minimum(p["eta_carnot"] * te / np.maximum(tc - te, 1.0), p["cop_max"])


def electric_chiller_operate(load_w, t_chilled_supply_c, t_cooling_water_c, p=None):
    p = {**DEFAULTS, **(p or {})}
    cool = np.minimum(np.asarray(load_w, float), p["capacity_w"])
    cop = electric_chiller_cop(t_chilled_supply_c, t_cooling_water_c, p)
    comp = cool / cop
    rejected = cool + comp
    return {"cooling": cool, "cop": cop, "compressor_power": comp, "heat_rejected": rejected,
            "power_el": comp + p["aux_fraction"] * rejected}


class ElectricChiller(StaticModel):
    """Inputs ``u``: cooling_load (W), chilled_water_supply_temperature (degC),
    cooling_water_temperature (degC). Outputs: cooling, cop, power_el (W), heat_rejected (W)."""

    def __init__(self):
        self.parameters = dict(DEFAULTS)
        self.output = {}

    def update_parameters(self, parameters):
        for key, value in parameters.items():
            self.parameters[key] = value

    def initialize_state(self, x):
        pass

    def update_state(self, u, x):
        pass

    def calculate_output(self, u, x=None):
        r = electric_chiller_operate(u["cooling_load"], u["chilled_water_supply_temperature"],
                                     u["cooling_water_temperature"], self.parameters)
        self.output.update({k: float(v) for k, v in r.items()})
        self.output["power_th"] = 0.0
        self.output["emission"] = 0.0

    def get_output(self):
        return self.output
