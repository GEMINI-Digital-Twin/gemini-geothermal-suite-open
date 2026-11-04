"""Bubble point and gas rates of a brine carrying dissolved methane and CO2 (Henry's law).

Each gas sits in the brine at the concentration set by the gas-liquid ratio (GLR) and its mole
fraction. The bubble point is the pressure at which the brine just holds both gases at the given
temperature, the sum of the Henry partial pressures:

    c_i = GLR y_i / V_m                         (mol/m3)
    p_b = sum_i f_i c_i / H_i(T)                (Pa)

with H^cp in mol/(m3 Pa) and f_i the salting-out factor (1 for CO2 here). Methane is salted out by
NaCl with a Setschenow factor f = exp(k m) ("ln") or 10^(k m) ("log10"), m the NaCl molality
approximated as (g/L) / 1000 / M_NaCl.

Sources: Henry constants from Sander, R. (2023) Atmos. Chem. Phys. 23, 10901-12440,
https://www.henrys-law.org (methane 74-82-8, CO2 124-38-9); methane salting-out coefficient from
Sun et al. (2024) J. Chem. Eng. Data, https://pmc.ncbi.nlm.nih.gov/articles/PMC11472311/;
molar masses and heats of combustion and of vaporisation from the NIST Chemistry WebBook,
https://webbook.nist.gov (C74828, C124389, C7732185).
"""

import math

from gemini_model.model_abstract import StaticModel

R_GAS = 8.314462618  # molar gas constant (J/mol/K)
V_M = R_GAS * 273.15 / 101325.0  # ideal-gas molar volume at 0 C, 1.01325 bar (m3/mol)
M_CO2 = 44.0095e-3  # CO2 molar mass (kg/mol)
M_NACL = 58.44e-3  # NaCl molar mass (kg/mol)
LHV_CH4 = (890.7 - 2 * (285.830 - 241.826)) * 1e3  # methane LHV: gross minus 2 H2O latent (J/mol)


class HenryGasBubblePoint(StaticModel):
    """Bubble point, dissolved CH4/CO2 and gas rates of a gas-bearing brine by Henry's law.

    This is Henry's law in pure water with a Setschenow salting-out correction for methane, not a
    PVT model: no gas-phase non-ideality, no CO2 salting-out, no pressure effect on the Henry
    constants. The sources of the Henry fits do not state a validity range.

    Parameters: GLR (Nm3/m3), methane_fraction (-), co2_fraction (-), nacl_concentration (g/L),
    salting_out_coefficient (kg/mol), salting_out_convention ("ln" or "log10"), henry_method
    ("fits": mean of the measured fits, or "vant_hoff": van 't Hoff from 298.15 K), henry_fits,
    henry_vant_hoff.
    Inputs (u): temperature (K), flowrate (m3/s, optional).
    Outputs: bubble_point_pressure (Pa), methane_concentration and co2_concentration (mol/m3);
    with flowrate also gas_flowrate (Nm3/s), methane_power (W, LHV) and co2_mass_flow (kg/s).
    """

    def __init__(self):
        """Initialize with GLR 0.8 Nm3/m3, 80/20 CH4/CO2, pure water and the Sander (2023) fits."""
        super().__init__()
        self.parameters = {
            "GLR": 0.8,  # gas-liquid ratio (Nm3/m3)
            "methane_fraction": 0.8,  # mole fraction in the gas (-)
            "co2_fraction": 0.2,  # mole fraction in the gas (-)
            "nacl_concentration": 0.0,  # NaCl in the brine (g/L), 0 is pure water
            "salting_out_coefficient": 0.319,  # methane Setschenow coefficient (kg/mol)
            "salting_out_convention": "ln",  # "ln": exp(k m), "log10": 10^(k m)
            "henry_method": "fits",  # "fits" or "vant_hoff"
            # H^cp = exp(A + B/T + C ln T) in mol/(m3 Pa), measured fits from henrys-law.org
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
            # H^cp at 298.15 K in mol/(m3 Pa) and dlnH/d(1/T) in K, henrys-law.org
            "henry_vant_hoff": {"CH4": (1.4e-5, 1600.0), "CO2": (3.4e-4, 2300.0)},
        }

    def henry_constant(self, gas, temperature):
        """Henry solubility H^cp (mol/m3/Pa) of gas "CH4" or "CO2" at temperature (K)."""
        if self.parameters["henry_method"] == "vant_hoff":
            h_ref, slope = self.parameters["henry_vant_hoff"][gas]
            return h_ref * math.exp(slope * (1 / temperature - 1 / 298.15))
        fits = self.parameters["henry_fits"][gas]
        return sum(
            math.exp(a + b / temperature + c * math.log(temperature)) for a, b, c in fits
        ) / len(fits)

    def salting_out_factor(self):
        """Factor (-) by which the NaCl raises the methane partial pressure."""
        p = self.parameters
        km = p["salting_out_coefficient"] * p["nacl_concentration"] / 1000 / M_NACL
        if p["salting_out_convention"] == "log10":
            return 10**km
        return math.exp(km)

    def calculate_output(self, u, x=None):
        """Calculate the bubble point and, if u has a flowrate, the gas rates."""
        p = self.parameters
        temperature = u["temperature"]  # K
        c_ch4 = p["GLR"] * p["methane_fraction"] / V_M  # mol/m3
        c_co2 = p["GLR"] * p["co2_fraction"] / V_M  # mol/m3

        p_ch4 = self.salting_out_factor() * c_ch4 / self.henry_constant("CH4", temperature)  # Pa
        p_co2 = c_co2 / self.henry_constant("CO2", temperature)  # Pa

        self.output = {
            "bubble_point_pressure": p_ch4 + p_co2,
            "methane_concentration": c_ch4,
            "co2_concentration": c_co2,
        }

        flowrate = u.get("flowrate")  # m3/s
        if flowrate is not None:
            gas = p["GLR"] * flowrate  # Nm3/s
            self.output["gas_flowrate"] = gas
            self.output["methane_power"] = gas * p["methane_fraction"] / V_M * LHV_CH4  # W
            self.output["co2_mass_flow"] = gas * p["co2_fraction"] / V_M * M_CO2  # kg/s
