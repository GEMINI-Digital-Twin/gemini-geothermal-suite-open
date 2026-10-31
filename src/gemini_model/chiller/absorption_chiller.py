"""Single-effect LiBr/water absorption chiller driven by hot water.

Steady-state model in GEMINI's ``StaticModel`` style, plus a vectorised
function used by annual simulations (the class calls the same function, so
both give identical results).

Performance follows the characteristic-equation approach for absorption
chillers (Kuehn & Ziegler, "Operational results of a 10 kW absorption
chiller and adaptation of the characteristic equation", 2005; Hellmann &
Ziegler 1999): capacity and COP are functions of one combined driving
temperature difference

    ddt = t_G - A * t_AC + B * t_E

with t_G, t_AC, t_E the mean external temperatures of the generator (hot
water), absorber/condenser (cooling water) and evaporator (chilled water).
For single-effect LiBr/water typical values are A ~ 2.5 and B ~ 1.5.

Simplifications (documented, adjustable through parameters):

* capacity fraction = clip((ddt - ddt_min) / (ddt_nom - ddt_min), 0, cap_max)
* COP = cop_nom * (1 - exp(-(ddt - ddt_min) / ddt_tau)), 0 below ddt_min
* auxiliary electricity (solution pump, dry-cooler fans) = aux_fraction x
  rejected heat

Defaults: nominal point 85 / 30 / 7 degC (ddt_nom = 20.5 K), cop_nom 0.75
(typical single-effect units 0.65-0.80). With the challenge's warm 20 degC
chilled-water supply the evaporator term is large, so the machine can run on
lower drive temperatures than a conventional 7 degC chiller: a physically
expected effect.
"""

import numpy as np

from gemini_model.model_abstract import StaticModel

DEFAULTS = {
    "capacity_w": 5e6,  # nominal cooling capacity (W)
    "A": 2.5,
    "B": 1.5,
    "ddt_nom": 85.0 - 2.5 * 30.0 + 1.5 * 7.0,  # 20.5 K at 85/30/7 degC
    "ddt_min": 5.0,  # K: below this the machine produces no cooling
    "ddt_tau": 5.0,  # K: COP approach rate
    "cop_nom": 0.75,
    "cap_max": 1.2,  # max over-capacity at favourable conditions
    "aux_fraction": 0.02,  # electricity per unit of rejected heat
}


def absorption_performance(t_gen_mean_c, t_cooling_water_c, t_chilled_mean_c, p=None):
    """Vectorised: returns (capacity_fraction, cop, ddt)."""
    p = {**DEFAULTS, **(p or {})}
    ddt = np.asarray(t_gen_mean_c, float) - p["A"] * t_cooling_water_c + p["B"] * t_chilled_mean_c
    x = ddt - p["ddt_min"]
    frac = np.clip(x / (p["ddt_nom"] - p["ddt_min"]), 0.0, p["cap_max"])
    cop = np.where(x > 0, p["cop_nom"] * (1.0 - np.exp(-np.clip(x, 0, None) / p["ddt_tau"])), 0.0)
    return frac, cop, ddt


class AbsorptionChiller(StaticModel):
    """Inputs ``u``: cooling_load (W), drive_temperature_in (degC), drive_flow_capacity (W/K, hot
    water m*cp), cooling_water_temperature (degC), chilled_water_supply_temperature (degC),
    chilled_water_return_temperature (degC).

    Outputs: cooling (W, <= load and <= available capacity), cop, drive_heat (W),
    drive_temperature_out (degC), heat_rejected (W), power_el (W), capacity_fraction, ddt (K).
    The drive outlet temperature and the COP depend on each other, so they are
    solved by fixed-point iteration (converges in a few steps).
    """

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
        if "drive_flow_capacity" in u:
            c = u["drive_flow_capacity"]
        else:  # volumetric hot-water flow (m3/s), e.g. straight from a GEMINI filter or heat exchanger
            c = u["drive_flow_rate"] * self.parameters.get("fluid_density", 1000.0) * self.parameters.get("specific_heat", 4186.0)
        r = absorption_operate(u["cooling_load"], u["drive_temperature_in"], c, u["cooling_water_temperature"],
                               0.5 * (u["chilled_water_supply_temperature"] + u["chilled_water_return_temperature"]),
                               self.parameters, max_drive_dt=self.parameters.get("max_drive_dt", np.inf))
        self.output.update({k: float(v) for k, v in r.items()})
        if "drive_flow_rate" in u:
            self.output["drive_flow_rate"] = u["drive_flow_rate"]
        if "pressure_in" in u:  # no hydraulic model: pressure passes through
            self.output["pressure_out"] = u["pressure_in"]
        self.output["power_th"] = 0.0
        self.output["emission"] = 0.0

    def get_output(self):
        return self.output


def absorption_operate(load_w, t_drive_in_c, drive_capacity_w_k, t_cw_c, t_chw_mean_c, p=None, max_drive_dt=np.inf):
    """Vectorised operation: cooling delivered, drive heat drawn from the hot-water stream, etc.

    ``max_drive_dt`` limits how far the drive stream may be cooled (e.g. the brine cooling cap).
    """
    p = {**DEFAULTS, **(p or {})}
    load = np.asarray(load_w, float)
    t_in = np.asarray(t_drive_in_c, float)
    c = np.asarray(drive_capacity_w_k, float)
    cool = np.minimum(load, p["capacity_w"] * p["cap_max"])
    t_mean = t_in.copy()
    for _ in range(6):
        frac, cop, ddt = absorption_performance(t_mean, t_cw_c, t_chw_mean_c, p)
        cool = np.minimum(np.minimum(load, p["capacity_w"] * frac), cool + 1e-9)
        with np.errstate(divide="ignore", invalid="ignore"):
            drive = np.where(cop > 0, cool / cop, 0.0)
            dt = np.where(c > 0, drive / c, 0.0)
        over = dt > max_drive_dt
        if np.any(over):
            cool = np.where(over, max_drive_dt * c * cop, cool)
            drive = np.where(over, max_drive_dt * c, drive)
            dt = np.minimum(dt, max_drive_dt)
        t_mean = t_in - 0.5 * dt
    cool = np.where(cop > 0, cool, 0.0)
    drive = np.where(cop > 0, drive, 0.0)
    rejected = cool + drive
    return {"cooling": cool, "cop": cop, "drive_heat": drive, "drive_temperature_out": t_in - np.where(cop > 0, dt, 0.0),
            "heat_rejected": rejected, "power_el": p["aux_fraction"] * rejected, "capacity_fraction": frac, "ddt": ddt}
