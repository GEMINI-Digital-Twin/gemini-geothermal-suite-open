"""Unit tests for Compressor model.

Reference values use realistic data for a multi-stage hydrogen
compressor: mass_flow=0.01 kg/s, inlet_pressure=1e5 Pa,
outlet_pressure=20e6 Pa, gas_constant=4124.2 J/(kg.K), with mechanical
and compressor efficiencies and a two-stage configuration.
"""

import unittest

from gemini_model.compressor.compressor import Compressor

COMPRESSOR_PARAMS = {
    "specific_heat_ratio": 1.41,  # hydrogen
    "inlet_temperature": 298.0,  # K
    "inlet_pressure": 1e5,  # Pa
    "outlet_pressure": 20e6,  # Pa
    "gas_constant": 4124.2,  # J/(kg.K), hydrogen
    "mechanical_efficiency": 0.97,
    "compressor_efficiency": 0.88,
    "number_of_stages": 2,
}

COMPRESSOR_INPUT = {
    "mass_flow": 0.01,  # kg/s
}


class TestCompressor(unittest.TestCase):
    """Test cases for Compressor model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.compressor = Compressor()
        self.compressor.update_parameters(dict(COMPRESSOR_PARAMS))

    def test_compressor_calculation(self):
        """Test compressor power calculation with ideal intercooling."""
        self.compressor.calculate_output(dict(COMPRESSOR_INPUT))
        y = self.compressor.get_output()

        self.assertAlmostEqual(y["compressor_power"], 81504.0451457452, delta=1e-3)
        self.assertEqual(y["mass_flow"], 0.01)

    def test_zero_mass_flow_gives_zero_power(self):
        """Test zero mass flow results in zero compressor power."""
        self.compressor.calculate_output({"mass_flow": 0.0})
        y = self.compressor.get_output()
        self.assertEqual(y["compressor_power"], 0.0)

    def test_calculate_output_requires_required_inputs(self):
        """Test required Compressor runtime inputs are validated."""
        with self.assertRaises(KeyError):
            self.compressor.calculate_output({})
