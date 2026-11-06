"""Unit tests for Boiler model.

Reference values use realistic data for a geothermal doublet surface
network (~10 MW doublet): efficiency_factor=0.8, caloric_value=50 MJ/kg,
gas_emission_factor=56.6 kg/GJ. The gas mass flow rate and water flow
rate below are the already-allocated (post-Splitter) values, derived from
Q_p=Q_s=140 m3/h, gas_water_ratio=0.5 Nm3/m3, gas_density=0.7 kg/Nm3,
with this boiler taking an 80% gas fraction and a 90% water fraction of
the shared streams. The water inlet temperature continues the chain from
the HeatExchanger secondary outlet (see test_heat_exchanger.py).
"""

import unittest

from gemini_model.boiler.boiler import Boiler

BOILER_PARAMS = {
    "efficiency_factor": 0.8,
    "caloric_value": 50e6,  # J/kg
    "gas_emission_factor": 56.6,  # kg CO2 / GJ
}

FLOW_RATE = 140.0 / 3600.0  # m3/s, realistic doublet flow of 140 m3/h
GAS_WATER_RATIO = 0.5  # Nm3/m3
GAS_DENSITY = 0.7  # kg/Nm3
BOILER_GAS_FRACTION = 0.8
BOILER_WATER_FRACTION = 0.9

# already-allocated (post-Splitter) gas mass flow and water flow rate
GAS_FLOW_RATE = BOILER_GAS_FRACTION * GAS_WATER_RATIO * FLOW_RATE * GAS_DENSITY  # kg/s
WATER_FLOW_RATE = BOILER_WATER_FRACTION * FLOW_RATE  # m3/s

BOILER_INPUT = {
    "temperature_in": 350.8711856072279,  # K, HeatExchanger secondary outlet
    "water_flow_rate": WATER_FLOW_RATE,
    "gas_flow_rate": GAS_FLOW_RATE,
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

    def test_zero_water_flow_no_temperature_rise(self):
        """Test zero (already-split) water flow leaves temperature unchanged."""
        u = dict(BOILER_INPUT)
        u["water_flow_rate"] = 0.0
        self.boiler.calculate_output(u)
        y = self.boiler.get_output()
        self.assertAlmostEqual(y["temperature_out"], BOILER_INPUT["temperature_in"])

    def test_calculate_output_requires_required_inputs(self):
        """Test required Boiler runtime inputs are validated."""
        with self.assertRaises(KeyError):
            self.boiler.calculate_output({"temperature_in": 333.0})

    def test_volumetric_gas_flow_rate_matches_mass_flow_rate(self):
        """Test gas_volumetric_flow_rate (via gas_density) matches an equivalent mass flow."""
        u = dict(BOILER_INPUT)
        del u["gas_flow_rate"]
        u["gas_volumetric_flow_rate"] = GAS_FLOW_RATE / GAS_DENSITY

        boiler_params_with_density = dict(BOILER_PARAMS)
        boiler_params_with_density["gas_density"] = GAS_DENSITY
        self.boiler.update_parameters(boiler_params_with_density)

        self.boiler.calculate_output(u)
        y = self.boiler.get_output()

        self.boiler.calculate_output(dict(BOILER_INPUT))
        y_reference = self.boiler.get_output()

        self.assertAlmostEqual(y["power_th"], y_reference["power_th"], delta=1e-6)
        self.assertAlmostEqual(y["temperature_out"], y_reference["temperature_out"], delta=1e-9)
        self.assertAlmostEqual(y["emission"], y_reference["emission"], delta=1e-9)
