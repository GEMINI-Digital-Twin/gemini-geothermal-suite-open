"""Unit tests for the doublet thermal breakthrough and interference model."""

import unittest

from gemini_model.reservoir.thermal_breakthrough import YEAR, DoubletThermalBreakthrough

Q = 300 / 3600  # m3/s
BAR = 1e5  # Pa
PARAMS = {
    "reservoir_thickness": 100.0,  # m
    "porosity": 0.20,  # -
    "reservoir_permeability": 200 * 9.869233e-16,  # 200 mD in m2
    "viscosity": 0.40e-3,  # Pa s
}


def _model(**parameters):
    model = DoubletThermalBreakthrough()
    model.update_parameters({**PARAMS, **parameters})
    return model


def _run(**parameters):
    model = _model(**parameters)
    model.calculate_output({"flowrate": Q})
    return model.get_output()


class TestDoubletThermalBreakthrough(unittest.TestCase):
    """Breakthrough and interference at 300 m3/h, 100 m, phi 0.20, 200 mD, 0.40 mPa s."""

    def test_breakthrough_1020_m(self):
        """1020 m spacing: 30.0 years."""
        y = _run(well_spacing=1020.0)
        self.assertAlmostEqual(y["breakthrough_time"] / YEAR, 30.0, delta=0.5)

    def test_breakthrough_1500_m(self):
        """1500 m spacing (default): 64.9 years."""
        self.assertAlmostEqual(_run()["breakthrough_time"] / YEAR, 64.9, delta=0.5)

    def test_spacing_for_years(self):
        """Spacing for 30 years is about 1020 m and gives back 30 years."""
        model = _model()
        spacing = model.spacing_for_years(30.0, Q)
        self.assertAlmostEqual(spacing, 1020.0, delta=5.0)
        self.assertAlmostEqual(model.breakthrough_time(Q, spacing) / YEAR, 30.0, delta=1e-9)

    def test_interference_two_doublets(self):
        """Two doublets 1500 m apart: 0.93 bar at each injector."""
        y = _run(number_of_doublets=2)
        self.assertEqual(len(y["interference_pressure"]), 2)
        for dp in y["interference_pressure"]:
            self.assertAlmostEqual(dp / BAR, 0.93, delta=0.02)
        self.assertAlmostEqual(y["interference_pressure_max"] / BAR, 0.93, delta=0.02)

    def test_interference_three_doublets(self):
        """Three doublets: the middle injector sees the most."""
        dp = _run(number_of_doublets=3)["interference_pressure"]
        self.assertAlmostEqual(dp[0], dp[2], delta=1e-9)
        self.assertGreater(dp[1], dp[0])

    def test_interference_one_doublet(self):
        """One doublet has no neighbour."""
        y = _run()
        self.assertEqual(y["interference_pressure"], [0.0])
        self.assertEqual(y["interference_pressure_max"], 0.0)

    def test_zero_doublets_rejected(self):
        """Fewer than one doublet raises ValueError."""
        with self.assertRaises(ValueError):
            _run(number_of_doublets=0)


if __name__ == "__main__":
    unittest.main()
