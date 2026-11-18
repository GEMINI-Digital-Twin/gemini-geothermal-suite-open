"""A flat forecast window must keep the full-year corrosion rate."""

import unittest
from datetime import datetime

from gemini_application.wims.corrosion_from_prod_data import (
    build_prod_corrosion_context,
    corroded_mm_for_interval,
)

MODEL_RATE_MM_YR = 0.8
WINDOW_START = datetime(2025, 11, 11, 13, 57, 20)
WINDOW_END = datetime(2026, 11, 11, 13, 57, 20)
LATE_SAMPLE = datetime(2026, 11, 11, 12, 0, 0)


class _FixedRateModel:
    """Corrosion model that always returns one rate [mm/year]."""

    def __init__(self, rate_mm_yr):
        self.rate_mm_yr = rate_mm_yr
        self.output = {}

    def calculate_output(self, u, x):
        """Store the fixed corrosion rate."""
        self.output = {"corrosion_rate": self.rate_mm_yr}

    def get_output(self):
        """Return the stored corrosion rate."""
        return self.output


class _Pvt:
    """PVT stub. The forecast test only needs a finite gas density."""

    def get_pvt(self, temperature_c, pressure_bar):
        """Return a dummy gas density [kg/m3]."""
        return (1.0,)


class _Vlp:
    """VLP stub that echoes the inlet pressure [Pa] and temperature [K]."""

    def __init__(self):
        self.PVT = _Pvt()
        self.output = {}

    def calculate_output(self, u, x):
        """Echo one section so the joint keeps the inlet conditions."""
        self.output = {
            "section_pressure_output": [u["pressure"]],
            "section_temperature_output": [u["temperature"]],
        }

    def get_output(self):
        """Return the echoed section output."""
        return self.output


class _Co2:
    """CO2 model stub with a constant partial pressure [bar]."""

    def __init__(self):
        self.output = {}

    def calculate_output(self, u, x):
        """Store a constant CO2 partial pressure [bar]."""
        self.output = {"CO2 Partial Pressure [bar]": 0.4}

    def get_output(self):
        """Return the stored CO2 partial pressure."""
        return self.output


def _window_rate_mm_yr(inputs):
    """Integrated rate [mm/year] for one joint over the forecast window."""
    context = build_prod_corrosion_context(
        [{"Joint": "116"}],
        inputs,
        _Vlp(),
        [_Co2()],
        esp_joint_start_idx=0,
        verbose=False,
        boundaries=[WINDOW_START, WINDOW_END],
    )
    interval = context["intervals"][0]
    corroded_mm = corroded_mm_for_interval(interval, 0, _FixedRateModel(MODEL_RATE_MM_YR))
    return corroded_mm / interval["total_duration_yr"], interval


class TestFlatForecastWindow(unittest.TestCase):
    """A single late sample must represent the whole forecast year."""

    def test_end_of_window_sample_keeps_full_year_rate(self):
        """One finite sample near the end keeps the model rate, not a 2-hour tail."""
        # -- one flowing sample two hours before the window ends ------------
        inputs = {
            "time": [LATE_SAMPLE],
            "flow": [147.7],
            "pressure": [60.08],
            "temperature": [80.0],
        }

        # -- the reported rate is metal loss divided by the calendar year ---
        rate_mm_yr, interval = _window_rate_mm_yr(inputs)

        self.assertAlmostEqual(
            interval["step_durations_yr"].sum(), interval["total_duration_yr"], places=4
        )
        self.assertAlmostEqual(rate_mm_yr, MODEL_RATE_MM_YR, places=2)

    def test_nan_anchor_inside_window_does_not_shrink_the_rate(self):
        """A non-finite first sample must not leave only the short tail."""
        # -- empty anchor early in the year, then the year-average sample ---
        inputs = {
            "time": [datetime(2025, 11, 11, 14, 0, 0), LATE_SAMPLE],
            "flow": [float("nan"), 147.7],
            "pressure": [float("nan"), 60.08],
            "temperature": [float("nan"), 80.0],
        }

        rate_mm_yr, _interval = _window_rate_mm_yr(inputs)

        self.assertAlmostEqual(rate_mm_yr, MODEL_RATE_MM_YR, places=2)
