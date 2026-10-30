"""Unit tests for the ElectricChiller model.

Reference case: 20 degC chilled-water supply (challenge cooling supply
temperature), 26 degC return, 30 degC cooling water.
"""

import unittest

from gemini_model.chiller.electric_chiller import ElectricChiller


def _u(cooling_w):
    return {
        "chilled_temperature_in": 26.0,
        "chilled_flow_rate": cooling_w / (1000 * 4186 * 6),
        "cooling_water_temperature": 30.0,
    }


class TestElectricChiller(unittest.TestCase):
    """Tests for ElectricChiller."""

    def setUp(self):
        """Build a 10 MW chiller with default (realistic) parameters."""
        self.chiller = ElectricChiller()
        self.chiller.update_parameters({"capacity_nominal": 10e6})

    def test_full_load_cop_uses_refrigerant_temperatures(self):
        """Te = 20 - 4 degC, Tc = 30 + 8 degC, COP = 0.4 * Te / (Tc - Te)."""
        te, tc = 16 + 273.15, 38 + 273.15
        self.assertAlmostEqual(self.chiller.cop(30.0), 0.4 * te / (tc - te))
        self.assertLess(self.chiller.cop(30.0), self.chiller.parameters["cop_max"])

    def test_system_cop_is_realistic_at_full_load(self):
        """With fans and pumps the system COP of a 20 degC chiller sits around 4.5-5.5."""
        self.chiller.calculate_output(_u(10e6))
        out = self.chiller.output
        self.assertAlmostEqual(out["cooling_power"], 10e6, places=2)
        self.assertAlmostEqual(out["part_load_ratio"], 1.0)
        self.assertTrue(4.5 < out["COP"] < 5.5, out["COP"])
        compressor_power = out["cooling_power"] / out["compressor_cop"]
        self.assertAlmostEqual(out["heat_rejected"], out["cooling_power"] + compressor_power)

    def test_part_load_curve(self):
        """Part-load power is 1 at full load, best near mid load, worst when cycling."""
        self.assertAlmostEqual(self.chiller.part_load_power_fraction(1.0), 1.0, places=3)
        cops = {}
        for plr in (0.05, 0.5, 1.0):
            self.chiller.calculate_output(_u(plr * 10e6))
            cops[plr] = self.chiller.output["compressor_cop"]
        self.assertGreater(cops[0.5], cops[1.0])
        self.assertLess(cops[0.05], cops[1.0])

    def test_staging_keeps_low_load_efficient(self):
        """Three staged units run one module at 10% total load instead of one big unit at 10%."""
        self.chiller.calculate_output(_u(1e6))
        single = self.chiller.output["COP"]
        self.chiller.update_parameters({"units": 3})
        self.chiller.calculate_output(_u(1e6))
        out = self.chiller.output
        self.assertEqual(out["units_on"], 1)
        self.assertAlmostEqual(out["part_load_ratio"], 0.3)
        self.assertGreater(out["COP"], single)
        self.chiller.calculate_output(_u(10e6))
        self.assertEqual(self.chiller.output["units_on"], 3)

    def test_capacity_limit_and_zero_load(self):
        """Above capacity the rest is unmet; no load means no power."""
        self.chiller.calculate_output(_u(12e6))
        self.assertAlmostEqual(self.chiller.output["unmet_cooling"], 2e6, places=2)
        self.chiller.calculate_output(_u(0.0))
        self.assertEqual(self.chiller.output["power_el"], 0.0)

    def test_cop_cap(self):
        """COP is capped at cop_max for very warm chilled water / cold sinks."""
        self.assertEqual(self.chiller.cop(-30.0), 7.0)


if __name__ == "__main__":
    unittest.main()
