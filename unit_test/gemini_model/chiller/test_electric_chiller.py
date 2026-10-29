"""Unit tests for the ElectricChiller model."""

import unittest

from gemini_model.chiller.electric_chiller import ElectricChiller


class TestElectricChiller(unittest.TestCase):
    """Tests for ElectricChiller."""

    def test_cop_and_power(self):
        """Electric power equals cooling / COP with a Carnot-fraction COP."""
        chiller = ElectricChiller()
        chiller.update_parameters({"cop_max": 20.0})
        te, tc = 20 + 273.15, 30 + 5 + 273.15
        expected_cop = 0.5 * te / (tc - te)
        chw_flow = 2e6 / (1000 * 4186 * 6)
        chiller.calculate_output(
            {
                "chilled_temperature_in": 26.0,
                "chilled_flow_rate": chw_flow,
                "cooling_water_temperature": 30.0,
            }
        )
        out = chiller.output
        self.assertAlmostEqual(out["COP"], expected_cop)
        self.assertAlmostEqual(out["cooling_power"], 2e6, places=3)
        self.assertAlmostEqual(out["power_el"], 2e6 / expected_cop, places=3)
        self.assertAlmostEqual(out["heat_rejected"], out["cooling_power"] + out["power_el"])

    def test_cop_cap(self):
        """COP is capped at cop_max."""
        chiller = ElectricChiller()
        self.assertEqual(chiller.cop(10.0), 7.0)


if __name__ == "__main__":
    unittest.main()
