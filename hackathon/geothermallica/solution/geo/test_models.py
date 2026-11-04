"""Unit tests: gas rates, well cost and doublet lifetime against hand calculations, and the plant table against frozen values."""
import unittest

import numpy as np

from geo import cost, gas, lifetime
from geo.plant import DoubletTable

# DoubletTable at 60 C return, 2 500 m, heat-pump layout: first and last row, frozen on 3 Nov 2026 as a regression reference
BEFORE = {"MW_out": [8.165720210178794, 15.206432108241914], "kW_esp": [188.36576949356862, 596.8526578341806],
          "cop": [5.052470940492809, 5.05996544563592]}


class TestModels(unittest.TestCase):
    """Hand-checked values for gas, cost, lifetime and the plant table."""

    def test_gas_rates(self):
        """Gas rates at 300 m3/h: 0.8 Nm3/m3 split 80/20, methane power and CO2 mass."""
        g = gas.gas_at(300.0)
        for k, v, tol in (("gas_Nm3h", 240, 1e-9), ("CH4_Nm3h", 192, 1e-9), ("CO2_Nm3h", 48, 1e-9), ("CH4_MW_LHV", 1.91, 0.005),
                          ("CO2_in_gas_kg_h", 94, 0.5)):
            self.assertAlmostEqual(g[k], v, delta=tol, msg=k)

    def test_gas_handling(self):
        """Gas handling at 300 m3/h: 94 kg/h CO2 in the gas, 377 kg/h from burning the CH4, engine electricity 0.64 MW."""
        hours = gas.OPERATING_DAYS * 24
        opts = {o["option"]: o for o in gas.handling_options(300.0)}
        self.assertAlmostEqual(opts["vent"]["CO2_t_per_yr"] * 1000 / hours, 94, delta=0.5)
        self.assertAlmostEqual((opts["flare"]["CO2_t_per_yr"] - opts["vent"]["CO2_t_per_yr"]) * 1000 / hours, 377, delta=0.5)
        self.assertAlmostEqual(opts["engine"]["electricity_MWh_per_yr"] / hours, 0.64, delta=0.005)
        self.assertEqual(opts["engine"]["CO2_t_per_yr"], opts["flare"]["CO2_t_per_yr"])
        self.assertEqual(opts["reinject"]["CO2_t_per_yr"], 0.0)
        self.assertGreater(opts["vent"]["CO2e_t_per_yr"], opts["flare"]["CO2e_t_per_yr"])

    def test_co2_electricity(self):
        """Electricity CO2 equals electricity GWh x 0.3 kg/kWh, and the total adds the three lines."""
        e = cost.economics(2, 60.0, 30.0, 10.0)
        self.assertAlmostEqual(e["co2_electricity_kt"], e["electricity_GWh"] * 0.3, places=9)
        self.assertAlmostEqual(e["co2_total_kt"], e["co2_kt"] + e["co2_electricity_kt"] + e["co2_associated_gas_kt"], places=9)

    def test_bubble_point_tens_of_bar(self):
        """Bubble point between 10 and 100 bar, van 't Hoff above the fits."""
        self.assertTrue(10 < gas.p_bubble_bar(2500.0) < gas.p_bubble_bar(2500.0, "vant_hoff") < 100)

    def test_doublet_cost(self):
        """ThermoGIS doublet cost at 2 500 m is about 9.33 MEUR."""
        self.assertAlmostEqual(cost.doublet_meur(2500.0), 9.33, delta=0.05)

    def test_breakthrough(self):
        """Breakthrough at 300 m3/h: 30 years at 1 020 m spacing, 65 years at 1 500 m."""
        self.assertAlmostEqual(lifetime.t_bt_yr(300.0, 1020.0), 30.0, delta=1.0)
        self.assertAlmostEqual(lifetime.t_bt_yr(300.0, 1500.0), 65.0, delta=1.0)

    def test_interference(self):
        """No interference for one doublet; 0.93 bar for two at 300 m3/h."""
        self.assertEqual(lifetime.interference_bar(1, 300.0), [0])
        self.assertAlmostEqual(lifetime.interference_bar(2, 300.0)[0], 0.93, delta=0.01)   # 2.69 bar x ln(sqrt 2), checked by hand

    def test_plant_table_unchanged(self):
        """Plant table first and last rows equal the frozen values."""
        t = DoubletTable(60.0, depth_m=2500.0)
        for k, (first, last) in BEFORE.items():
            np.testing.assert_allclose([t.cols[k][0], t.cols[k][-1]], [first, last], rtol=1e-6, err_msg=k)


if __name__ == "__main__":
    unittest.main()
