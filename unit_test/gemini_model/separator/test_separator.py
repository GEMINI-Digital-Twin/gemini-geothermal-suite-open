"""Unit tests for Separator model.

Reference values use realistic data for a geothermal doublet's surface
network (~10 MW doublet): flow resistance R1=0.001 bar/(m3/h), converted
to SI (1 bar/(m3/h) = 3.6e8 Pa/(m3/s)); doublet flow rate 140 m3/h;
producer wellhead pressure/temperature of 10 bar / 80 degC.
"""

import unittest

from gemini_model.separator.separator import Separator

SEPARATOR_PARAMS = {
    "flow_resistance": 0.001 * 3.6e8,  # Pa/(m3/s), 0.001 bar/(m3/h)
    "temperature_drop": 1.0,  # K
}

FLOW_RATE = 140.0 / 3600.0  # m3/s, realistic doublet flow of 140 m3/h
PRESSURE_IN = 10e5  # Pa, producer wellhead pressure of 10 bar
TEMPERATURE_IN = 80.0 + 273.15  # K, producer wellhead temperature of 80 degC


class TestSeparator(unittest.TestCase):
    """Test cases for Separator model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.separator = Separator()
        self.separator.update_parameters(dict(SEPARATOR_PARAMS))

    def test_forward_calculation(self):
        """Test forward pressure/temperature drop calculation."""
        u = {
            "pressure": PRESSURE_IN,
            "temperature": TEMPERATURE_IN,
            "flow_rate": FLOW_RATE,
            "direction": "forward",
        }
        self.separator.calculate_output(u)
        y = self.separator.get_output()

        self.assertAlmostEqual(y["pressure_in"], PRESSURE_IN)
        self.assertAlmostEqual(y["pressure_out"], 986000.0, delta=1e-3)
        self.assertAlmostEqual(y["temperature_in"], TEMPERATURE_IN)
        self.assertAlmostEqual(y["temperature_out"], 352.15, delta=1e-6)
        self.assertEqual(y["power_el"], 0.0)
        self.assertEqual(y["power_th"], 0.0)
        self.assertEqual(y["emission"], 0.0)

    def test_backward_calculation(self):
        """Test backward pressure/temperature drop calculation."""
        pressure_out = 986000.0
        temperature_out = 352.15
        u = {
            "pressure": pressure_out,
            "temperature": temperature_out,
            "flow_rate": FLOW_RATE,
            "direction": "backward",
        }
        self.separator.calculate_output(u)
        y = self.separator.get_output()

        self.assertAlmostEqual(y["pressure_out"], pressure_out)
        self.assertAlmostEqual(y["pressure_in"], PRESSURE_IN, delta=1e-3)
        self.assertAlmostEqual(y["temperature_out"], temperature_out)
        self.assertAlmostEqual(y["temperature_in"], TEMPERATURE_IN, delta=1e-6)

    def test_invalid_direction_raises(self):
        """Test unsupported direction raises ValueError."""
        u = {
            "pressure": PRESSURE_IN,
            "temperature": TEMPERATURE_IN,
            "flow_rate": FLOW_RATE,
            "direction": "sideways",
        }
        with self.assertRaises(ValueError):
            self.separator.calculate_output(u)

    def test_calculate_output_requires_required_inputs(self):
        """Test required Separator runtime inputs are validated."""
        with self.assertRaises(KeyError):
            self.separator.calculate_output({"pressure": PRESSURE_IN})

    def test_initialize_and_update_state_are_noop_for_static_model(self):
        """Test StaticModel no-state defaults on Separator."""
        self.assertIsNone(self.separator.initialize_state(None))
        self.assertIsNone(
            self.separator.update_state(
                {
                    "pressure": PRESSURE_IN,
                    "temperature": TEMPERATURE_IN,
                    "flow_rate": FLOW_RATE,
                    "direction": "forward",
                },
                None,
            )
        )
