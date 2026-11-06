"""Unit tests for Adder model.

Reference values use realistic flow rates for a geothermal doublet
field with three production wells joining a shared header, each
delivering a different share of a combined ~140 m3/h design flow
(e.g. 60, 50 and 30 m3/h), converted to SI (m3/s).
"""

import unittest

from gemini_model.adder.adder import Adder

WELL_1_FLOW = 60.0 / 3600.0  # m3/s
WELL_2_FLOW = 50.0 / 3600.0  # m3/s
WELL_3_FLOW = 30.0 / 3600.0  # m3/s


class TestAdder(unittest.TestCase):
    """Test cases for Adder model."""

    def test_sums_two_inputs_by_default(self):
        """Test the default 2-input configuration sums input_0 and input_1."""
        adder = Adder()
        u = {"input_0": WELL_1_FLOW, "input_1": WELL_2_FLOW}
        adder.calculate_output(u)
        y = adder.get_output()

        self.assertAlmostEqual(y["output"], WELL_1_FLOW + WELL_2_FLOW)

    def test_sums_n_inputs(self):
        """Test summing three numbered inputs (three wells into one header)."""
        adder = Adder()
        adder.update_parameters({"num_inputs": 3})
        u = {"input_0": WELL_1_FLOW, "input_1": WELL_2_FLOW, "input_2": WELL_3_FLOW}
        adder.calculate_output(u)
        y = adder.get_output()

        self.assertAlmostEqual(y["output"], WELL_1_FLOW + WELL_2_FLOW + WELL_3_FLOW)
        self.assertAlmostEqual(y["output"], 140.0 / 3600.0)

    def test_missing_input_raises_keyerror(self):
        """Test a missing numbered input is validated and raises KeyError."""
        adder = Adder()
        adder.update_parameters({"num_inputs": 3})
        u = {"input_0": WELL_1_FLOW, "input_1": WELL_2_FLOW}

        with self.assertRaises(KeyError):
            adder.calculate_output(u)

    def test_single_input(self):
        """Test the degenerate 1-input case passes the value through."""
        adder = Adder()
        adder.update_parameters({"num_inputs": 1})
        u = {"input_0": WELL_1_FLOW}
        adder.calculate_output(u)
        y = adder.get_output()

        self.assertAlmostEqual(y["output"], WELL_1_FLOW)
