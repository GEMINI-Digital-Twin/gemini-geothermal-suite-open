"""Unit tests for Splitter model.

Reference values use a realistic secondary-loop flow for a geothermal
doublet plant (140 m3/h) split between a Boiler and a CHP branch.
"""

import unittest

from gemini_model.splitter.splitter import Splitter

TOTAL_FLOW = 140.0 / 3600.0  # m3/s


class TestSplitter(unittest.TestCase):
    """Test cases for Splitter model."""

    def test_splits_into_two_outputs_by_default(self):
        """Test the default 50/50, 2-output split."""
        splitter = Splitter()
        u = {"input": TOTAL_FLOW}
        splitter.calculate_output(u)
        y = splitter.get_output()

        self.assertAlmostEqual(y["output_0"], TOTAL_FLOW * 0.5)
        self.assertAlmostEqual(y["output_1"], TOTAL_FLOW * 0.5)

    def test_splits_into_n_outputs_with_custom_fractions(self):
        """Test splitting into three branches (e.g. Boiler/CHP/bypass)."""
        splitter = Splitter()
        splitter.update_parameters({"split_fractions": [0.6, 0.3, 0.1]})
        u = {"input": TOTAL_FLOW}
        splitter.calculate_output(u)
        y = splitter.get_output()

        self.assertAlmostEqual(y["output_0"], TOTAL_FLOW * 0.6)
        self.assertAlmostEqual(y["output_1"], TOTAL_FLOW * 0.3)
        self.assertAlmostEqual(y["output_2"], TOTAL_FLOW * 0.1)
        self.assertAlmostEqual(y["output_0"] + y["output_1"] + y["output_2"], TOTAL_FLOW)

    def test_fractions_not_summing_to_one_raises(self):
        """Test split_fractions that do not sum to 1 raise ValueError."""
        splitter = Splitter()
        splitter.update_parameters({"split_fractions": [0.6, 0.3]})
        u = {"input": TOTAL_FLOW}

        with self.assertRaises(ValueError):
            splitter.calculate_output(u)

    def test_single_output_passes_value_through(self):
        """Test the degenerate 1-output case passes the value through."""
        splitter = Splitter()
        splitter.update_parameters({"split_fractions": [1.0]})
        u = {"input": TOTAL_FLOW}
        splitter.calculate_output(u)
        y = splitter.get_output()

        self.assertAlmostEqual(y["output_0"], TOTAL_FLOW)
