"""Unit tests for CO2 corrosion model."""

import math
import unittest

from gemini_model.corrosion.co2_corrosion import CO2Corrosion


class TestCO2Corrosion(unittest.TestCase):
    """Test CO2 corrosion calculations."""

    def test_get_corrosion_rate_norsok(self):
        """Test NORSOK corrosion rate calculation."""
        well_param = dict()
        well_param["roughness"] = 50e-6
        well_param["corrosion_model"] = "NORSOK"
        well_param["diameter"] = 0.1

        model = CO2Corrosion()
        model.update_parameters(well_param)
        x = []
        u = {
            "co2_fraction": 0.1,  # CO2 concentration [-]
            "pressure": 3,  # Total pressure [bar]
            "temperature": 40,  # Temperature [C]
            "water_density": 1024,  # kg/m3
            "water_viscosity": 0.5469,  # cp
            "water_flow_rate": 1000,  # m3/day
            "bicarb_concentration": 268,  # mg/l
            "ionic_strength": 71,  # g/l
            "calc_of_ph": 10,  # [-]
        }
        # ACT
        model.calculate_output(u, x)
        corrosion_rate = model.get_output()["corrosion_rate"]
        # ASSERT
        expected_corrosion_rate = 1.412  # [mm/year]
        self.assertAlmostEqual(corrosion_rate, expected_corrosion_rate, places=3)

    def test_get_corrosion_rate_dld(self):
        """Test DLD corrosion rate calculation."""
        well_param = dict()
        well_param["corrosion_model"] = "DLD"
        well_param["diameter"] = 0.1

        model = CO2Corrosion()
        model.update_parameters(well_param)
        x = []
        u = {
            "co2_fraction": 1,  # CO2 concentration [-]
            "pressure": 3,  # Total pressure [bar]
            "temperature": 50,  # Temperature [C]
            "flow_rate": 1 * math.pi * (well_param["diameter"] ** 2) / 4.0,
        }
        # ACT
        model.calculate_output(u, x)
        corrosion_rate = model.get_output()["corrosion_rate"]
        # ASSERT
        expected_corrosion_rate = 9.6  # [mm/year]
        self.assertAlmostEqual(corrosion_rate, expected_corrosion_rate, places=1)

    def test_get_corrosion_rate_dlm(self):
        """Test DLM corrosion rate calculation."""
        well_param = dict()
        well_param["corrosion_model"] = "DLM"

        model = CO2Corrosion()
        model.update_parameters(well_param)
        x = []
        u = {
            "co2_fraction": 1,  # CO2 concentration [-]
            "pressure": 3,  # Total pressure [bar]
            "temperature": 50,  # Temperature [C]
        }
        # ACT
        model.calculate_output(u, x)
        corrosion_rate = model.get_output()["corrosion_rate"]
        # ASSERT
        expected_corrosion_rate = 6.7  # [mm/year]
        self.assertAlmostEqual(corrosion_rate, expected_corrosion_rate, places=1)
