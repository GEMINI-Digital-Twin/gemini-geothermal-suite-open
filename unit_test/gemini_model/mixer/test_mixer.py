"""Unit tests for Mixer model.

Reference values mirror a boiler + CHP water outlet recombination in a
geothermal doublet secondary network: a hotter, lower-flow CHP branch
and a cooler, higher-flow boiler branch mixing into a single outlet.
"""

import unittest

from gemini_model.mixer.mixer import Mixer

BOILER_FLOW_M3S = 112.0 / 3600.0  # m3/s
BOILER_TEMPERATURE_C = 65.0
CHP_FLOW_M3S = 28.0 / 3600.0  # m3/s
CHP_TEMPERATURE_C = 55.0


class TestMixer(unittest.TestCase):
    """Test cases for Mixer model."""

    def test_flow_weighted_temperature_two_inputs(self):
        """Test the default 2-input configuration mixes flow and temperature."""
        mixer = Mixer()
        u = {
            "input_0_flow": BOILER_FLOW_M3S,
            "input_0_temperature": BOILER_TEMPERATURE_C,
            "input_1_flow": CHP_FLOW_M3S,
            "input_1_temperature": CHP_TEMPERATURE_C,
        }
        mixer.calculate_output(u)
        y = mixer.get_output()

        expected_flow = BOILER_FLOW_M3S + CHP_FLOW_M3S
        expected_temperature = (
            BOILER_FLOW_M3S * BOILER_TEMPERATURE_C + CHP_FLOW_M3S * CHP_TEMPERATURE_C
        ) / expected_flow

        self.assertAlmostEqual(y["flow"], expected_flow)
        self.assertAlmostEqual(y["temperature"], expected_temperature)

    def test_mixes_n_inputs(self):
        """Test mixing three numbered branches."""
        mixer = Mixer()
        mixer.update_parameters({"num_inputs": 3})
        u = {
            "input_0_flow": 60.0 / 3600.0,
            "input_0_temperature": 70.0,
            "input_1_flow": 50.0 / 3600.0,
            "input_1_temperature": 60.0,
            "input_2_flow": 30.0 / 3600.0,
            "input_2_temperature": 50.0,
        }
        mixer.calculate_output(u)
        y = mixer.get_output()

        expected_flow = 140.0 / 3600.0
        expected_temperature = (
            60.0 / 3600.0 * 70.0 + 50.0 / 3600.0 * 60.0 + 30.0 / 3600.0 * 50.0
        ) / expected_flow

        self.assertAlmostEqual(y["flow"], expected_flow)
        self.assertAlmostEqual(y["temperature"], expected_temperature)

    def test_missing_input_raises_keyerror(self):
        """Test a missing numbered flow/temperature input is validated and raises KeyError."""
        mixer = Mixer()
        u = {"input_0_flow": BOILER_FLOW_M3S, "input_0_temperature": BOILER_TEMPERATURE_C}

        with self.assertRaises(KeyError):
            mixer.calculate_output(u)

    def test_zero_total_flow_falls_back_to_plain_average(self):
        """Test that a zero total flow avoids division by zero and averages temperatures."""
        mixer = Mixer()
        u = {
            "input_0_flow": 0.0,
            "input_0_temperature": 70.0,
            "input_1_flow": 0.0,
            "input_1_temperature": 50.0,
        }
        mixer.calculate_output(u)
        y = mixer.get_output()

        self.assertAlmostEqual(y["flow"], 0.0)
        self.assertAlmostEqual(y["temperature"], 60.0)
