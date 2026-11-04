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
