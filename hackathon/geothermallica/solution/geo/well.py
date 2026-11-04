"""Production and injection wells on the challenge inputs, built from GEMINI models.

Producer: reservoir inflow (IPR, inflow performance relationship) -> tubing below the pump -> electrical submersible pump (ESP)
-> tubing above. Injector: tubing down -> reservoir. Tubing uses DPDT, GEMINI's pipe-flow pressure-drop model.
Parameter sources are in the inline comments.
Producer.run() returns a dict of pressures, wellhead temperature and pump power; injector_at() a dict of injection pressures,
injection-pump power and the margin to the injection-pressure limit of SodM (Dutch State Supervision of Mines).
"""
from functools import lru_cache

import numpy as np

from geo.common import DEPTH_M, DT_BRINE_MAX_K, MU_PA_S, P_RES_BAR, PERM_MD, RHO, THICKNESS_M, T_SURFACE_C, t_reservoir_c
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.pump.esp import ESP
from gemini_model.pump.esp_affinity import ESPAffinity
from gemini_model.reservoir.inflow_performance import IPR
from gemini_model.well.pressure_drop import DPDT

BAR = 1e5                     # Pa per bar
Z_TOP_M = 2450.0              # reservoir top, m: the brief's 2 500 m midpoint minus half the 100 m thickness
# SodM maximum bottomhole injection pressure, bar: 0.135 bar per m of depth to the reservoir top; source: Mijnlieff 2015,
# TNO note AGE 15-10.072, quoting the SodM protocol for maximum injection pressures,
# https://acc.nlog.nl/sites/default/files/begeleidende%20notitie%20geomech.pdf
P_SODM_BAR = 0.135 * Z_TOP_M
TUBING_ID_M = 0.1778          # tubing inner diameter, m (7 inch); assumed, no source
ROUGHNESS_M = 4.5e-5          # tubing wall roughness, m, commercial steel; assumed, textbook value
# well spacing used as the drainage radius, and wellbore radius, m; values assumed. Using the spacing as the drainage
# radius follows the DoubletCalc 1.4 manual (TNO 2014, report R11396),
# https://acc.nlog.nl/sites/default/files/6ab98fc3-1ca1-4bbe-b0a2-c5a9658a3597_doubletcalc%20v143%20manual.pdf
SPACING_M, R_W_M = 1300.0, 0.108
CELL_M = 50.0                 # length of one DPDT pipe segment, m
ESP_DEPTH_M = 1100.0          # pump setting depth, m; design choice: deep enough that the pump intake stays above the gas bubble point
PUMP_EFF = 0.70               # pump efficiency (ESP and injection pump); from the challenge brief
# GEMINI example pump: head polynomial per stage; flow axis stretched so the best-efficiency point (BEP) sits at Q_BEP_M3H
EXAMPLE_HEAD_COEFF = [125.518426, -0.0020852856, 2.28955651e-07, -1.45640214e-11, 2.37859645e-16, -1.18258356e-21]
EXAMPLE_BEP_M3H, EXAMPLE_QMIN_M3H, EXAMPLE_QMAX_M3H = 129.98, 82.0, 178.0   # example pump BEP and operating range, m3/h
Q_BEP_M3H = 250.0             # BEP of our pump, m3/h; design choice


def sodm_limit_bar(depth_m=DEPTH_M):
    """SodM limit, bar: 0.135 bar/m times the reservoir top 50 m above depth_m (compared with pressure at depth_m: ~5 bar conservative)."""
    return 0.135 * (depth_m - (DEPTH_M - Z_TOP_M))


def productivity_index(depth_m=DEPTH_M):
    """Productivity index (PI), m3/h per bar: steady radial Darcy flow, PI = 2 pi k h / (mu ln(r_e / r_w))."""
    k = PERM_MD * 9.869e-16
    pi = 2 * np.pi * k * THICKNESS_M / (MU_PA_S * np.log(SPACING_M / R_W_M))
    return pi * 3600 * BAR          # m3/h/bar


def reservoir_pressure(depth_m=DEPTH_M):
    """Reservoir pressure at depth_m, bar: the brief's 250 bar at 2 500 m, plus or minus the brine column."""
    return P_RES_BAR + RHO * 9.81 * (depth_m - DEPTH_M) / BAR


def _well(length_m):
    """GEMINI DPDT model of a vertical tubing of length_m, split into CELL_M segments."""
    n = max(1, int(round(length_m / CELL_M)))
    w = DPDT()
    w.PVT = PVTConstantSTP()
    w.PVT.update_parameters({"RHOL": RHO, "VISL": MU_PA_S})
    w.update_parameters({
        "length": np.full(n, length_m / n), "diameter": np.full(n, TUBING_ID_M), "angle": np.full(n, np.pi / 2),
        "roughness": [ROUGHNESS_M] * n, "friction_correlation": "darcy_weisbach",
        "friction_correlation_2p": "BeggsBrill", "correction_factors": [1, 0],
    })
    return w


def _pump(stages, q_bep=Q_BEP_M3H, affinity=True):
    """ESPAffinity (or GEMINI's ESP if affinity is False) with the example head curve stretched to put its BEP at q_bep;
    power curve unused (zeros)."""
    s = EXAMPLE_BEP_M3H / q_bep
    p = ESPAffinity() if affinity else ESP()
    p.update_parameters({"no_stages": stages, "head_coeff": [c * s ** i for i, c in enumerate(EXAMPLE_HEAD_COEFF)],
                         "power_coeff": [0.0] * 6})
    return p


class Producer:
    """Production well with an ESP: reservoir inflow, tubing, pump and tubing, solved bottom up."""

    def __init__(self, depth_m=DEPTH_M, stages=30, esp_depth_m=ESP_DEPTH_M, affinity=True, q_bep=Q_BEP_M3H, pi=None):
        """Build the GEMINI models; pi overrides the productivity index (m3/h per bar)."""
        # affinity=True uses ESPAffinity, which reads the 60 Hz head curve at q x 60/f (pump similarity law);
        # affinity=False uses GEMINI's ESP, which reads it at q
        self.depth_m, self.stages, self.esp_depth_m, self.affinity = depth_m, stages, esp_depth_m, affinity
        self.t_res_c = t_reservoir_c(depth_m)
        self.p_res_bar = reservoir_pressure(depth_m)
        self.pi = productivity_index(depth_m) if pi is None else pi   # m3/h per bar
        self.q_min, self.q_max = (EXAMPLE_QMIN_M3H * q_bep / EXAMPLE_BEP_M3H,
                                  EXAMPLE_QMAX_M3H * q_bep / EXAMPLE_BEP_M3H)
        self.ipr = IPR()
        self.ipr.update_parameters({"type": "production_reservoir", "reservoir_pressure": self.p_res_bar,
                                    "productivity_index": self.pi})
        self.lower = _well(depth_m - esp_depth_m)
        self.upper = _well(esp_depth_m)
        self.pump = _pump(stages, q_bep, affinity)
        self.t_ambient_c = 0.5 * (T_SURFACE_C + self.t_res_c)   # one ambient T for the whole well

    def _leg(self, well, p_in_bar, t_in_c, q_m3h):
        """Pressure (bar) and temperature (C) at the top of one tubing section, flowing up."""
        well.calculate_output({"pressure": p_in_bar * BAR, "temperature": t_in_c + 273.15, "flowrate": q_m3h / 3600,
                               "temperature_ambient": self.t_ambient_c + 273.15, "direction": "up"}, None)
        y = well.get_output()
        return y["pressure_output"] / BAR, y["temperature_output"] - 273.15

    def run(self, q_m3h, freq_hz):
        """Dict of pressures (bar), wellhead temperature (C), pump head and power (kW) at q_m3h and freq_hz."""
        self.ipr.calculate_output({"flow": q_m3h}, None)
        p_bh = self.ipr.get_output()["bottomhole_pressure"]
        p_in, t_in = self._leg(self.lower, p_bh, self.t_res_c, q_m3h)
        self.pump.calculate_output({"pump_freq": freq_hz, "pump_flow": q_m3h / 3600})
        head_bar = self.pump.get_output()["pump_head"] / BAR
        p_wh, t_wh = self._leg(self.upper, p_in + head_bar, t_in, q_m3h)
        hydraulic_kw = head_bar * BAR * q_m3h / 3600 / 1e3
        return {"q_m3h": q_m3h, "freq_hz": freq_hz, "p_bottomhole_bar": p_bh, "p_esp_intake_bar": p_in,
                "esp_head_bar": head_bar, "p_wellhead_bar": p_wh, "T_wellhead_C": t_wh,
                "esp_hydraulic_kW": hydraulic_kw, "esp_electric_kW": hydraulic_kw / PUMP_EFF,
                "in_envelope": self.q_min <= q_m3h <= self.q_max}

    def freq_for_wellhead(self, q_m3h, p_wh_target_bar=10.0, f_lo=30.0, f_hi=60.0):
        """Lowest pump frequency (Hz) that holds the wellhead at p_wh_target_bar (bisection); None if 60 Hz is not enough."""
        if self.run(q_m3h, f_hi)["p_wellhead_bar"] < p_wh_target_bar:
            return None
        for _ in range(40):
            f = 0.5 * (f_lo + f_hi)
            if self.run(q_m3h, f)["p_wellhead_bar"] < p_wh_target_bar:
                f_lo = f
            else:
                f_hi = f
        return f_hi


def water_viscosity(t_c):
    """Water viscosity at t_c, Pa s, Vogel equation: mu = A 10^(B / (T - C)), T in K."""
    return 2.414e-5 * 10 ** (247.8 / (t_c + 273.15 - 140.0))


class Injector:
    """Injection well: wellhead -> DPDT down the same tubing -> reservoir, p_bh = p_res + q / II (II = injectivity index)."""

    def __init__(self, depth_m=DEPTH_M, gemini_sign=False, ii=None):
        """Set up the injector; ii overrides the injectivity index (m3/h per bar)."""
        # gemini_sign=True passes +q to DPDT "down" as GEMINI's simulator does (friction adds); False passes -q (physical)
        self.depth_m, self.gemini_sign, self.ii = depth_m, gemini_sign, ii
        self.t_res_c = t_reservoir_c(depth_m)
        self.p_res_bar = reservoir_pressure(depth_m)
        self.pi = productivity_index(depth_m)
        self.t_ambient_c = 0.5 * (T_SURFACE_C + self.t_res_c)

    def run(self, q_m3h, t_inj_c):
        """Dict of required bottomhole and wellhead pressure (bar) and injection-pump power (kW) at q_m3h and t_inj_c."""
        # injectivity = productivity scaled by viscosity, with the whole drainage area at the injection temperature
        ii = self.ii if self.ii is not None else self.pi * water_viscosity(self.t_res_c) / water_viscosity(t_inj_c)
        ipr = IPR()
        ipr.update_parameters({"type": "injection_reservoir", "reservoir_pressure": self.p_res_bar,
                               "injectivity_index": ii})
        ipr.calculate_output({"flow": q_m3h}, None)
        p_bh_req = ipr.get_output()["bottomhole_pressure"]
        w = _well(self.depth_m)
        w.PVT.update_parameters({"RHOL": RHO, "VISL": water_viscosity(t_inj_c)})
        sign = 1.0 if self.gemini_sign else -1.0
        w.calculate_output({"pressure": 0.0, "temperature": t_inj_c + 273.15, "flowrate": sign * q_m3h / 3600,
                            "temperature_ambient": self.t_ambient_c + 273.15, "direction": "down"}, None)
        p_bh_free = w.get_output()["pressure_output"] / BAR    # bottomhole with 0 bar at the wellhead
        p_wh = max(0.0, p_bh_req - p_bh_free)                  # constant density: bottomhole pressure moves 1:1 with wellhead pressure
        pump_kw = p_wh * BAR * q_m3h / 3600 / 1e3 / PUMP_EFF
        return {"q_m3h": q_m3h, "T_inj_C": t_inj_c, "II": ii, "p_bh_req_bar": p_bh_req, "p_bh_free_bar": p_bh_free,
                "p_wh_bar": p_wh, "pump_kW": pump_kw}


@lru_cache
def _injector_wells(depth_m=DEPTH_M):
    """Producer (24-stage pump), physical-sign injector and GEMINI-sign injector at depth_m (cached)."""
    return Producer(depth_m=depth_m, stages=24), Injector(depth_m=depth_m), Injector(depth_m=depth_m, gemini_sign=True)


def injector_at(q, depth_m=DEPTH_M):
    """Injector dict at q m3/h, brine at the producer's wellhead temperature minus 40 K; adds GEMINI-sign wellhead pressure and SodM margin."""
    prod, inj, inj_g = _injector_wells(depth_m)
    f = prod.freq_for_wellhead(q)
    t_inj = prod.run(q, f if f is not None else 60.0)["T_wellhead_C"] - DT_BRINE_MAX_K
    r = inj.run(q, t_inj)
    r["p_wh_gemini_sign_bar"] = inj_g.run(q, t_inj)["p_wh_bar"]
    r["sodm_limit_bar"] = sodm_limit_bar(depth_m)
    r["sodm_margin_bar"] = r["sodm_limit_bar"] - r["p_bh_req_bar"]
    return r
