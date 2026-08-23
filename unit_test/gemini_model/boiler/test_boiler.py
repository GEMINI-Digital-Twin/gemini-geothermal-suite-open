"""Unit tests for Boiler model.

Reference values use realistic data for a geothermal doublet surface
network (~10 MW doublet): gas_water_ratio=0.5 Nm3/m3,
efficiency_factor=0.8, caloric_value=50 MJ/kg, gas_emission_factor=56.6
kg/GJ. Flow rates, burner modulation (``u``) and secondary valve position
(``v``) are Q_p=Q_s=140 m3/h, u=80%, v=90%. The secondary inlet
temperature continues the chain from the HeatExchanger secondary outlet
(see test_heat_exchanger.py).
"""

import unittest

from gemini_model.boiler.boiler import Boiler

BOILER_PARAMS = {
    "gas_water_ratio": 0.5,  # Nm3/m3
    "efficiency_factor": 0.8,
    "caloric_value": 50e6,  # J/Nm3
    "gas_emission_factor": 56.6,  # kg CO2 / GJ
}

FLOW_RATE = 140.0 / 3600.0  # m3/s, realistic doublet flow of 140 m3/h

BOILER_INPUT = {
    "temperature_in": 350.8711856072279,  # K, HeatExchanger secondary outlet
    "primary_flow_rate": FLOW_RATE,
    "secondary_flow_rate": FLOW_RATE,
    "burner_modulation": 0.8,
    "secondary_valve_position": 0.9,
    "grid_gas_flow_rate": 0.0,
}


class TestBoiler(unittest.TestCase):
    """Test cases for Boiler model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.boiler = Boiler()
        self.boiler.update_parameters(dict(BOILER_PARAMS))

    def test_boiler_calculation(self):
        """Test boiler heat output, outlet temperature, and emissions."""
        self.boiler.calculate_output(dict(BOILER_INPUT))
        y = self.boiler.get_output()

        self.assertAlmostEqual(y["power_th"], 435555.5555555555, delta=1e-2)
        self.assertAlmostEqual(y["temperature_out"], 353.69305509576407, delta=1e-6)
        self.assertAlmostEqual(y["emission"], 0.030815555555555554, delta=1e-8)
        self.assertEqual(y["power_el"], 0.0)

    def test_zero_secondary_flow_no_temperature_rise(self):
        """Test closed secondary valve leaves temperature unchanged."""
        u = dict(BOILER_INPUT)
        u["secondary_valve_position"] = 0.0
        self.boiler.calculate_output(u)
        y = self.boiler.get_output()
        self.assertAlmostEqual(y["temperature_out"], BOILER_INPUT["temperature_in"])

    def test_calculate_output_requires_required_inputs(self):
        """Test required Boiler runtime inputs are validated."""
        with self.assertRaises(KeyError):
            self.boiler.calculate_output({"temperature_in": 333.0})
