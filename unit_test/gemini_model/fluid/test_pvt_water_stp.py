"""Unit tests for PVT water STP model."""

import unittest

from gemini_model.fluid.pvt_water_stp import PVTConstantSTP


class TestPVTWaterSTP(unittest.TestCase):
    """Test cases for PVT water STP model."""

    def test_get_pvt(self):
        """Test PVT water STP calculation."""
        # ARRANGE
        pvt_instance = PVTConstantSTP()

        # ACT
        P = 1e5
        T = 15 + 273.15
        rho_g, rho_l, gmf, eta_g, eta_l, cp_g, cp_l, K_g, K_l, sigma = pvt_instance.get_pvt(P, T)

        # ASSERT
        self.assertEqual(rho_l, 1000)
