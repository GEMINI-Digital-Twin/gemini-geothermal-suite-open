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
            "hot_flow_rate": 10.0 / 3600.0,  # m3/s
            "source_flow_rate": 20.0 / 3600.0,  # m3/s
        }

        heatpump.calculate_output(u, None)
        output = heatpump.get_output()

        self.assertAlmostEqual(output["COP"], 4.4144, delta=1e-3)
        self.assertAlmostEqual(output["Th_out"], 80.0, delta=1e-3)
        self.assertAlmostEqual(output["Ts_out"], 20.6633, delta=1e-3)
        self.assertAlmostEqual(output["Thermal_production"], 580694.44, delta=0.1)
        self.assertAlmostEqual(output["electrical_consumption"], 131546.24, delta=0.1)

    def test_calculate_output_lorenz_mode(self):
        """Test HeatpumpBasic output calculation in Lorenz mode."""
        heatpump = self._create_lorenz_model()
        u = {
            "Th_in": 30,  # °C
            "Ts_in": 40,  # °C
            "hot_flow_rate": 10.0 / 3600.0,  # m3/s
            "source_flow_rate": 20.0 / 3600.0,  # m3/s
        }

        heatpump.calculate_output(u, None)
        output = heatpump.get_output()

        self.assertAlmostEqual(output["COP"], 6.5310, delta=1e-3)
        self.assertAlmostEqual(output["Th_out"], 80.0, delta=1e-3)
        self.assertAlmostEqual(output["Ts_out"], 18.8279, delta=1e-3)
        self.assertAlmostEqual(output["Thermal_production"], 580694.44, delta=0.1)
        self.assertAlmostEqual(output["electrical_consumption"], 88913.32, delta=0.1)

    def test_carnot_cop_satisfies_carnot_equation(self):
        """The Carnot COP must equal eta * Th_out / (Th_out - Ts_in) for any flow."""
        heatpump = self._create_carnot_model()
        heatpump.update_parameters({"Th_out_target": 100, "Ts_in_minimum": 47})
        u = {
            "Th_in": 84.0,  # °C
            "Ts_in": 59.4,  # °C
            "hot_flow_rate": 0.0021,  # m3/s
            "source_flow_rate": 0.0705,  # m3/s
        }

        heatpump.calculate_output(u, None)
        output = heatpump.get_output()

        expected_cop = 0.5 * 373.15 / (373.15 - 332.55)
        self.assertAlmostEqual(output["COP"], expected_cop, delta=1e-6)
        self.assertAlmostEqual(output["Th_out"], 100.0, delta=1e-6)
        balance = output["Thermal_production"] * (1 - 1 / output["COP"])
        source_heat = 4181 * 1000 * 0.0705 * (59.4 - output["Ts_out"])
        self.assertAlmostEqual(balance, source_heat, delta=1e-3)

    def test_carnot_source_minimum_limits_sink_temperature(self):
        """If the source would drop below Ts_in_minimum, Th_out is lowered instead."""
        heatpump = self._create_carnot_model()
        heatpump.update_parameters({"Ts_in_minimum": 35})
        u = {
            "Th_in": 30,  # °C
            "Ts_in": 40,  # °C
            "hot_flow_rate": 10.0 / 3600.0,  # m3/s
            "source_flow_rate": 20.0 / 3600.0,  # m3/s
        }

        heatpump.calculate_output(u, None)
        output = heatpump.get_output()

        self.assertAlmostEqual(output["Ts_out"], 35.0, delta=1e-6)
        self.assertLess(output["Th_out"], 80.0)
        source_heat = 4181 * 1000 * (20.0 / 3600.0) * 5.0
        balance = output["Thermal_production"] * (1 - 1 / output["COP"])
        self.assertAlmostEqual(balance, source_heat, delta=1e-3)
        expected_cop = 0.5 * (output["Th_out"] + 273.15) / (output["Th_out"] - 40.0)
        self.assertAlmostEqual(output["COP"], expected_cop, delta=1e-6)

    def test_flow_and_pressure_passthrough(self):
        """Test that flow rates and pressures are echoed back as outputs."""
        heatpump = self._create_carnot_model()
        u = {
            "Th_in": 30,  # °C
            "Ts_in": 40,  # °C
            "hot_flow_rate": 10.0 / 3600.0,  # m3/s
            "source_flow_rate": 20.0 / 3600.0,  # m3/s
            "hot_pressure_in": 5.0,  # bar
            "source_pressure_in": 3.0,  # bar
        }

        heatpump.calculate_output(u, None)
        output = heatpump.get_output()

        self.assertAlmostEqual(output["hot_flow_rate"], 10.0 / 3600.0)
        self.assertAlmostEqual(output["hot_flow_rate_m3h"], 10.0)
        self.assertAlmostEqual(output["source_flow_rate"], 20.0 / 3600.0)
        self.assertAlmostEqual(output["source_flow_rate_m3h"], 20.0)
        self.assertAlmostEqual(output["hot_pressure_in"], 5.0)
        self.assertAlmostEqual(output["hot_pressure_out"], 5.0)
        self.assertAlmostEqual(output["source_pressure_in"], 3.0)
        self.assertAlmostEqual(output["source_pressure_out"], 3.0)
        self.assertAlmostEqual(output["power_th"], output["Thermal_production"])
        self.assertAlmostEqual(output["power_el"], output["electrical_consumption"])


if __name__ == "__main__":
    unittest.main()
