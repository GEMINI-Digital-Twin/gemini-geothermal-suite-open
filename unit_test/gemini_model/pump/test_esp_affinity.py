"""Unit tests for the similarity-law ESP model."""

import unittest

from gemini_model.pump.esp import ESP
from gemini_model.pump.esp_affinity import ESPAffinity

# pump HC27000, as test_esp.py
ESP_PARAMS = {
    "no_stages": 12,
    "head_coeff": [83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21],
    "power_coeff": [10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23],
}
Q_REF = 200 / 3600  # m3/s


def _run(model_class, freq, flow):
    model = model_class()
    model.update_parameters(dict(ESP_PARAMS))
    model.calculate_output({"pump_freq": freq, "pump_flow": flow})
    return model.get_output()


class TestESPAffinity(unittest.TestCase):
    """ESPAffinity reads the 60 Hz curve at q 60/f; ESP reads it at q."""

    def test_equals_esp_at_60_hz(self):
        """Both models agree at the curve's own frequency."""
        a, g = _run(ESPAffinity, 60, Q_REF), _run(ESP, 60, Q_REF)
        for key in ("pump_head", "pump_power", "pump_eff"):
            self.assertAlmostEqual(a[key], g[key], delta=1e-9)

    def test_homologous_point_48_hz(self):
        """At q proportional to f: head scales with f^2, power with f^3, efficiency is unchanged."""
        ref = _run(ESPAffinity, 60, Q_REF)
        y = _run(ESPAffinity, 48, 0.8 * Q_REF)
        self.assertAlmostEqual(y["pump_head"], 0.64 * ref["pump_head"], delta=1e-6)
        self.assertAlmostEqual(y["pump_power"], 0.512 * ref["pump_power"], delta=1e-6)
        self.assertAlmostEqual(y["pump_eff"], ref["pump_eff"], delta=1e-9)

    def test_esp_differs_off_60_hz(self):
        """ESP head at 48 Hz, 160 m3/h exceeds the similarity-law head by over 10 %."""
        g = _run(ESP, 48, 160 / 3600)["pump_head"]
        a = _run(ESPAffinity, 48, 160 / 3600)["pump_head"]
        self.assertGreater(100 * (g - a) / a, 10.0)

    def test_zero_frequency_rejected(self):
        """A non-positive frequency cannot be scaled to 60 Hz."""
        with self.assertRaises(ValueError):
            _run(ESPAffinity, 0, Q_REF)


if __name__ == "__main__":
    unittest.main()
