"""Unit tests for the AbsorptionChiller model.

Reference case: 20 degC chilled-water supply (challenge cooling supply
temperature), 26 degC return, 30 degC cooling water, geothermal brine at
85 degC driving the generator.
"""

import unittest

from gemini_model.chiller.absorption_chiller import AbsorptionChiller


class TestAbsorptionChiller(unittest.TestCase):
    """Tests for AbsorptionChiller."""

    def setUp(self):
        """Build a 5 MW chiller."""
        self.chiller = AbsorptionChiller()
        self.chiller.update_parameters({"capacity_nominal": 5e6})

    def test_cop_reversible_fraction_capped(self):
        """COP follows eta_rev * COP_rev but never exceeds cop_max."""
        tg, tc, te = 85 + 273.15, 30 + 273.15, 20 + 273.15
        cop_rev = (1 - tc / tg) * te / (tc - te)
        self.assertAlmostEqual(self.chiller.cop(85, 30), min(0.8, 0.2 * cop_rev))
        self.chiller.update_parameters({"eta_rev": 0.05})
        self.assertAlmostEqual(self.chiller.cop(85, 30), 0.05 * cop_rev)

    def test_energy_balance_and_temperatures(self):
        """Heat rejected = heat in + cooling, and stream temperatures follow."""
        chw_flow = 4e6 / (1000 * 4186 * 6)  # 4 MW at 26 -> 20 degC
        u = {
            "hot_temperature_in": 85.0,
            "hot_flow_rate": 300 / 3600,
            "chilled_temperature_in": 26.0,
            "chilled_flow_rate": chw_flow,
            "cooling_water_temperature": 30.0,
        }
        self.chiller.calculate_output(u)
        out = self.chiller.output
        self.assertAlmostEqual(out["cooling_power"], 4e6, places=3)
        self.assertAlmostEqual(out["chilled_temperature_out"], 20.0, places=6)
        self.assertAlmostEqual(out["heat_consumed"], out["cooling_power"] / out["COP"])
        self.assertAlmostEqual(
            out["heat_rejected"], out["heat_consumed"] + out["cooling_power"], places=6
        )
        dt_hot = out["heat_consumed"] / (300 / 3600 * 1030 * 4180)
        self.assertAlmostEqual(out["hot_temperature_out"], 85.0 - dt_hot)
        self.assertEqual(out["unmet_cooling"], 0.0)

    def test_capacity_limit_and_cold_generator(self):
        """Capacity caps cooling; below the minimum firing temperature nothing is produced."""
        u = {
            "hot_temperature_in": 85.0,
            "hot_flow_rate": 600 / 3600,
            "chilled_temperature_in": 26.0,
            "chilled_flow_rate": 1.0,
            "cooling_water_temperature": 30.0,
        }
        self.chiller.calculate_output(u)
        self.assertAlmostEqual(self.chiller.output["cooling_power"], 5e6)
        self.assertGreater(self.chiller.output["unmet_cooling"], 0.0)

        u["hot_temperature_in"] = 60.0
        self.chiller.calculate_output(u)
        self.assertEqual(self.chiller.output["cooling_power"], 0.0)
        self.assertEqual(self.chiller.output["hot_temperature_out"], 60.0)

    def test_hot_water_limit(self):
        """With little driving flow, cooling is capped by the max hot-water temperature drop."""
        u = {
            "hot_temperature_in": 85.0,
            "hot_flow_rate": 50 / 3600,
            "chilled_temperature_in": 26.0,
            "chilled_flow_rate": 1.0,
            "cooling_water_temperature": 30.0,
        }
        self.chiller.calculate_output(u)
        out = self.chiller.output
        self.assertAlmostEqual(out["hot_temperature_out"], 85.0 - 15.0)
        self.assertLess(out["cooling_power"], 5e6)


if __name__ == "__main__":
    unittest.main()
