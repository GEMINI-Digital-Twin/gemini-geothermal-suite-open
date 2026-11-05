"""Organic Rankine cycle (ORC) power unit on hot brine, air-cooled.

A binary power plant: the brine heats an organic working fluid, which
drives a turbine and condenses in an air-cooled condenser. The model is a
second-law one: the net power is a fixed fraction of the exergy the brine
gives up between its inlet and outlet, taken against the condensing
temperature (outdoor air + condenser approach)::

    P_net = eps * m * cp * [(T_in - T_out) - T_cond * ln(T_in / T_out)]   (kelvin)

``eps`` (``second_law_fraction``) lumps the turbine, feed pump,
generator, pinch losses and condenser fans. Calibrated against a
subcritical cycle with the best of seven working fluids (isobutane,
n-butane, isopentane, R245fa, R1233zd(E), R134a, propane; CoolProp,
turbine 0.82, feed pump 0.70, generator 0.96, 5 K evaporator pinch,
condenser fans 1.5 % of the heat rejected), eps is 0.45-0.54 for brine at
100-140 degC and 0.33-0.45 below 90 degC (see
``simulator_examples/run_orc_cycle_check.py``). The default of 0.45
matches the cycle model at ~100 degC and is optimistic below ~90 degC.

The brine is cooled down to the highest of: the minimum outlet the caller
allows (e.g. the 40 K brine cool-down cap) and the condensing temperature
plus ``min_outlet_above_condensing``. Output is capped at the rated net
power (the brine then leaves warmer). Below ``plr_min`` of the rating the
unit is off; at part load ``eps`` falls linearly by up to
``part_load_penalty``.
"""

import math

from gemini_model.model_abstract import StaticModel

K = 273.15


class OrganicRankineCycle(StaticModel):
    """Air-cooled ORC binary power unit on brine (second-law model)."""

    DEFAULTS = {
        "capacity_net": 0.0,  # W_e, rated net output (0 = no unit)
        "second_law_fraction": 0.45,
        "condenser_approach": 15.0,  # K, condensing temperature above the outdoor air
        "min_outlet_above_condensing": 20.0,  # K, brine outlet floor above condensing
        "plr_min": 0.3,  # off below this share of the rating
        "part_load_penalty": 0.15,  # eps x (1 - penalty x (1 - plr))
        "fluid_density": 1030.0,  # kg/m3, brine
        "specific_heat": 4180.0,  # J/(kg.K), brine
    }

    def __init__(self):
        """Model initialization with default parameters."""
        super().__init__()
        self.parameters = dict(self.DEFAULTS)

    @staticmethod
    def _exergy_k(t_in_k, t_out_k, t_cond_k):
        """Brine exergy drop per unit heat capacity (K), against the condensing temperature."""
        if t_out_k >= t_in_k:
            return 0.0
        return (t_in_k - t_out_k) - t_cond_k * math.log(t_in_k / t_out_k)

    def calculate_output(self, u, x=None):
        """Net power and brine outlet for one steady operating point.

        Inputs (``u``): ``hot_temperature_in`` (degC), ``hot_flow_rate``
        (m3/s), ``air_temperature`` (degC) and optionally
        ``hot_temperature_out_min`` (degC, e.g. the brine cool-down cap).
        """
        p = self.parameters
        t_in = float(u["hot_temperature_in"])
        flow = max(0.0, float(u["hot_flow_rate"]))
        t_air = float(u["air_temperature"])
        t_cond = t_air + p["condenser_approach"]
        floor = t_cond + p["min_outlet_above_condensing"]
        if u.get("hot_temperature_out_min") is not None:
            floor = max(floor, float(u["hot_temperature_out_min"]))
        cap = p["fluid_density"] * p["specific_heat"] * flow  # W/K
        eps = p["second_law_fraction"]
        rating = p["capacity_net"]

        def power(t_out, e):
            return e * cap * self._exergy_k(t_in + K, t_out + K, t_cond + K)

        t_out, p_net = t_in, 0.0
        if rating > 0 and cap > 0 and t_in > floor + 0.1:
            t_out = floor
            p_net = power(t_out, eps)
            if p_net > rating:  # rated output reached: the brine leaves warmer
                lo, hi = floor, t_in
                for _ in range(60):
                    mid = 0.5 * (lo + hi)
                    lo, hi = (mid, hi) if power(mid, eps) > rating else (lo, mid)
                t_out = hi
                p_net = power(t_out, eps)
            plr = p_net / rating
            if plr < p["plr_min"]:
                t_out, p_net = t_in, 0.0
            elif plr < 1.0:
                p_net = power(t_out, eps * (1.0 - p["part_load_penalty"] * (1.0 - plr)))
        heat_in = cap * (t_in - t_out)
        self.output = {
            "power_el": p_net,
            "heat_in": heat_in,
            "heat_rejected": heat_in - p_net,
            "hot_temperature_out": t_out,
            "condensing_temperature": t_cond,
            "efficiency": p_net / heat_in if heat_in > 0 else 0.0,
            # upper bound: Carnot between the brine inlet and the outdoor air
            "carnot_efficiency": max(0.0, 1.0 - (t_air + K) / (t_in + K)),
            "part_load_ratio": p_net / rating if rating > 0 else 0.0,
        }
