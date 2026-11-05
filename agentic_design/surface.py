"""Vectorised surface components for the annual model.

Heat pump: the same Lorenz-efficiency equation as GEMINI's ``HeatpumpBasic``
(mode="lorenz", eta_lorenz=0.5):

    COP = eta * Th_lm / (Th_lm - Ts_lm)

with Th_lm / Ts_lm the logarithmic mean temperatures (K) of the sink (network
water) and source (brine) glides. GEMINI solves it with a Nelder-Mead
optimiser per call (too slow for 365 days x 250 flows x 3 doublet counts),
so it is solved here by fixed-point iteration over arrays. ``verify.py``
cross-checks the result against GEMINI's own HeatpumpBasic.

Chillers come from the new GEMINI models in ``gemini_model.chiller``.
"""

import numpy as np

from gemini_model.chiller.absorption_chiller import absorption_operate  # noqa: F401 (re-exported)
from gemini_model.chiller.electric_chiller import electric_chiller_operate  # noqa: F401

K0 = 273.15


def _log_mean(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        lm = (a - b) / np.log(a / b)
    return np.where(np.abs(a - b) < 1e-6, a, lm)


def lorenz_cop(th_in_c, th_out_c, ts_in_c, ts_out_c, eta=0.5, cop_max=10.0):
    th = _log_mean(np.asarray(th_in_c) + K0, np.asarray(th_out_c) + K0)
    ts = _log_mean(np.asarray(ts_in_c) + K0, np.asarray(ts_out_c) + K0)
    with np.errstate(divide="ignore", invalid="ignore"):
        cop = np.where(th - ts > 0.5, eta * th / (th - ts), cop_max)
    return np.clip(cop, 1.0, cop_max)


def heat_pump_operate(capacity_mw, need_mw, c_sink_mw_k, t_sink_in_c, t_source_in_c, c_source_mw_k,
                      t_source_out_min_c, eta=0.5, iterations=10):
    """Heat delivered (MW), electricity (MW), COP, source outlet temperature, evaporator heat (MW).

    Limits: capacity, the network's remaining need, and the source (brine) may not be
    cooled below ``t_source_out_min_c`` (the brine cooling cap).
    """
    need = np.clip(np.asarray(need_mw, float), 0, None)
    q = np.minimum(capacity_mw, need)
    c_src = np.maximum(np.asarray(c_source_mw_k, float), 1e-12)
    c_snk = max(float(c_sink_mw_k), 1e-12)
    evap_max = np.clip(c_src * (np.asarray(t_source_in_c) - t_source_out_min_c), 0, None)
    cop = np.full_like(q, 3.0)
    for _ in range(iterations):
        q = np.minimum(q, evap_max / np.maximum(1.0 - 1.0 / cop, 1e-6))
        q = np.minimum(q, np.minimum(capacity_mw, need))
        evap = q * (1.0 - 1.0 / cop)
        ts_out = t_source_in_c - evap / c_src
        th_out = t_sink_in_c + q / c_snk
        cop = lorenz_cop(t_sink_in_c, th_out, t_source_in_c, ts_out, eta)
    evap = q * (1.0 - 1.0 / cop)
    return {"heat": q, "power": q / cop, "cop": np.where(q > 1e-9, cop, np.nan),
            "source_out_c": np.asarray(t_source_in_c) - evap / c_src, "evaporator_heat": evap,
            "sink_out_c": t_sink_in_c + q / c_snk}
