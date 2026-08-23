"""Unit tests for Filter model.

Reference values use realistic data for a geothermal doublet surface
filter: base resistance R0=0.01 bar/(m3/h), fouling coefficients
a=0.005 bar/(m3/h), b=1e-5 h/m3, converted to SI (1 bar/(m3/h) =
3.6e8 Pa/(m3/s); a rate constant expressed per m3/h is multiplied by 3600
to work with a flow rate in m3/s). The filter is placed downstream of the
Separator (~10 MW doublet, Q=140 m3/h), so its inlet pressure/temperature
are the Separator's forward outlet values.
"""

import math
import unittest

from gemini_model.filter.filter import Filter

FILTER_PARAMS = {
    "base_resistance": 0.01 * 3.6e8,  # Pa/(m3/s), 0.01 bar/(m3/h)
    "fouling_coeff_a": 0.005 * 3.6e8,  # Pa/(m3/s), 0.005 bar/(m3/h)
    "fouling_coeff_b": 1e-5 * 3600.0,  # s/m3, 1e-5 h/m3
    "temperature_drop": 1.0,  # K
}

FLOW_RATE = 140.0 / 3600.0  # m3/s, realistic doublet flow of 140 m3/h
PRESSURE_IN = 986000.0  # Pa, Separator forward outlet (see test_separator.py)
TEMPERATURE_IN = 352.15  # K, Separator forward outlet


class TestFilter(unittest.TestCase):
    """Test cases for Filter model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.filter_instance = Filter()
        self.filter_instance.update_parameters(dict(FILTER_PARAMS))

    def test_forward_calculation(self):
        """Test forward pressure/temperature drop calculation with fouling."""
        u = {
            "pressure": PRESSURE_IN,
            "temperature": TEMPERATURE_IN,
            "flow_rate": FLOW_RATE,
            "direction": "forward",
        }
        self.filter_instance.calculate_output(u)
        y = self.filter_instance.get_output()

        expected_resistance = (
            FILTER_PARAMS["fouling_coeff_a"]
            * (1 - math.exp(-FILTER_PARAMS["fouling_coeff_b"] * FLOW_RATE))
            + FILTER_PARAMS["base_resistance"]
        )

        self.assertAlmostEqual(y["flow_resistance"], 3602518.236822912, delta=1e-3)
        self.assertAlmostEqual(y["flow_resistance"], expected_resistance)
        self.assertAlmostEqual(y["pressure_out"], 845902.0685679979, delta=1e-3)
        self.assertAlmostEqual(y["temperature_out"], 351.15, delta=1e-6)

    def test_zero_flow_resistance_equals_base(self):
        """Test resistance approaches base_resistance at (near) zero flow."""
        u = {
            "pressure": PRESSURE_IN,
            "temperature": TEMPERATURE_IN,
            "flow_rate": 0.0,
            "direction": "forward",
        }
        self.filter_instance.calculate_output(u)
        y = self.filter_instance.get_output()
        self.assertAlmostEqual(y["flow_resistance"], FILTER_PARAMS["base_resistance"])
        self.assertAlmostEqual(y["pressure_out"], PRESSURE_IN)

    def test_backward_calculation(self):
        """Test backward pressure/temperature drop calculation."""
        expected_resistance = (
            FILTER_PARAMS["fouling_coeff_a"]
            * (1 - math.exp(-FILTER_PARAMS["fouling_coeff_b"] * FLOW_RATE))
            + FILTER_PARAMS["base_resistance"]
        )
        pressure_out = 845902.0685679979
        temperature_out = 351.15
        u = {
            "pressure": pressure_out,
            "temperature": temperature_out,
            "flow_rate": FLOW_RATE,
            "direction": "backward",
        }
        self.filter_instance.calculate_output(u)
        y = self.filter_instance.get_output()
        self.assertAlmostEqual(y["pressure_in"], pressure_out + FLOW_RATE * expected_resistance)
        self.assertAlmostEqual(y["temperature_in"], TEMPERATURE_IN, delta=1e-6)

    def test_calculate_output_requires_required_inputs(self):
        """Test required Filter runtime inputs are validated."""
        with self.assertRaises(KeyError):
            self.filter_instance.calculate_output({"pressure": PRESSURE_IN})
