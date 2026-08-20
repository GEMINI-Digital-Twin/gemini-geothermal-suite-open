"""Unit tests for the HeatpumpBasic model."""

import unittest

from gemini_model.heatpump.heatpump_basic import HeatpumpBasic


class TestHeatpumpBasic(unittest.TestCase):
    """Test cases for the Carnot-efficiency based HeatpumpBasic model."""

    def _create_carnot_model(self):
        heatpump = HeatpumpBasic()
        heatpump.update_parameters(
            {
                "mode": "carnot",
                "eta_carnot": 0.5,
                "eta_lorenz": 0.5,
                "COP_0": 4.0,
                "Cp_h": 4181,  # J/kg.K
                "Cp_s": 4181,  # J/kg.K
                "rho_h": 1000,  # kg/m3
                "rho_s": 1000,  # kg/m3
                "Th_out_target": 80,  # °C
                "Ts_in_minimum": 5,  # °C
            }
        )
        return heatpump

    def _create_lorenz_model(self):
        heatpump = HeatpumpBasic()
        heatpump.update_parameters(
            {
                "mode": "lorenz",
                "eta_carnot": 0.5,
                "eta_lorenz": 0.5,
                "COP_0": 4.0,
                "Cp_h": 4181,  # J/kg.K
                "Cp_s": 4181,  # J/kg.K
                "rho_h": 1000,  # kg/m3
                "rho_s": 1000,  # kg/m3
                "Th_out_target": 80,  # °C
                "Ts_in_minimum": 5,  # °C
            }
        )
        return heatpump

    def test_calculate_output_carnot_mode(self):
        """Test HeatpumpBasic output calculation in Carnot mode."""
        heatpump = self._create_carnot_model()
        u = {
            "Th_in": 30,  # °C
            "Ts_in": 40,  # °C
            "qh": 10.0,  # m3/h
            "qs": 20.0,  # m3/h
        }

        heatpump.calculate_output(u, None)
        output = heatpump.get_output()

        self.assertAlmostEqual(output["COP"], 4.4144, delta=1e-3)
        self.assertAlmostEqual(output["Th_out"], 80.0, delta=1e-3)
        self.assertAlmostEqual(output["Ts_out"], 20.6633, delta=1e-3)
        self.assertAlmostEqual(output["Thermal_production"], 580694.44, delta=0.1)
        self.assertAlmostEqual(output["electrical_consumption"], 131546.03, delta=0.1)

    def test_calculate_output_lorenz_mode(self):
        """Test HeatpumpBasic output calculation in Lorenz mode."""
        heatpump = self._create_lorenz_model()
        u = {
            "Th_in": 30,  # °C
            "Ts_in": 40,  # °C
            "qh": 10.0,  # m3/h
            "qs": 20.0,  # m3/h
        }

        heatpump.calculate_output(u, None)
        output = heatpump.get_output()

        self.assertAlmostEqual(output["COP"], 6.5310, delta=1e-3)
        self.assertAlmostEqual(output["Th_out"], 80.0, delta=1e-3)
        self.assertAlmostEqual(output["Ts_out"], 18.8279, delta=1e-3)
        self.assertAlmostEqual(output["Thermal_production"], 580694.44, delta=0.1)
        self.assertAlmostEqual(output["electrical_consumption"], 88913.32, delta=0.1)


if __name__ == "__main__":
    unittest.main()
