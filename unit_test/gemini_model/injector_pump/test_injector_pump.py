"""Unit tests for InjectorPump model.

Parameters use realistic data for a geothermal doublet surface network
(~10 MW doublet): efficiency_factor=0.8, electricity_emission_factor=0.3
kg CO2/kWh. Flow rate and inlet pressure continue the same doublet chain
(BoosterPump forward outlet, see test_booster_pump.py); the outlet
pressure is an assumed injector wellhead target pressure.
"""

import unittest

from gemini_model.injector_pump.injector_pump import InjectorPump

INJECTOR_PARAMS = {
    "efficiency_factor": 0.8,
    "electricity_emission_factor": 0.3,  # kg CO2/kWh
}

FLOW_RATE = 140.0 / 3600.0  # m3/s, realistic doublet flow of 140 m3/h
PRESSURE_IN = 691804.1371359958  # Pa, BoosterPump forward outlet


class TestInjectorPump(unittest.TestCase):
    """Test cases for InjectorPump model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.pump = InjectorPump()
        self.pump.update_parameters(dict(INJECTOR_PARAMS))

    def test_power_and_emission_calculation(self):
        """Test power/emission for a realistic positive injector pressure boost."""
        pressure_out = 750000.0  # Pa, above the BoosterPump outlet pressure
        u = {
            "pressure_in": PRESSURE_IN,
            "pressure_out": pressure_out,
            "flow_rate": FLOW_RATE,
        }
        self.pump.calculate_output(u)
        y = self.pump.get_output()

        expected_power = FLOW_RATE * (pressure_out - PRESSURE_IN) / 0.8
        expected_emission = 0.3 / 3.6e6 * expected_power

        self.assertAlmostEqual(y["power_el"], expected_power)
        self.assertAlmostEqual(y["emission"], expected_emission)
        self.assertEqual(y["power_th"], 0.0)

    def test_negative_pressure_difference_clamped_to_zero(self):
        """Test power is clamped to zero when outlet pressure is below inlet."""
        u = {
            "pressure_in": PRESSURE_IN,
            "pressure_out": 5e5,  # Pa, below the BoosterPump outlet pressure
            "flow_rate": FLOW_RATE,
        }
        self.pump.calculate_output(u)
        y = self.pump.get_output()
        self.assertEqual(y["power_el"], 0.0)
        self.assertEqual(y["emission"], 0.0)

    def test_calculate_output_requires_required_inputs(self):
        """Test required InjectorPump runtime inputs are validated."""
        with self.assertRaises(KeyError):
            self.pump.calculate_output({"pressure_in": PRESSURE_IN})
