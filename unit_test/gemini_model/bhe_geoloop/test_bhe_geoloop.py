"""Unit tests for the geoloop BHE model."""

import unittest

import numpy as np

from gemini_model.bhe_geoloop.bhe_geoloop import BHEGeoloop

BHE_PARAMS = {
                "H": 300,

                "k_g": [0.8],
                "z_k_g": [300],

                "k_s": [2.5, 1, 2.5],
                "z_k_s": [25, 10, 300],

                "nsegments": 10,

                "Tin": 6
            }


class TestBHEGeoloop(unittest.TestCase):
	"""Test cases for the BHE geoloop wrapper model."""

	def setUp(self):
		"""Initialize the BHE geoloop model with default parameters."""
		self.bhe_geoloop = BHEGeoloop()
		self.bhe_geoloop.update_parameters(BHE_PARAMS)

	def test_calculate_output_power_mode_tracks_history(self):
		"""Test POWER mode output and history accumulation."""
		self.bhe_geoloop.update_parameters({"run_type": "POWER"})

		output = self.bhe_geoloop.calculate_output({"heat_demand": 1000,
		                                            "mass_flow_rate": 1.0})
		output = self.bhe_geoloop.output

		self.assertAlmostEqual(round(output["outlet_temperature"], 0), 12.0)
		self.assertAlmostEqual(round(output["pump_power"], 0), 464)
		self.assertAlmostEqual(round(output["mean_borehole_wall_temperature"], 1), 12.5)
		self.assertEqual(self.bhe_geoloop.state["step_index"], 1)
		self.assertEqual(self.bhe_geoloop._single_run.sim_params.Nt, 1)

	def test_calculate_output_tin_mode_tracks_history(self):
		"""Test TIN mode output and history accumulation."""
		self.bhe_geoloop.update_parameters({"run_type": "TIN"})

		output = self.bhe_geoloop.calculate_output({"inlet_temperature": 5.0,
		                                            "mass_flow_rate": 1.0})
		output = self.bhe_geoloop.output

		self.assertAlmostEqual(round(output["outlet_temperature"], 0), 6.0)
		self.assertAlmostEqual(round(output["heat_extracted"], 0), 6110)
		self.assertAlmostEqual(round(output["mean_borehole_wall_temperature"], 1), 8.7)
		self.assertEqual(self.bhe_geoloop.state["step_index"], 1)
		self.assertEqual(self.bhe_geoloop._single_run.sim_params.Nt, 1)

	def _run_tin(self, parameters):
		"""Run a single TIN step with extra parameters and return the output."""
		self.bhe_geoloop.update_parameters({"run_type": "TIN", **parameters})
		self.bhe_geoloop.calculate_output({"inlet_temperature": 5.0,
		                                  "mass_flow_rate": 1.0})
		return self.bhe_geoloop.output

	def test_depth_dependent_subsurface_profiles(self):
		"""Test a depth-dependent temperature and thermal conductivity affects the output."""
		z_tg = [0, 100, 200, 300]
		cold = self._run_tin({"Tg": [10, 10, 10, 10], "z_Tg": z_tg})
		self.assertAlmostEqual(round(cold["outlet_temperature"], 1), 5.9)
		self.assertAlmostEqual(round(cold["mean_borehole_wall_temperature"], 1), 7.2)

		low_k = self._run_tin({"k_s": [1.5, 1, 0.8], "z_k_s": [100, 200, 300]})
		self.assertAlmostEqual(round(low_k["heat_extracted"], 0), 3425)


if __name__ == "__main__":
	unittest.main()

