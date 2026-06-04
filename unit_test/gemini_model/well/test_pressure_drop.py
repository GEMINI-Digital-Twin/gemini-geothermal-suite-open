"""Unit tests for well pressure drop model."""

import unittest

import numpy as np

from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.well.pressure_drop import DPDT


class TestDPDT(unittest.TestCase):
    """Test cases for well pressure drop model."""

    def test_calculate_bottomhole(self):
        """Test well pressure drop bottomhole calculation."""
        # ARRANGE
        well_param = dict()

        well_param["diameter"] = (
            np.array([6.366, 6.366, 9.95, 6.366, 3.92]) * 0.0254
        )  # casing diameter in [m]
        well_param["length"] = np.array([0, 148, 949, 1012, 218])  # well length in [m]
        well_param["angle"] = np.array([90, 90, 69.0, 44.4, 40.3]) * np.pi / 180
        # well angle in [rad]
        well_param["roughness"] = np.array(
            [0.0003, 0.0003, 0.0003, 0.0003, 0.0003]
        )  # well roughness in [m]
        well_param["friction_correlation"] = "darcy_weisbach"
        well_param["friction_correlation_2p"] = "BeggsBrill"
        well_param["correction_factors"] = [1, 0]

        well_instance = DPDT()

        well_instance.update_parameters(well_param)
        well_instance.PVT = PVTConstantSTP()

        # Test 1: injection flow rate of 10 m3/hr and checked dp_fric using darcy correlation
        x = []

        u = dict()
        u["flowrate"] = -10 / 3600  # m3/s
        u["temperature"] = 61.5 + 273.15  # K
        u["pressure"] = 1 * 1e5  # Pa
        u["direction"] = "down"  # injection well
        u["temperature_ambient"] = 20 + 273.15  # K

        # ACT
        well_instance.calculate_output(u, x)

        # ASSERT
        y = well_instance.get_output()

        self.assertAlmostEqual(y["pressuredrop_fric_output"], -6264.02, delta=0.01)

        # Test 2: flow rate of 0 m3/hr and checked dp_fric using darcy correlation
        x = []

        u = dict()
        u["flowrate"] = 0 / 3600  # m3/s
        u["temperature"] = 61.5 + 273.15  # K
        u["pressure"] = 1 * 1e5  # Pa
        u["direction"] = "down"  # injection well
        u["temperature_ambient"] = 20 + 273.15  # K

        # ACT
        well_instance.calculate_output(u, x)

        # ASSERT
        y = well_instance.get_output()

        self.assertAlmostEqual(y["pressuredrop_fric_output"], 0, delta=0.01)

    def test_calculate_wellhead(self):
        """Test well pressure drop wellhead calculation."""
        # ARRANGE
        well_param = dict()

        well_param["diameter"] = (
            np.array([8.535, 8.535, 8.535, 8.535, 8.535]) * 0.0254
        )  # casing diameter in [m]
        well_param["length"] = np.array([400, 600, 600, 400, 200])  # well length in [m]
        well_param["angle"] = np.array([90, 90, 90, 75, 60]) * np.pi / 180  # well angle in [rad]
        well_param["roughness"] = np.array(
            [0.01e-3, 0.01e-3, 0.01e-3, 0.01e-3, 0.01e-3]
        )  # well roughness in [m]
        well_param["friction_correlation"] = "darcy_weisbach"
        well_param["friction_correlation_2p"] = "BeggsBrill"
        well_param["correction_factors"] = [1, 0]

        well_instance = DPDT()

        well_instance.update_parameters(well_param)
        well_instance.PVT = PVTConstantSTP()

        x = []

        u = dict()
        u["pressure"] = 250 * 1e5  # Pa
        u["temperature"] = 80 + 273.15  # K
        u["flowrate"] = 150 / 3600  # m3/s
        u["temperature_ambient"] = 20 + 273.15
        u["direction"] = "up"  # production well
        u["correction_a"] = 1
        u["correction_b"] = 0

        # ACT
        well_instance.calculate_output(u, x)

        # ASSERT
        y = well_instance.get_output()

        self.assertAlmostEqual(y["pressure_output"], 3714980.20, delta=0.01)
        self.assertAlmostEqual(y["temperature_output"], 75.06 + 273.15, delta=0.01)
