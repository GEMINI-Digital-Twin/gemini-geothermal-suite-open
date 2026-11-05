"""Shared helpers of the agent tools: argument range checks, rounding, and the cached heating and cooling years."""
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

import geo.gemini_path  # noqa: F401,E402  (puts the GEMINI tree on the path)
from geo.common import DEPTH_M  # noqa: E402
from geo.well import ESP_DEPTH_M  # noqa: E402
from geo import outage, year  # noqa: E402

gwh = lambda s: float(s.sum() * 24 / 1000)


def r2(d):
    """Make a result JSON-ready: text, bools and ints kept, other numbers rounded to 2 decimals (CO2 to 3)."""
    def one(k, v):
        if isinstance(v, (str, bool, np.bool_)):
            return v if isinstance(v, str) else bool(v)
        if isinstance(v, (int, np.integer)):
            return int(v)
        return round(float(v), 3 if k.startswith("co2_") else 2)
    return {k: one(k, v) for k, v in d.items()}


def _need(name, x, lo, hi):
    if x is not None and not lo <= x <= hi:
        raise ValueError(f"{name}={x} outside {lo}-{hi}")


def _peaks(peak_heat_MW, peak_cold_MW):
    _need("peak_heat_MW", peak_heat_MW, 1, 100)
    _need("peak_cold_MW", peak_cold_MW, 0, 50)


def _esp(esp_depth_m):
    """ESP setting depth, 300-1 250 m; None gives the 1 100 m default."""
    _need("esp_depth_m", esp_depth_m, 300, 1250)
    return ESP_DEPTH_M if esp_depth_m is None else float(esp_depth_m)


@lru_cache
def _heat(n, t, ph=None, depth=DEPTH_M, esp=None, mode="staggered"):
    _need("n_doublets", n, 1, 3)
    _need("t_return_c", t, 30, 70)
    _peaks(ph, None)
    _need("depth_m", depth, 1500, 4000)
    _mode(mode)
    return year.heating_year(int(n), float(t), peak_heat_MW=ph, depth_m=float(depth), esp_depth_m=_esp(esp), outage_mode=mode)


@lru_cache
def _cool(n, t, ph=None, pc=None, depth=DEPTH_M, esp=None):
    _peaks(ph, pc)
    return year.cooling_year(_heat(n, t, ph, depth, esp).surplus, peak_cold_MW=pc)


def _mode(outage_mode):
    if outage_mode not in outage.MODES:
        raise ValueError(f"outage_mode={outage_mode} not one of {outage.MODES}")
    return outage_mode
