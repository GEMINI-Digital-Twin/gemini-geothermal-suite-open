"""Unit tests for reservoir inflow performance model."""

import unittest

from gemini_model.reservoir.inflow_performance import IPR


class TestESP(unittest.TestCase):
    """Test cases for reservoir inflow performance model."""

    def test_calculate_bottomhole(self):
        """Test reservoir inflow performance calculation."""
        # ARRANGE
        res_param = dict()

        res_param["reservoir_pressure"] = 300
        res_param["productivity_index"] = 5
        res_param["type"] = "production_reservoir"

        res_instance = IPR()
        res_instance.update_parameters(res_param)

        x = []

        u = dict()
        u["flow"] = 100

        # ACT
        res_instance.calculate_output(u, x)

        # ASSERT
        y = res_instance.get_output()

        self.assertAlmostEqual(y["bottomhole_pressure"], 280, delta=0.01)
