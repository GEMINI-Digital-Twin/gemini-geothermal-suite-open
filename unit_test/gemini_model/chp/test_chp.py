"""Unit tests for CHP model.

Reference values use realistic data for a geothermal doublet surface
network (~10 MW doublet): gas_water_ratio=0.5 Nm3/m3,
efficiency_factor=0.8, caloric_value=50 MJ/kg, gas_emission_factor=56.6
kg/GJ. Flow rates, burner modulation (``u``) and secondary valve position
(``v``) are Q_p=Q_s=140 m3/h, u=80%, v=90%, matching the co-located Boiler
(see test_boiler.py), sharing the same gas/flow streams via the
complementary (1 - u)/(1 - v) fractions.
"""

import unittest

from gemini_model.chp.chp import CHP

CHP_PARAMS = {
    "gas_water_ratio": 0.5,  # Nm3/m3
    "efficiency_factor": 0.8,
    "caloric_value": 50e6,  # J/Nm3
    "gas_emission_factor": 56.6,  # kg CO2 / GJ
}

FLOW_RATE = 140.0 / 3600.0  # m3/s, realistic doublet flow of 140 m3/h

CHP_INPUT = {
    "temperature_in": 350.8711856072279,  # K, HeatExchanger secondary outlet
    "primary_flow_rate": FLOW_RATE,
    "secondary_flow_rate": FLOW_RATE,
    "burner_modulation": 0.8,  # boiler takes 80%, CHP takes remaining 20%
    "secondary_valve_position": 0.9,  # boiler takes 90%, CHP takes remaining 10%
    "grid_gas_flow_rate": 0.0,
}


class TestCHP(unittest.TestCase):
    """Test cases for CHP model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.chp = CHP()
        self.chp.update_parameters(dict(CHP_PARAMS))

    def test_chp_calculation(self):
        """Test CHP electrical power, heat output, outlet temperature, and emissions."""
        self.chp.calculate_output(dict(CHP_INPUT))
        y = self.chp.get_output()

        self.assertAlmostEqual(y["power_el"], 36296.296296296285, delta=1e-2)
        self.assertAlmostEqual(y["power_th"], 72592.59259259257, delta=1e-2)
        self.assertAlmostEqual(y["temperature_out"], 355.10398984003217, delta=1e-6)
        self.assertAlmostEqual(y["emission"], 0.007703888888888887, delta=1e-8)

    def test_electrical_power_is_half_of_thermal(self):
        """Test the fixed 1/3-2/3 electrical/thermal power split."""
        self.chp.calculate_output(dict(CHP_INPUT))
        y = self.chp.get_output()
        self.assertAlmostEqual(y["power_el"], y["power_th"] / 2)

    def test_zero_chp_flow_fraction_no_temperature_rise(self):
        """Test secondary_valve_position == 1 (all flow to boiler) leaves temperature unchanged."""
        u = dict(CHP_INPUT)
        u["secondary_valve_position"] = 1.0
        self.chp.calculate_output(u)
        y = self.chp.get_output()
        self.assertAlmostEqual(y["temperature_out"], CHP_INPUT["temperature_in"])

    def test_calculate_output_requires_required_inputs(self):
        """Test required CHP runtime inputs are validated."""
        with self.assertRaises(KeyError):
            self.chp.calculate_output({"temperature_in": 333.0})
