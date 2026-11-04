"""Unit tests: gas rates, well cost and doublet lifetime against hand calculations, and the plant table against frozen values."""
import unittest
from pathlib import Path

import numpy as np

from geo import cost, gas, gemini_project, lifetime, optimise, rule
from geo.plant import APPROACH_K, T_ABS_MIN_C, DoubletTable
from geo.well import Producer
from geo.year import COP_ABSORPTION

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

    def test_optimiser_challenge_brief(self):
        """Optimiser on the challenge brief: a feasible 2-doublet row on the front, best LCoH within 5 EUR/MWh below the 60 C
        sweep value of 63.97 (the lowest feasible return is 57.5 C, one 2.5 C pattern step below 60 C), every front row feasible."""
        r = optimise.optimise()
        self.assertTrue(any(p["n"] == 2 for p in r["front"]))
        self.assertTrue(all(p["feasible"] and not p["fails"] for p in r["front"]))
        self.assertLess(abs(r["best_lcoh"]["lcoh_EUR_MWh"] - 63.97), 5.0)
        self.assertLess(r["best_lcoh"]["lcoh_EUR_MWh"], 63.97)
        self.assertTrue(56.25 < r["best_lcoh"]["t_return_c"] <= 57.5)   # 56.25 C needs boiler lift, 57.5 C is the 1.25 C sweep point
        self.assertLessEqual(r["n_evaluated"], 400)

    def test_rule_shared(self):
        """The doublet rule: boiler above 5 % of the heat served fails, a row with nothing unmet and a covered peak passes."""
        self.assertEqual(rule.rule_failures({"unmet_GWh": 0.0, "boiler_GWh": 1.0, "served_GWh": 100.0, "peak_margin_pct": 2.0}), [])
        self.assertEqual([f[0] for f in rule.rule_failures({"unmet_GWh": 0.0, "boiler_GWh": 6.0, "served_GWh": 100.0,
                                                            "boiler_share_pct": 6.0})], ["boiler share"])

    def test_plant_table_unchanged(self):
        """Plant table first and last rows equal the frozen values."""
        t = DoubletTable(60.0, depth_m=2500.0)
        for k, (first, last) in BEFORE.items():
            np.testing.assert_allclose([t.cols[k][0], t.cols[k][-1]], [first, last], rtol=1e-6, err_msg=k)

    def test_gemini_project_dict(self):
        """The generated GEMINI project has the example's component types plus our four models, our ESP depth and one station
        per 50 m."""
        w = Producer(stages=24)
        day = {"freq_hz": 58.0, "T_wellhead_C": 85.0, "secondary_m3s": 0.1, "ua_w_per_k": 5e5, "ii_m3h_bar": 6.0,
               "T_chiller_floor_C": 85.0, "T_hp_floor_C": 45.0}
        p = gemini_project.project_dict(w, 60.0, day, n=2)
        self.assertEqual([c["type"] for c in p["components"].values()],
                         ["producer_well", "separator", "filter", "absorption_chiller", "heat_exchanger", "heatpump_lift",
                          "filter", "boiler", "injector_well", "henry_gas", "thermal_breakthrough"])
        self.assertEqual(p["components"]["producer_well"]["parameters"]["esp_depth_m"], 1100.0)
        self.assertEqual(len(p["components"]["producer_well"]["parameters"]["trajectory_table"]), 51)

    def test_gemini_replay_coldest_day(self):
        """GEMINI's solver on the coldest day (full draw, 2 doublets at 57.5 C return): same flow, exchanger duty equal, ESP head
        within 1 bar after the 7.4 bar water-column offset (what is left is the friction of water at 1 mPa s against our 0.4 mPa s
        brine), project file written. Our models inside GEMINI's chain: heat-pump duty within 1 % and COP within 2 % of the plant
        (printed 6.436 MW, COP 4.8109 vs 4.8108), bubble point within 0.05 bar (45.57 bar), breakthrough within 0.5 % (65.2 years),
        no absorption drive (the exchanger needs all the brine above 78 C)."""
        days = gemini_project._days(2, 57.5, 2500.0, 1100.0).iloc[[0]]
        r = gemini_project.replay(2, 57.5, days=days)
        d = r["days"][0]
        self.assertAlmostEqual(d["q_m3h_diff_pct"], 0.0, delta=0.01)
        self.assertAlmostEqual(d["MW_exchanger_diff_pct"], 0.0, delta=0.1)
        self.assertAlmostEqual(d["water_column_offset_bar"], 7.36, delta=0.01)
        self.assertLess(abs(d["esp_head_residual_bar"]), 1.0)
        self.assertTrue(Path(r["project_path"]).exists())
        self.assertLess(abs(d["MW_heat_pump_diff_pct"]), 1.0)
        self.assertLess(abs(d["cop_heat_pump_diff_pct"]), 2.0)
        self.assertAlmostEqual(d["p_bubble_bar_gemini"], d["p_bubble_bar_ours"], delta=0.05)
        self.assertLess(abs(d["t_breakthrough_yr_diff_pct"]), 0.5)
        self.assertEqual(d["MW_abs_drive_ours"], 0.0)
        self.assertLess(d["MW_abs_drive_gemini"], 1e-6)

    def test_gemini_replay_at_the_brief_peak(self):
        """A 45 MW brief (brief D, 3 doublets at 56.5 C): the replayed coldest day carries 45 MW, not the 30 MW of the file,
        GEMINI solves it (ESP head residual present) and the project file name carries the peak."""
        days = gemini_project._days(3, 56.5, peak_heat_MW=45)
        self.assertAlmostEqual(float(days.demand.iloc[0]), 45.0, delta=1e-6)
        import tempfile
        runs, gemini_project.RUNS = gemini_project.RUNS, Path(tempfile.mkdtemp())   # the project file goes to a scratch folder
        try:
            r = gemini_project.replay(3, 56.5, days=days.iloc[[0]], peak_heat_MW=45)
        finally:
            gemini_project.RUNS = runs
        self.assertIn("esp_head_residual_bar", r["days"][0])
        self.assertTrue(r["project_path"].endswith("gemini_project_3d_56.5C_45MW.json"))

    def test_gemini_replay_mildest_day(self):
        """GEMINI's solver on the mildest day with both doublets on (19 Sep, 57.5 C return): flow at the 160 m3/h floor, chiller-first
        part load, so the brine above 78 C drives the absorption chiller, the exchanger heats the water to 75 C and the heat pump
        lifts it to 100 C. GEMINI's chiller drive equals ours within 0.1 % and is above zero (printed 1.1685 MW), its cold is
        COP_ABSORPTION x drive, its heat pump within 2 % of ours (printed 1.6871 MW both, COP 9.05) and its supply within 0.5 C of
        100 C (printed 100.0 C)."""
        days = gemini_project._days(2, 57.5, 2500.0, 1100.0).iloc[[-1]]
        d = gemini_project.replay(2, 57.5, days=days)["days"][0]
        self.assertGreater(d["MW_abs_drive_gemini"], 0.0)
        self.assertLess(abs(d["MW_abs_drive_diff_pct"]), 0.1)
        self.assertAlmostEqual(d["MW_abs_cold_gemini"], COP_ABSORPTION * d["MW_abs_drive_gemini"], delta=1e-9)
        self.assertGreater(d["MW_heat_pump_ours"], 0.0)
        self.assertLess(abs(d["MW_heat_pump_diff_pct"]), 0.5)
        self.assertAlmostEqual(d["T_supply_C_gemini"], 100.0, delta=0.5)

    def test_part_load_chiller_first(self):
        """Part load at 56.5 C return, 2 500 m, 2.68 MW per doublet (flow at the 160 m3/h floor, mcp 0.183 MW/K, wellhead 84.4 C):
        chiller-first, the chiller takes mcp x (84.4 - 78) = 1.169 MW, exchanger plus heat pump deliver the 2.68 MW (printed
        1.140 + 1.540), electricity 0.165 MW at COP 9.3, the evaporator leaves the brine above the 40 K floor."""
        t = DoubletTable(56.5, depth_m=2500.0)
        pt = t.at_output(2.68)
        floor = {k: float(v[0]) for k, v in t.cols.items()}
        self.assertEqual(pt["part_load"], "chiller-first")
        self.assertAlmostEqual(pt["MW_hx"] + pt["MW_hp"], 2.68, places=9)
        self.assertGreater(pt["MW_el_hp"], 0.0)
        self.assertAlmostEqual(pt["MW_abs_drive"], floor["mcp_MW_per_K"] * (floor["T_wh_C"] - T_ABS_MIN_C), places=9)
        self.assertAlmostEqual(pt["t_hx_C"], T_ABS_MIN_C - APPROACH_K, places=9)
        self.assertGreaterEqual(pt["MW_brine_left"], 0.0)   # evaporator outlet above the 40 K brine floor
        self.assertEqual(pt["MW_boiler_lift"], 0.0)

    def test_part_load_exchanger_first_near_floor(self):
        """Near the floor output (8.0 MW of 8.07 at 56.5 C) chiller-first would cool the brine below the return plus approach, so the
        floor point's split is held: exchanger and heat pump scale together, the COP rises with the smaller lift (so the
        electricity falls below the scaled value), no chiller drive, water out below the brine."""
        t = DoubletTable(56.5, depth_m=2500.0)
        floor = {k: float(v[0]) for k, v in t.cols.items()}
        pt = t.at_output(8.0)
        f = 8.0 / floor["MW_out"]
        self.assertEqual(pt["part_load"], "exchanger-first")
        for k in ("MW_hx", "MW_hp"):
            self.assertAlmostEqual(pt[k], f * floor[k], places=9, msg=k)
        self.assertGreater(pt["cop"], floor["cop"])
        self.assertLess(pt["MW_el_hp"], f * floor["MW_el_hp"])
        self.assertAlmostEqual(pt["MW_el_hp"], pt["MW_hp"] / pt["cop"], places=9)
        self.assertEqual(pt["MW_abs_drive"], 0.0)
        self.assertLessEqual(pt["t_hx_C"], floor["T_wh_C"] - APPROACH_K + 1e-9)
        self.assertEqual(t.at_output(9.0)["part_load"], "full")


if __name__ == "__main__":
    unittest.main()
