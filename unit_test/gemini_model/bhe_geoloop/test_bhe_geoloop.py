"""Unit tests for the geoloop BHE model."""

import unittest

import numpy as np

from gemini_model.bhe_geoloop.bhe_geoloop import BHEGeoloop

# lithology_params = {
#                             "input_dir_lithology": "input",
#                             "out_dir_lithology": "output",
#                             "borehole_lithology_path": "lithology_B58G0191_Roermond.xlsx",
#                             "borehole_lithology_sheetname": "poro-litho",
#                             "out_table": "lithology_samples_Roermond.h5",
#                             "read_from_table": True,
#                             "Tg": [
#                                 10.8, 10.4, 10.4, 10.6, 11.2,
#                                 11.5, 11.8, 12.0, 12.3, 12.5,
#                                 12.7, 13.0, 13.2, 13.4, 13.8,
#                                 14.1, 14.5, 14.9, 15.3, 15.6,
#                                 16.0, 16.3, 16.6, 17.0, 17.3,
#                                 17.7, 18.0, 18.3, 18.7, 19.0,
#                                 19.4, 19.7, 20.0, 20.4, 20.7,
#                                 21.1, 21.4, 21.7, 22.1, 22.4,
#                                 22.8, 23.1, 23.5, 23.8, 24.1,
#                                 24.5, 24.8, 25.2, 25.5, 25.8
#                             ],
#                             "Tgrad": 2,
#                             "z_Tg": [
#                                 20, 40, 60, 80, 100, 120, 140, 160, 180, 200,
#                                 220, 240, 260, 280, 300, 320, 340, 360, 380, 400,
#                                 420, 440, 460, 480, 500, 520, 540, 560, 580, 600,
#                                 620, 640, 660, 680, 700, 720, 740, 760, 780, 800,
#                                 820, 840, 860, 880, 900, 920, 940, 960, 980, 1000
#                             ],
#                             "phi_scale": 0.1,
#                             "lithology_scale": 0.1,
#                             "lithology_error": 0.1,
#                             "basecase": False,
#                             "n_samples": 500
#         }

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

	# def test_lithology_update_parameters(self):
	# 	"""Test nested dict parameters are merged rather than replaced."""

	# 	self.bhe_geoloop.update_parameters({"litho_k_param": {"added": 2.0}})

	# 	self.assertEqual(self.bhe_geoloop.parameters["litho_k_param"]["existing"], 1.0)
	# 	self.assertEqual(self.bhe_geoloop.parameters["litho_k_param"]["added"], 2.0)


if __name__ == "__main__":
	unittest.main()

