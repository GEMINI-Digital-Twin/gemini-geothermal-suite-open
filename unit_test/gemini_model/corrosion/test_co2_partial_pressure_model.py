"""Unit tests for CO2 partial pressure model."""

import unittest

from gemini_model.corrosion.correlation.co2_partial_pressure_model import CO2PartialPressureModel


class TestCO2PartialPressureModel(unittest.TestCase):
    """Test cases for CO2 partial pressure model."""

    def test_get_co2_partial_pressure(self):
        """Test CO2 partial pressure calculation."""
        # Test data taken from WEP CO2 Partial Pressure model.
        # ARRANGE
        co2_model = CO2PartialPressureModel()
        x = []
        u = {
            "co2_mol_fraction": 0.1882,  # CO2 mol fraction in a gas phase[-]
            "gas_pressure": 1,  # Total Gas Pressure at sample P and T[bar]
            "gas_water_ratio": 0.4224,  # GWR [-]
            "gas_density": 1.027,  # Gas-water mixture density [kg/m3]
            "gas_molecular_weight": 22.955,  # Gas-water molecular weight [g/mol]
            "temperature_sample": 20,  # Temperature of a sample [C]
            "temperature_system": 85,  # System Temperature [C]
        }
        # ACT
        # Calculate dissolved CO2
        result_dissolved_co2 = co2_model._get_CO2_solubility_in_liquid(
            u["co2_mol_fraction"], u["temperature_sample"], u["gas_pressure"]
        )
        # Calculate gas phase CO2
        result_gas_phase_co2 = co2_model._get_CO2_solubility_in_gas(
            u["co2_mol_fraction"], u["gas_water_ratio"], u["gas_density"], u["gas_molecular_weight"]
        )
        co2_model.calculate_output(u, x)
        result_co2_partial_pressure = co2_model.get_output()["CO2 Partial Pressure [bar]"]
        # ASSERT
        expected_dissolved_co2 = 0.007245
        expected_gas_phase_co2 = 0.003557
        expected_co2_partial_pressure = 1.2398
        self.assertAlmostEqual(result_dissolved_co2, expected_dissolved_co2, places=3)
        self.assertAlmostEqual(result_gas_phase_co2, expected_gas_phase_co2, places=3)
        self.assertAlmostEqual(result_co2_partial_pressure, expected_co2_partial_pressure, places=3)
