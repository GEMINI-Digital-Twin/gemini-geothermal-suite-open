"""Unit tests for the Henry's-law bubble point model."""

import unittest

from gemini_model.fluid.henry_gas import HenryGasBubblePoint

T_RES = 87 + 273.15  # K
BAR = 1e5  # Pa


def _run(parameters=None, flowrate=None):
    model = HenryGasBubblePoint()
    model.update_parameters(parameters or {})
    u = {"temperature": T_RES}
    if flowrate is not None:
        u["flowrate"] = flowrate
    model.calculate_output(u)
    return model.get_output()


class TestHenryGasBubblePoint(unittest.TestCase):
    """Bubble point and gas rates for GLR 0.8 Nm3/m3, 80/20 CH4/CO2 at 87 C."""

    def test_bubble_point_pure_water(self):
        """Pure water: 35.8 bar."""
        self.assertAlmostEqual(_run()["bubble_point_pressure"] / BAR, 35.8, delta=0.5)

    def test_bubble_point_brine_ln(self):
        """45 g/L NaCl, ln convention: 45.6 bar."""
        y = _run({"nacl_concentration": 45.0})
        self.assertAlmostEqual(y["bubble_point_pressure"] / BAR, 45.6, delta=0.5)

    def test_log10_convention_is_higher(self):
        """The log10 reading of the coefficient salts out more than the ln reading."""
        ln = _run({"nacl_concentration": 45.0})["bubble_point_pressure"]
        log10 = _run({"nacl_concentration": 45.0, "salting_out_convention": "log10"})
        self.assertGreater(log10["bubble_point_pressure"], ln)

    def test_vant_hoff_alternative(self):
        """The van 't Hoff extrapolation from 298.15 K gives a different, higher bubble point."""
        fits = _run()["bubble_point_pressure"]
        vant_hoff = _run({"henry_method": "vant_hoff"})["bubble_point_pressure"]
        self.assertGreater(vant_hoff, fits)

    def test_gas_rates(self):
        """300 m3/h of brine carries 240 Nm3/h of gas; fuel power and CO2 follow the split."""
        y = _run(flowrate=300 / 3600)
        self.assertAlmostEqual(y["gas_flowrate"] * 3600, 240.0, delta=1e-9)
        self.assertAlmostEqual(y["methane_power"] / 1e6, 1.910, delta=0.001)
        self.assertAlmostEqual(y["co2_mass_flow"] * 3600, 94.25, delta=0.01)

    def test_no_flowrate_no_rates(self):
        """Without a flowrate only the bubble point and the concentrations are returned."""
        self.assertNotIn("gas_flowrate", _run())


if __name__ == "__main__":
    unittest.main()
