"""Unit tests for the brine-driven absorption chiller model."""

import unittest

from gemini_model.chiller.absorption_chiller import AbsorptionChiller
from gemini_simulator.project_loader import build_project
from gemini_simulator.registry import create_component

FLOW = 300.0 / 3600.0  # m3/s, 300 m3/h of brine
MCP = 1030.0 * FLOW * 4000.0  # W/K, about 343 333


def _run(temperature=85.6, **extra):
    model = AbsorptionChiller()
    u = {"pressure": 10.0, "temperature": temperature, "flow_rate": FLOW}
    model.calculate_output({**u, **extra})
    return model.get_output()


class TestAbsorptionChiller(unittest.TestCase):
    """Drive heat, cold and brine outlet for 300 m3/h of brine at 10 bar."""

    def test_full_drive_at_85_6_c(self):
        """85.6 C brine cooled to 78 C: 2.609 MW drive, 1.957 MW cold, 58.7 kW electricity."""
        y = _run()
        self.assertAlmostEqual(MCP, 343333, delta=1.0)
        self.assertAlmostEqual(y["drive_heat"] / 1e6, 2.609, delta=0.001)
        self.assertAlmostEqual(y["cooling_power"] / 1e6, 1.957, delta=0.001)
        self.assertAlmostEqual(y["temperature_out"], 78.0, delta=1e-9)
        self.assertAlmostEqual(y["power_el"] / 1e3, 58.7, delta=0.1)
        self.assertEqual(y["pressure_out"], 10.0)
        self.assertEqual(y["cooling_unmet"], 0.0)

    def test_brine_too_cold(self):
        """70 C brine is below the driving minimum: no drive, no cold, outlet equals inlet."""
        y = _run(temperature=70.0)
        self.assertEqual((y["drive_heat"], y["cooling_power"]), (0.0, 0.0))
        self.assertEqual(y["temperature_out"], 70.0)

    def test_cooling_demand_caps_drive(self):
        """A 1 MW demand takes 1.333 MW of drive and leaves the brine at 81.72 C."""
        y = _run(cooling_demand=1.0e6)
        self.assertAlmostEqual(y["drive_heat"] / 1e6, 1.3333, delta=1e-4)
        self.assertAlmostEqual(y["cooling_power"], 1.0e6, delta=1e-6)
        self.assertAlmostEqual(y["temperature_out"], 81.72, delta=0.01)
        self.assertAlmostEqual(y["cooling_unmet"], 0.0, delta=1e-6)
        self.assertEqual(_run(cooling_demand=-1.0e6)["drive_heat"], 0.0)  # negative demand

    def test_floor_above_minimum(self):
        """A floor of 80 C leaves 5.6 K: 1.923 MW of drive."""
        y = _run(temperature_floor=80.0)
        self.assertEqual(y["drive_temperature_floor"], 80.0)
        self.assertAlmostEqual(y["drive_heat"] / 1e6, 1.923, delta=0.001)

    def test_floor_below_minimum_ignored(self):
        """A floor of 70 C is below the driving minimum, so the floor stays 78 C."""
        y = _run(temperature_floor=70.0)
        self.assertEqual(y["drive_temperature_floor"], 78.0)
        self.assertAlmostEqual(y["temperature_out"], 78.0, delta=1e-9)

    def test_registry(self):
        """create_component("absorption_chiller") returns an AbsorptionChiller."""
        self.assertIsInstance(create_component("absorption_chiller"), AbsorptionChiller)

    def test_project_filter_to_chiller(self):
        """A filter without temperature drop feeding the chiller gives 1.957 MW of cold."""
        project = {
            "components": {
                "filter": {
                    "type": "filter",
                    "parameters": {
                        "base_resistance": 3.6,
                        "fouling_coeff_a": 18.0,
                        "fouling_coeff_b": 0.036,
                        "temperature_drop": 0,
                    },
                },
                "chiller": {"type": "absorption_chiller", "parameters": {}},
            },
            "boundary_inputs": [
                {"component": "filter", "key": "pressure", "value": 10.0},
                {"component": "filter", "key": "temperature", "value": 85.6},
                {"component": "filter", "key": "flow_rate", "value": FLOW},
            ],
            "connections": [
                {
                    "predecessor": "filter",
                    "successor": "chiller",
                    "ports": [
                        ["pressure_out", "pressure"],
                        ["temperature_out", "temperature"],
                        ["flow_rate", "flow_rate"],
                    ],
                }
            ],
        }
        solver = build_project(project)
        solver.run()
        cooling = solver.get_output("chiller", "cooling_power")
        self.assertAlmostEqual(cooling / 1e6, 1.957, delta=0.001)


if __name__ == "__main__":
    unittest.main()
