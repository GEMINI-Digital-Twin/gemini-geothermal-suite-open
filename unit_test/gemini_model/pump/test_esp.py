"""Unit tests for ESP pump model."""

import unittest

from gemini_model.pump.esp import ESP


class TestESP(unittest.TestCase):
    """Test cases for ESP pump model."""

    def test_esp_calculation(self):
        """Test ESP pump calculation."""
        # ARRANGE
        esp_param = dict()

        esp_param["pump_name"] = "HC27000"
        esp_param["no_stages"] = 12
        esp_param["head_coeff"] = [
            83.08389282,
            -0.000460444,
            -1.19e-07,
            1.69e-11,
            -6.36e-16,
            6.69e-21,
        ]
        esp_param["power_coeff"] = [
            10.02089977,
            -0.000160233,
            6.52e-08,
            -2.13e-12,
            1.71e-17,
            1.38e-23,
        ]

        esp_instance = ESP()
        esp_instance.update_parameters(esp_param)

        x = []

        u = dict()
        u["pump_freq"] = 60  # Hz
        u["pump_flow"] = 200 / 3600  # m3/h to m3/s

        # ACT
        esp_instance.calculate_output(u, x)

        # ASSERT
        y = esp_instance.get_output()

        self.assertAlmostEqual(y["pump_head"] / 1e5, 23.37, delta=0.01)  # bar
        self.assertAlmostEqual(y["pump_power"] / 1e3, 183.89, delta=0.01)  # kW
        self.assertAlmostEqual(y["pump_eff"], 70.53, delta=0.01)  # %

    def test_esp_missing_coefficient_power(self):
        """Test ESP pump with missing power coefficient."""
        # ARRANGE
        esp_param = dict()
        esp_param["pump_name"] = "HC27000"
        esp_param["no_stages"] = 12
        esp_param["head_coeff"] = [
            83.08389282,
            -0.000460444,
            -1.19e-07,
            1.69e-11,
            -6.36e-16,
            6.69e-21,
        ]
        esp_param["power_coeff"] = [
            10.02089977,
            -0.000160233,
            6.52e-08,
            -2.13e-12,
            1.71e-17,
            1.38e-23,
        ]

        esp_instance = ESP()
        esp_instance.update_parameters(esp_param)

        esp_instance.parameters["power_coeff"] = [0, 0, 0, 0, 0, 0]

        x = []
        u = dict()
        u["pump_freq"] = 60  # Hz
        u["pump_flow"] = 200 / 3600  # m3/h to m3/s

        # ACT
        esp_instance.calculate_output(u, x)
        # ASSERT
        y = esp_instance.get_output()
        self.assertAlmostEqual(y["pump_power"] / 1e3, 0, delta=0.01)  # kW
        self.assertAlmostEqual(y["pump_eff"], 0, delta=0.01)  # %
