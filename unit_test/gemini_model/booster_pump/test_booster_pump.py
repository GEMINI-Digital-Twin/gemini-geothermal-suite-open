"""Unit tests for BoosterPump model.

Reference values use realistic data for a geothermal doublet surface
network (~10 MW doublet): flow resistance C=0.01 bar/(m3/h), converted to
SI (1 bar/(m3/h) = 3.6e8 Pa/(m3/s)), for the same doublet flow
(Q=140 m3/h) used throughout the surface-equipment test suite.
"""

import unittest

from gemini_model.booster_pump.booster_pump import BoosterPump

BOOSTER_PARAMS = {
    "flow_resistance": 0.01 * 3.6e8,  # Pa/(m3/s), 0.01 bar/(m3/h)
    "temperature_drop": 1.0,  # K
}

FLOW_RATE = 140.0 / 3600.0  # m3/s, realistic doublet flow of 140 m3/h


class TestBoosterPump(unittest.TestCase):
    """Test cases for BoosterPump model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.pump = BoosterPump()
        self.pump.update_parameters(dict(BOOSTER_PARAMS))

    def test_forward_calculation(self):
        """Test forward pressure/temperature calculation."""
        pressure_in = 831804.1371359958  # Pa, FilterB forward outlet
        temperature_in = 298.2009329534948  # K, FilterB forward outlet
        u = {
            "pressure": pressure_in,
            "temperature": temperature_in,
            "flow_rate": FLOW_RATE,
            "direction": "forward",
        }
        self.pump.calculate_output(u)
        y = self.pump.get_output()
        self.assertAlmostEqual(y["pressure_out"], 691804.1371359958, delta=1e-3)
        self.assertAlmostEqual(y["temperature_out"], 297.2009329534948, delta=1e-6)

    def test_backward_calculation(self):
        """Test backward pressure/temperature calculation."""
        pressure_out = 691804.1371359958
        temperature_out = 297.2009329534948
        u = {
            "pressure": pressure_out,
            "temperature": temperature_out,
            "flow_rate": FLOW_RATE,
            "direction": "backward",
        }
        self.pump.calculate_output(u)
        y = self.pump.get_output()
        self.assertAlmostEqual(y["pressure_in"], 831804.1371359958, delta=1e-3)
        self.assertAlmostEqual(y["temperature_in"], 298.2009329534948, delta=1e-6)

    def test_invalid_direction_raises(self):
        """Test unsupported direction raises ValueError."""
        u = {
            "pressure": 831804.1371359958,
            "temperature": 298.2009329534948,
            "flow_rate": FLOW_RATE,
            "direction": "up",
        }
        with self.assertRaises(ValueError):
            self.pump.calculate_output(u)

    def test_calculate_output_requires_required_inputs(self):
        """Test required BoosterPump runtime inputs are validated."""
        with self.assertRaises(KeyError):
            self.pump.calculate_output({"pressure": 831804.1371359958})
