"""Cross-checks: our five GEMINI models (in the fork's src/gemini_model) against the plant model in geo.

The models' own unit tests live in the fork, unit_test/gemini_model/. Run: python -m unittest geo.test_gemini_models -v
"""
import sys
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geo.gemini_path  # noqa: F401  (puts the GEMINI tree with our models first on sys.path)
from gemini_model.chiller.absorption_chiller import AbsorptionChiller
from gemini_model.fluid.henry_gas import HenryGasBubblePoint
from gemini_model.heatpump.heatpump_lift import HeatPumpLift
from gemini_model.pump.esp import ESP
from gemini_model.pump.esp_affinity import ESPAffinity
from gemini_model.reservoir.thermal_breakthrough import YEAR, DoubletThermalBreakthrough

from geo import gas, lifetime, plant, year
from geo.common import MU_PA_S, PERM_MD, RHO, THICKNESS_M, t_reservoir_c
from geo.well import Producer, _pump

BAR = 1e5


def esp_out(model_class, params, freq, flow):
    """Output of a pump model at freq (Hz) and flow (m3/s)."""
    m = model_class()
    m.update_parameters(dict(params))
    m.calculate_output({"pump_freq": freq, "pump_flow": flow})
    return m.get_output()


class TestESPAffinity(unittest.TestCase):
    """Similarity-law pump on our 24-stage pump."""

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
        """The producer well model gives the ESPAffinity head at its own operating point."""
        w = Producer(stages=24)
        f = w.freq_for_wellhead(300.0, 10.0)
        head = w.run(300.0, f)["esp_head_bar"]
        a = esp_out(ESPAffinity, _pump(24).parameters, f, 300.0 / 3600)["pump_head"] / BAR
        self.assertAlmostEqual(head / a, 1.0, delta=1e-6)


class TestHeatPumpLift(unittest.TestCase):
    """HeatPumpLift against the plant model."""

    def test_constants_match_plant(self):
        """Heat capacity, brine density and Lorenz efficiency match the plant model."""
        hp = HeatPumpLift()
        self.assertEqual(hp.parameters["Cp_s"], plant.CP * 1000)
        self.assertEqual(hp.parameters["rho_s"], plant.RHO)
        self.assertEqual(hp.parameters["eta_lorenz"], plant.LORENZ_EFF)

    def test_cop_matches_plant(self):
        """COP of HeatPumpLift within 5 % of the plant model at 300 m3/h and 60 C return."""
        r = plant.doublet_at(Producer(stages=24), 300.0, 60.0)
        t_wh = r["T_wh_C"]
        t_water_in = t_wh - plant.APPROACH_K
        q_water = r["MW_hp"] * 1e6 / (1000.0 * plant.CP * 1000 * (100.0 - t_water_in))
        hp = HeatPumpLift()
        hp.calculate_output({"T_brine_in_C": 60.0 + plant.APPROACH_K, "brine_flow_m3h": 300.0,
                             "T_brine_floor_C": t_wh - plant.DT_BRINE_MAX_K, "T_water_in_C": t_water_in,
                             "water_flow_m3h": q_water * 3600})
        y = hp.get_output()
        print(f"  COP HeatPumpLift {y['COP']:.3f} vs geo.plant {r['cop']:.3f}")
        self.assertAlmostEqual(y["COP"], r["cop"], delta=0.05 * r["cop"])


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
            print(f"  {key}: model {y['bubble_point_pressure'] / BAR:.3f} bar, geo.gas {g[key]:.3f} bar")
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


def run_chiller(temperature=85.6, **extra):
    """Output of AbsorptionChiller for 300 m3/h of brine at 10 bar."""
    m = AbsorptionChiller()
    m.calculate_output({"pressure": 10.0, "temperature": temperature, "flow_rate": 300 / 3600, **extra})
    return m.get_output()


class TestAbsorptionChiller(unittest.TestCase):
    """AbsorptionChiller against the plant constants and plant._abs_drive."""

    def test_constants_match_plant(self):
        """COP equals year.COP_ABSORPTION and the driving minimum equals plant.T_ABS_MIN_C."""
        p = AbsorptionChiller().parameters
        self.assertEqual(p["cop_thermal"], year.COP_ABSORPTION)
        self.assertEqual(p["min_driving_temperature"], plant.T_ABS_MIN_C)

    def test_drive_matches_plant(self):
        """Chiller drive equals plant._abs_drive at 300 m3/h and 60 C return for four exchanger duties."""
        p = plant.doublet_at(Producer(stages=24), 300.0, 60.0)
        t_wh, mcp = p["T_wh_C"], p["mcp_MW_per_K"]
        # full duty leaves nothing above the floor; 4 MW puts the floor below the 78 C minimum, 5.2 and 6 MW just above it
        for hx in (p["MW_hx"], 4.0, 5.2, 6.0):
            floor = 60.0 + plant.APPROACH_K + hx / mcp
            y = run_chiller(temperature=t_wh, temperature_floor=floor)
            ref = plant._abs_drive(t_wh, mcp, 60.0, hx)
            print(f"  hx {hx:.3f} MW: drive chiller {y['drive_heat'] / 1e6:.6f} MW, plant {ref:.6f} MW")
            self.assertAlmostEqual(y["drive_heat"] / 1e6, ref, delta=1e-6)


if __name__ == "__main__":
    unittest.main()
