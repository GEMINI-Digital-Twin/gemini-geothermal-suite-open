"""Tests of the GEMINI contributions against GEMINI's own models and the geo package.

Run: python -m unittest geo.gemini_contrib.test_contrib -v
"""
import sys
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import geo.gemini_contrib  # noqa: F401  (puts the GEMINI tree on the path before geo.well)
from geo.gemini_contrib.esp_affinity import ESPAffinity
from geo.gemini_contrib.heatpump_lift import HeatPumpLift, register
from geo.gemini_contrib import injector_sign as fixed
from geo.gemini_contrib.henry_gas import HenryGasBubblePoint
from geo.gemini_contrib.thermal_breakthrough import YEAR, DoubletThermalBreakthrough

from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.heatpump.heatpump_basic import HeatpumpBasic
from gemini_model.pump.esp import ESP
from gemini_model.well.pressure_drop import DPDT
from gemini_simulator import nodal_solver
from gemini_simulator.well_flow import _build_dpdt
import numpy as np

from geo import gas, lifetime, plant
from geo.common import MU_PA_S, PERM_MD, RHO, THICKNESS_M, t_reservoir_c
from geo.well import ROUGHNESS_M, TUBING_ID_M, Producer, _pump

BAR = 1e5
ESP_PARAMS = {  # pump HC27000 from GEMINI unit_test/gemini_model/pump/test_esp.py
    "no_stages": 12,
    "head_coeff": [83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21],
    "power_coeff": [10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23],
}
Q_REF = 200 / 3600  # reference flow, m3/s, as in test_esp.py


def esp_out(model_class, params, freq, flow):
    """Output of a pump model at freq (Hz) and flow (m3/s)."""
    m = model_class()
    m.update_parameters(dict(params))
    m.calculate_output({"pump_freq": freq, "pump_flow": flow})
    return m.get_output()


class TestESPAffinity(unittest.TestCase):
    """Similarity-law pump against GEMINI's ESP."""

    def test_equals_gemini_at_60_hz(self):
        """Same head, power and efficiency as GEMINI's ESP at 60 Hz."""
        a, g = esp_out(ESPAffinity, ESP_PARAMS, 60, Q_REF), esp_out(ESP, ESP_PARAMS, 60, Q_REF)
        for k in ("pump_head", "pump_power", "pump_eff"):
            self.assertAlmostEqual(a[k], g[k], delta=1e-9)

    def test_homologous_point_48_hz(self):
        """At 48 Hz and 0.8 q: head x 0.64, power x 0.512, same efficiency."""
        ref = esp_out(ESPAffinity, ESP_PARAMS, 60, Q_REF)
        y = esp_out(ESPAffinity, ESP_PARAMS, 48, 0.8 * Q_REF)
        self.assertAlmostEqual(y["pump_head"], 0.64 * ref["pump_head"], delta=1e-6)
        self.assertAlmostEqual(y["pump_power"], 0.512 * ref["pump_power"], delta=1e-6)
        self.assertAlmostEqual(y["pump_eff"], ref["pump_eff"], delta=1e-9)

    def test_zero_frequency_rejected(self):
        """0 Hz raises ValueError."""
        with self.assertRaises(ValueError):
            esp_out(ESPAffinity, ESP_PARAMS, 0, Q_REF)

    def test_gemini_discrepancy_on_our_pump(self):
        """Below 60 Hz GEMINI's ESP gives more head than the similarity law."""
        params = _pump(24).parameters
        rows = []
        for q, f in ((230, 58.0), (250, 47.353), (300, 56.879), (230, 50.0)):
            g = esp_out(ESP, params, f, q / 3600)["pump_head"] / BAR
            a = esp_out(ESPAffinity, params, f, q / 3600)["pump_head"] / BAR
            rows.append((q, f, g, a, 100 * (g - a) / a))
            print(f"  {q} m3/h {f:.2f} Hz: head GEMINI {g:.2f} bar, affinity {a:.2f} bar")
        self.assertGreater(rows[0][4], 2.0)
        self.assertGreater(rows[3][4], 10.0)

    def test_producer_uses_same_law(self):
        """The producer well model uses the same similarity law as ESPAffinity."""
        w = Producer(stages=24)
        f = w.freq_for_wellhead(300.0, 10.0)
        head = w.run(300.0, f)["esp_head_bar"]
        a = esp_out(ESPAffinity, _pump(24).parameters, f, 300.0 / 3600)["pump_head"] / BAR
        self.assertAlmostEqual(head / a, 1.0, delta=1e-6)


def vertical_well():
    """GEMINI pipe-flow model (DPDT) of a 2 500 m vertical well in 100 m cells."""
    seg = [{"angle": 90.0, "depth": 100.0, "diameter": TUBING_ID_M}] * 25
    return _build_dpdt(seg, roughness=ROUGHNESS_M)


class TestInjectorSign(unittest.TestCase):
    """Friction sign in the injector pressure solve."""

    def test_gemini_own_convention(self):
        """Replica of GEMINI's own test: negative flow going down gives a negative friction drop."""
        w = DPDT()
        w.update_parameters({
            "diameter": np.array([6.366, 6.366, 9.95, 6.366, 3.92]) * 0.0254,
            "length": np.array([0, 148, 949, 1012, 218]),
            "angle": np.array([90, 90, 69.0, 44.4, 40.3]) * np.pi / 180,
            "roughness": np.array([0.0003] * 5),
            "friction_correlation": "darcy_weisbach", "friction_correlation_2p": "BeggsBrill",
            "correction_factors": [1, 0]})
        w.PVT = PVTConstantSTP()
        w.calculate_output({"flowrate": -10 / 3600, "temperature": 61.5 + 273.15, "pressure": 1e5,
                            "direction": "down", "temperature_ambient": 20 + 273.15}, None)
        self.assertAlmostEqual(w.get_output()["pressuredrop_fric_output"], -6264.02, delta=0.01)

    def test_friction_subtracts_with_fix(self):
        """With the fix the bottomhole pressure is below hydrostatic."""
        q, p_wh, t_wh = 300 / 3600, 1 * BAR, 50 + 273.15
        d = vertical_well()
        p_fix = fixed._well_bottomhole_pressure_injection(d, q, p_wh, t_wh)
        p_hyd = p_wh + d.get_output()["pressuredrop_grav_output"]
        p_gem = nodal_solver._well_bottomhole_pressure_injection(d, q, p_wh, t_wh)
        patched = abs(p_gem - p_fix) < 1.0  # the GEMINI tree on the path carries the fix
        print(f"  p_bh fixed {p_fix / BAR:.2f} bar, hydrostatic {p_hyd / BAR:.2f} bar, "
              f"GEMINI {p_gem / BAR:.2f} bar{' (patched tree)' if patched else ''}")
        self.assertLess(p_fix, p_hyd)
        if patched:
            self.assertAlmostEqual(p_gem, p_fix, delta=0.01 * BAR)
        else:
            self.assertGreater(p_gem, p_hyd)

    def test_wellhead_solver_drop_in(self):
        """Wellhead pressure 47.25 bar for 300 m3/h into 250 bar at 10 m3/h/bar."""
        cfg = {"reservoir_pressure_bar": 250.0, "productivity_index_m3h_per_bar": 10.0,
               "roughness_m": ROUGHNESS_M,
               "welltrajectory": [{"angle": 90.0, "depth": 100.0, "diameter": TUBING_ID_M}] * 25}
        from gemini_simulator.well_flow import solve_injector_wellhead_pressure_bar as gemini_solve
        p_fix = fixed.solve_injector_wellhead_pressure_bar(cfg, 300.0, 50.0)
        p_gem = gemini_solve(cfg, 300.0, 50.0)
        print(f"  injector wellhead: fixed {p_fix:.2f} bar, GEMINI {p_gem:.2f} bar")
        self.assertAlmostEqual(p_fix, 47.25, delta=0.05)
        if abs(p_gem - p_fix) > 1e-6:  # unpatched tree: the reversed sign gives 22.25 bar
            self.assertAlmostEqual(p_gem, 22.25, delta=0.05)


def balanced_case(duty_fraction=0.98):
    """Build the HeatPumpLift inputs and the plant result at 300 m3/h and 60 C return."""
    r = plant.doublet_at(Producer(stages=24), 300.0, 60.0)
    t_wh = r["T_wh_C"]
    t_brine_in = 60.0 + plant.APPROACH_K
    t_floor, t_water_in = t_wh - plant.DT_BRINE_MAX_K, t_wh - plant.APPROACH_K
    q_water = duty_fraction * r["MW_hp"] * 1e6 / (1000.0 * plant.CP * 1000 * (100.0 - t_water_in))
    u = {"T_brine_in_C": t_brine_in, "brine_flow_m3h": 300.0, "T_brine_floor_C": t_floor,
         "T_water_in_C": t_water_in, "water_flow_m3h": q_water * 3600}
    return u, r


def run_hp(u):
    """Output of HeatPumpLift for inputs u."""
    hp = HeatPumpLift()
    hp.calculate_output(u)
    return hp.get_output()


class TestHeatPumpLift(unittest.TestCase):
    """Energy balance, floor branch and registry of HeatPumpLift."""

    def test_constants_match_plant(self):
        """Heat capacity, brine density and Lorenz efficiency match the plant model."""
        hp = HeatPumpLift()
        self.assertEqual(hp.parameters["Cp_s"], plant.CP * 1000)
        self.assertEqual(hp.parameters["rho_s"], plant.RHO)
        self.assertEqual(hp.parameters["eta_lorenz"], plant.LORENZ_EFF)

    def test_energy_balance_and_cop(self):
        """Heat out = brine heat + electricity, COP consistent, water reaches 100 C."""
        u, _ = balanced_case()
        y = run_hp(u)
        print(f"  brine {u['T_brine_in_C']:.1f}->{y['T_brine_out_C']:.2f} C, "
              f"water {u['T_water_in_C']:.2f}->{y['T_water_out_C']:.2f} C, COP {y['COP']:.3f}")
        self.assertAlmostEqual(y["Q_th_MW"], y["Q_brine_MW"] + y["P_el_MW"], delta=1e-3 * y["Q_th_MW"])
        self.assertAlmostEqual(y["COP"], y["Q_th_MW"] / y["P_el_MW"], delta=1e-9)
        self.assertTrue(2.0 < y["COP"] < 8.0)
        self.assertFalse(y["floor_binds"])
        self.assertAlmostEqual(y["T_water_out_C"], 100.0, delta=1e-6)

    def test_floor_binds(self):
        """At twice the duty the brine floor binds and the water stays below 100 C."""
        u, _ = balanced_case()
        u["water_flow_m3h"] *= 2.0
        y = run_hp(u)
        print(f"  2x duty: brine out {y['T_brine_out_C']:.2f} C, water out {y['T_water_out_C']:.2f} C")
        self.assertTrue(y["floor_binds"])
        self.assertLess(y["T_water_out_C"], 100.0)
        self.assertGreater(y["T_water_out_C"], u["T_water_in_C"])
        self.assertAlmostEqual(y["Q_th_MW"], y["Q_brine_MW"] + y["P_el_MW"], delta=1e-3 * y["Q_th_MW"])

    def test_gemini_floor_branch_wrong_root(self):
        """The floor branch of GEMINI gives an unphysical water temperature; HeatPumpLift 91.2 C."""
        u, _ = balanced_case()
        u["water_flow_m3h"] *= 2.0
        hp = HeatpumpBasic()
        hp.update_parameters({"mode": "lorenz", "eta_lorenz": 0.5, "Th_out_target": 100.0,
                              "Ts_in_minimum": u["T_brine_floor_C"], "rho_s": 1030.0, "Cp_s": 4000.0})
        hp.calculate_output({"Th_in": u["T_water_in_C"], "Ts_in": u["T_brine_in_C"],
                             "hot_flow_rate": u["water_flow_m3h"] / 3600,
                             "source_flow_rate": u["brine_flow_m3h"] / 3600})
        g, y = hp.get_output()["Th_out"], run_hp(u)["T_water_out_C"]
        print(f"  floor branch at 2x duty: GEMINI {g:.1f} C, HeatPumpLift {y:.2f} C")
        self.assertGreater(g, 100.0)
        self.assertAlmostEqual(y, 91.23, delta=0.1)

    def test_cop_matches_plant(self):
        """COP of HeatPumpLift within 5 % of the plant model."""
        u, r = balanced_case(duty_fraction=1.0)
        y = run_hp(u)
        print(f"  COP HeatPumpLift {y['COP']:.3f} vs geo.plant {r['cop']:.3f}")
        self.assertAlmostEqual(y["COP"], r["cop"], delta=0.05 * r["cop"])

    def test_register(self):
        """register() makes create_component("heatpump_lift") return a HeatPumpLift."""
        register()
        from gemini_simulator.registry import create_component
        self.assertIsInstance(create_component("heatpump_lift"), HeatPumpLift)


class TestGasAndLifetime(unittest.TestCase):
    """HenryGasBubblePoint and DoubletThermalBreakthrough against geo.gas and geo.lifetime."""

    def test_henry_gas_matches_geo_gas(self):
        """Bubble points (four settings) and gas rates equal geo.gas at 300 m3/h."""
        g = gas.gas_at(300.0)
        t_k = t_reservoir_c() + 273.15

        def run(**par):
            m = HenryGasBubblePoint()
            m.update_parameters(par)
            m.calculate_output({"temperature": t_k, "flowrate": 300.0 / 3600})
            return m.get_output()

        brine = {"nacl_concentration": gas.SALT_G_L}
        cases = (("p_bubble_pure_water_bar", {}), ("p_bubble_bar", brine),
                 ("p_bubble_log10_reading_bar", {**brine, "salting_out_convention": "log10"}),
                 ("p_bubble_upper_bar", {**brine, "henry_method": "vant_hoff"}))
        for key, par in cases:
            y = run(**par)
            print(f"  {key}: contrib {y['bubble_point_pressure'] / BAR:.3f} bar, geo.gas {g[key]:.3f} bar")
            self.assertAlmostEqual(y["bubble_point_pressure"] / BAR, g[key], delta=1e-9)
        y = run(**brine)
        self.assertAlmostEqual(y["gas_flowrate"] * 3600, g["gas_Nm3h"], delta=1e-9)
        self.assertAlmostEqual(y["methane_power"] / 1e6, g["CH4_MW_LHV"], delta=1e-9)
        self.assertAlmostEqual(y["co2_mass_flow"] * 3600, g["CO2_in_gas_kg_h"], delta=1e-9)

    def test_breakthrough_matches_geo_lifetime(self):
        """Breakthrough time, spacing for 30 years and interference equal geo.lifetime at 300 m3/h."""
        q = 300.0 / 3600
        for n in (1, 2, 3):
            m = DoubletThermalBreakthrough()
            m.update_parameters({"reservoir_thickness": THICKNESS_M, "porosity": lifetime.PHI,
                                 "water_density": RHO, "reservoir_permeability": PERM_MD * 9.869e-16,
                                 "viscosity": MU_PA_S, "number_of_doublets": n})
            m.calculate_output({"flowrate": q})
            y = m.get_output()
            ref = lifetime.interference_bar(n, 300.0)
            print(f"  {n} doublet(s): t_bt {y['breakthrough_time'] / YEAR:.2f} yr, "
                  f"interference {[round(v / BAR, 3) for v in y['interference_pressure']]} bar")
            self.assertAlmostEqual(y["breakthrough_time"] / YEAR, lifetime.t_bt_yr(300.0), delta=1e-9)
            for a, b in zip(y["interference_pressure"], ref):
                self.assertAlmostEqual(a / BAR, b, delta=1e-9)
        self.assertAlmostEqual(m.spacing_for_years(30.0, q), lifetime.spacing_for_yr(30.0, 300.0),
                               delta=1e-6)


if __name__ == "__main__":
    unittest.main()
