"""Bubble point and gas rates of a brine with dissolved methane and CO2, by Henry's law.

Henry constants: Sander (2023), https://www.henrys-law.org (methane 74-82-8, CO2 124-38-9).
Parameter sources are in the inline comments. Output: bubble point (Pa), dissolved
concentrations (mol/m3) and, with a flowrate, gas rate (Nm3/s), methane power (W), CO2 (kg/s).
"""

import math

from gemini_model.model_abstract import StaticModel

R_GAS = 8.314462618  # molar gas constant, J/mol/K; source: NIST CODATA 2018, exact
V_M = R_GAS * 273.15 / 101325.0  # molar volume of an ideal gas at 0 C and 1 atm, m3/mol
M_CO2 = 44.0095e-3  # CO2 molar mass, kg/mol; source: NIST WebBook C124389
M_NACL = 58.44e-3  # NaCl molar mass, kg/mol; source: NIST WebBook
LHV_CH4 = (890.7 - 2 * (285.830 - 241.826)) * 1e3  # methane lower heating value, J/mol; NIST C74828


class HenryGasBubblePoint(StaticModel):
    """Compute the bubble point by Henry's law with methane salting-out; not a PVT model."""

    def __init__(self):
        """Set the defaults: GLR 0.8 Nm3/m3, 80/20 methane/CO2, pure water, Sander (2023) fits."""
        super().__init__()
        self.parameters = {
            "GLR": 0.8,  # gas-liquid ratio, Nm3 per m3 brine
            "methane_fraction": 0.8,  # mole fraction of methane in the gas
            "co2_fraction": 0.2,  # mole fraction of CO2 in the gas
            "nacl_concentration": 0.0,  # NaCl in the brine, g/L; 0 is pure water
            "salting_out_coefficient": 0.319,  # methane Setschenow coefficient, kg/mol; Sun 2024
            "salting_out_convention": "ln",  # "ln": factor exp(k m); "log10": factor 10^(k m)
            "henry_method": "fits",  # "fits": mean of the fits below; "vant_hoff": pair below
            # H = exp(A + B/T + C ln T), mol/(m3 Pa); measured fits from henrys-law.org
            "henry_fits": {
                "CH4": [
                    (-133.87698, 6629.95765, 17.62619),
                    (-206.41149, 10058.76380, 28.34414),
                    (-201.05778, 9920.37989, 27.48020),
                    (-195.92029, 9624.35229, 26.74970),
                    (-203.15923, 9951.76163, 27.82682),
                    (-185.72813, 9197.97398, 25.21142),
                ],
                "CO2": [
                    (-144.44445, 8071.06256, 19.20040),
                    (-167.86796, 9146.18176, 22.67310),
                    (-126.83006, 7302.88057, 16.55553),
                    (-140.70031, 7951.74051, 18.60965),
                    (-138.54127, 7859.16691, 18.28487),
                ],
            },
            # H at 298.15 K in mol/(m3 Pa) and its temperature slope in K; henrys-law.org
            "henry_vant_hoff": {"CH4": (1.4e-5, 1600.0), "CO2": (3.4e-4, 2300.0)},
        }

    def henry_constant(self, gas, temperature):
        """Henry solubility of "CH4" or "CO2" at temperature (K), mol/(m3 Pa)."""
        if self.parameters["henry_method"] == "vant_hoff":
            h_ref, slope = self.parameters["henry_vant_hoff"][gas]
            return h_ref * math.exp(slope * (1 / temperature - 1 / 298.15))
        fits = self.parameters["henry_fits"][gas]
        return sum(
            math.exp(a + b / temperature + c * math.log(temperature)) for a, b, c in fits
        ) / len(fits)

    def salting_out_factor(self):
        """Factor by which the salt raises the methane partial pressure."""
        p = self.parameters
        km = p["salting_out_coefficient"] * p["nacl_concentration"] / 1000 / M_NACL
        if p["salting_out_convention"] == "log10":
            return 10**km
        return math.exp(km)

    def calculate_output(self, u, x=None):
        """Bubble point from u["temperature"] (K); gas rates if u has "flowrate" (m3/s)."""
        p = self.parameters
        temperature = u["temperature"]
        c_ch4 = p["GLR"] * p["methane_fraction"] / V_M  # mol/m3
        c_co2 = p["GLR"] * p["co2_fraction"] / V_M  # mol/m3

        p_ch4 = self.salting_out_factor() * c_ch4 / self.henry_constant("CH4", temperature)
        p_co2 = c_co2 / self.henry_constant("CO2", temperature)

        self.output = {
            "bubble_point_pressure": p_ch4 + p_co2,
            "methane_concentration": c_ch4,
            "co2_concentration": c_co2,
        }

        flowrate = u.get("flowrate")
        if flowrate is not None:
            gas = p["GLR"] * flowrate  # Nm3/s
            self.output["gas_flowrate"] = gas
            self.output["methane_power"] = gas * p["methane_fraction"] / V_M * LHV_CH4
            self.output["co2_mass_flow"] = gas * p["co2_fraction"] / V_M * M_CO2
