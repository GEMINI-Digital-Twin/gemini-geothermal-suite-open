"""Unit tests for HeatExchanger model.

Includes synthetic edge-case tests that verify the NTU-effectiveness
formula at special capacity ratios (cr == 1), plus a realistic test case
using realistic data for a geothermal doublet surface network (~10 MW
doublet): heat_transfer_coefficient=250e3 W/K, doublet flow
Q_p=Q_s=140 m3/h, secondary valve position v=0.9, with inlet temperatures
taken from the upstream Filter outlet and secondary network inlet.
"""

import unittest

from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger

FLOW_RATE = 0.01  # m3/s
CAPACITY = 1050.0 * FLOW_RATE * 4200.0  # W/K, using default density/specific heat

# Realistic doublet surface-network scenario
REAL_FLOW_RATE = 140.0 / 3600.0  # m3/s, realistic doublet flow of 140 m3/h
REAL_VALVE_POSITION = 0.9  # secondary valve position
REAL_PRIMARY_TEMPERATURE_IN = 351.15  # K, Filter forward outlet (see test_filter.py)
REAL_SECONDARY_TEMPERATURE_IN = 20.0 + 273.15  # K, secondary network inlet of 20 degC
REAL_HEAT_TRANSFER_COEFFICIENT = 250e3  # W/K


class TestHeatExchanger(unittest.TestCase):
    """Test cases for HeatExchanger model."""

    def test_counter_flow_equal_capacities(self):
        """Test counter-flow effectiveness at capacity ratio == 1 (ntu/(1+ntu))."""
        model = HeatExchanger()
        model.update_parameters(
            {
                "flow_resistance": 1e4,
                "heat_transfer_coefficient": CAPACITY,  # ntu = 1
                "flow_configuration": "counter",
            }
        )
        u = {
            "pressure_in": 20e5,
            "primary_temperature_in": 350.0,
            "secondary_temperature_in": 300.0,
            "primary_flow_rate": FLOW_RATE,
            "secondary_flow_rate": FLOW_RATE,
            "secondary_valve_position": 1.0,
        }
        model.calculate_output(u)
        y = model.get_output()

        self.assertAlmostEqual(y["pressure_out"], 20e5 - FLOW_RATE * 1e4)
        self.assertAlmostEqual(y["heat_duty"], 1102500.0, delta=1e-3)
        self.assertAlmostEqual(y["primary_temperature_out"], 325.0, delta=1e-6)
        self.assertAlmostEqual(y["secondary_temperature_out"], 325.0, delta=1e-6)
        self.assertEqual(y["power_th"], y["heat_duty"])
        self.assertEqual(y["power_el"], 0.0)

    def test_parallel_flow_equal_capacities(self):
        """Test parallel-flow effectiveness at capacity ratio == 1."""
        model = HeatExchanger()
        model.update_parameters(
            {
                "flow_resistance": 1e4,
                "heat_transfer_coefficient": CAPACITY,  # ntu = 1
                "flow_configuration": "parallel",
            }
        )
        u = {
            "pressure_in": 20e5,
            "primary_temperature_in": 350.0,
            "secondary_temperature_in": 300.0,
            "primary_flow_rate": FLOW_RATE,
            "secondary_flow_rate": FLOW_RATE,
            "secondary_valve_position": 1.0,
        }
        model.calculate_output(u)
        y = model.get_output()
        self.assertAlmostEqual(y["heat_duty"], 953292.85, delta=1e-1)

    def test_zero_secondary_valve_position_no_heat_transfer(self):
        """Test closed secondary valve results in no heat exchange."""
        model = HeatExchanger()
        model.update_parameters(
            {
                "flow_resistance": 1e4,
                "heat_transfer_coefficient": CAPACITY,
                "flow_configuration": "counter",
            }
        )
        u = {
            "pressure_in": 20e5,
            "primary_temperature_in": 350.0,
            "secondary_temperature_in": 300.0,
            "primary_flow_rate": FLOW_RATE,
            "secondary_flow_rate": FLOW_RATE,
            "secondary_valve_position": 0.0,
        }
        model.calculate_output(u)
        y = model.get_output()
        self.assertEqual(y["heat_duty"], 0.0)
        self.assertAlmostEqual(y["primary_temperature_out"], 350.0)
        self.assertAlmostEqual(y["secondary_temperature_out"], 300.0)

    def test_realistic_middenmeer_doublet_scenario(self):
        """Test counter-flow HEX with realistic surface-network parameters."""
        model = HeatExchanger()
        model.update_parameters(
            {
                "flow_resistance": 0.0,  # no pressure drop across the heat exchanger
                "heat_transfer_coefficient": REAL_HEAT_TRANSFER_COEFFICIENT,
                "flow_configuration": "counter",
            }
        )
        u = {
            "pressure_in": 845902.0685679979,  # Pa, Filter forward outlet
            "primary_temperature_in": REAL_PRIMARY_TEMPERATURE_IN,
            "secondary_temperature_in": REAL_SECONDARY_TEMPERATURE_IN,
            "primary_flow_rate": REAL_FLOW_RATE,
            "secondary_flow_rate": REAL_FLOW_RATE,
            "secondary_valve_position": REAL_VALVE_POSITION,
        }
        model.calculate_output(u)
        y = model.get_output()

        self.assertAlmostEqual(y["heat_duty"], 8909264.998475632, delta=1e-2)
        self.assertAlmostEqual(y["primary_temperature_out"], 299.2009329534948, delta=1e-6)
        self.assertAlmostEqual(y["secondary_temperature_out"], 350.8711856072279, delta=1e-6)

    def test_calculate_output_requires_required_inputs(self):
        """Test required HeatExchanger runtime inputs are validated."""
        model = HeatExchanger()
        model.update_parameters(
            {
                "flow_resistance": 1e4,
                "heat_transfer_coefficient": CAPACITY,
                "flow_configuration": "counter",
            }
        )
        with self.assertRaises(KeyError):
            model.calculate_output({"pressure_in": 20e5})
