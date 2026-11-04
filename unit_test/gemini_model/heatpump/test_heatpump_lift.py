"""Unit tests for the HeatPumpLift model (brine-floor heat pump lifting district water to 100 C)."""

import unittest

from gemini_model.heatpump.heatpump_basic import HeatpumpBasic
from gemini_model.heatpump.heatpump_lift import HeatPumpLift

# brine leaving a 3 K-approach exchanger at a 60 C network return; wellhead 85.6 C and a 40 K cap
# give the 45.6 C floor
CASE = {
    "T_brine_in_C": 63.0,
    "brine_flow_m3h": 300.0,
    "T_brine_floor_C": 45.6,
    "T_water_in_C": 82.6,
    "water_flow_m3h": 360.0,
}

K = 273.15  # C to K


def _run(u):
    hp = HeatPumpLift()
    hp.calculate_output(u)
    return hp.get_output()


class TestHeatPumpLift(unittest.TestCase):
    """Energy balance, COP and the floor branch."""

    def test_energy_balance_and_cop(self):
        """Sink duty = source duty + electricity; COP = Q_th / P_el; water reaches 100 C."""
        y = _run(CASE)
        self.assertAlmostEqual(
            y["Q_th_MW"], y["Q_brine_MW"] + y["P_el_MW"], delta=1e-3 * y["Q_th_MW"]
        )
        self.assertAlmostEqual(y["COP"], y["Q_th_MW"] / y["P_el_MW"], delta=1e-9)
        self.assertTrue(2.0 < y["COP"] < 8.0)
        self.assertFalse(y["floor_binds"])
        self.assertAlmostEqual(y["T_water_out_C"], 100.0, delta=1e-6)

    def test_floor_binds_at_double_duty(self):
        """Twice the water flow: the floor binds, water leaves below 100 C but above its inlet."""
        u = {**CASE, "water_flow_m3h": 2 * CASE["water_flow_m3h"]}
        y = _run(u)
        self.assertTrue(y["floor_binds"])
        self.assertAlmostEqual(y["T_brine_out_C"], CASE["T_brine_floor_C"], delta=1e-6)
        self.assertAlmostEqual(y["T_water_out_C"], 91.74, delta=0.1)
        self.assertAlmostEqual(
            y["Q_th_MW"], y["Q_brine_MW"] + y["P_el_MW"], delta=1e-3 * y["Q_th_MW"]
        )

    def test_brine_at_floor_gives_nothing(self):
        """Brine entering at the floor: no heat, no electricity, the water passes through."""
        y = _run({**CASE, "T_brine_in_C": CASE["T_brine_floor_C"]})
        self.assertEqual((y["Q_th_MW"], y["P_el_MW"]), (0.0, 0.0))
        self.assertAlmostEqual(y["Q_brine_MW"], 0.0, delta=1e-9)
        self.assertTrue(y["floor_binds"])
        self.assertAlmostEqual(y["T_water_out_C"], CASE["T_water_in_C"], delta=1e-9)

    def test_heatpump_basic_keys(self):
        """Same outputs through HeatpumpBasic keys with the floor as a parameter."""
        hp = HeatPumpLift()
        hp.update_parameters({"Ts_in_minimum": CASE["T_brine_floor_C"]})
        hp.calculate_output(
            {
                "Ts_in": CASE["T_brine_in_C"],
                "Th_in": CASE["T_water_in_C"],
                "source_flow_rate": CASE["brine_flow_m3h"] / 3600.0,
                "hot_flow_rate": CASE["water_flow_m3h"] / 3600.0,
                "source_pressure_in": 9.5,
            }
        )
        y, ref = hp.get_output(), _run(CASE)
        for key in ("Q_th_MW", "COP", "Ts_out"):
            self.assertAlmostEqual(y[key], ref[key], delta=1e-9 * abs(ref[key]), msg=key)
        self.assertEqual(y["source_pressure_out"], 9.5)

    def test_cop_cap(self):
        """A 5 K lift on 80 C brine: Lorenz COP above 8 uncapped, 8 capped, duty held, balance."""
        u = {
            "T_brine_in_C": 80.0,
            "brine_flow_m3h": 300.0,
            "T_brine_floor_C": 45.0,
            "T_water_in_C": 95.0,
            "water_flow_m3h": 360.0,
        }
        hp = HeatPumpLift()
        hp.parameters["cop_max"] = 1e9
        hp.calculate_output(u)
        self.assertGreater(hp.get_output()["COP"], 8.0)
        y = _run(u)
        self.assertEqual(y["COP"], 8.0)
        self.assertAlmostEqual(y["Q_th_MW"], 2.0, delta=1e-9)
        self.assertAlmostEqual(y["P_el_MW"], 0.25, delta=1e-9)
        self.assertAlmostEqual(y["Q_brine_MW"] + y["P_el_MW"], y["Q_th_MW"], delta=1e-9)

    def test_at_target_balance(self):
        """_at_target on CASE: water at 100 C, brine out 46.78 C, COP 5.004, balance closes."""
        hp = HeatPumpLift()
        p = hp.parameters
        mh = CASE["water_flow_m3h"] / 3600.0 * p["rho_h"]
        ms = CASE["brine_flow_m3h"] / 3600.0 * p["rho_s"]
        ts_in, ts_floor = CASE["T_brine_in_C"] + K, CASE["T_brine_floor_C"] + K
        cop, th_out, ts_out, q_h, _ = hp._at_target(
            100.0 + K, CASE["T_water_in_C"] + K, ts_in, ts_floor, mh, ms
        )
        print(f"  _at_target: COP {cop:.4f}, brine out {ts_out - K:.4f} C, {q_h / 1e6:.3f} MW")
        self.assertAlmostEqual(th_out, 100.0 + K, delta=1e-9)
        self.assertTrue(ts_floor < ts_out < ts_in)
        brine = p["Cp_s"] * ms * (ts_in - ts_out)
        self.assertAlmostEqual(brine, q_h * (cop - 1) / cop, delta=1e-6 * brine)

    def test_heatpump_basic_floor_branch_root(self):
        """Same inputs through HeatpumpBasic: its floor branch gives an outlet far above target."""
        u = {**CASE, "water_flow_m3h": 2 * CASE["water_flow_m3h"]}
        hp = HeatpumpBasic()
        hp.update_parameters(
            {
                "mode": "lorenz",
                "eta_lorenz": 0.5,
                "Th_out_target": 100.0,
                "Ts_in_minimum": u["T_brine_floor_C"],
                "rho_s": 1030.0,
                "Cp_s": 4000.0,
            }
        )
        hp.calculate_output(
            {
                "Th_in": u["T_water_in_C"],
                "Ts_in": u["T_brine_in_C"],
                "hot_flow_rate": u["water_flow_m3h"] / 3600,
                "source_flow_rate": u["brine_flow_m3h"] / 3600,
            }
        )
        self.assertGreater(hp.get_output()["Th_out"], 100.0)  # about 796 C, unphysical


if __name__ == "__main__":
    unittest.main()
