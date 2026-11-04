"""Gas dissolved in the brine: rates, fuel power and CO2 per doublet, and a Henry's-law bubble point for the pump intake.

Henry's-law constants: Sander 2023, Atmos. Chem. Phys. 23, 10901, compilation at https://www.henrys-law.org .
Parameter sources are in the inline comments.
gas_at() returns a dict of gas rates (Nm3/h), methane fuel power (MW), CO2 mass flow (kg/h) and bubble-point pressures (bar).
Run: python -m geo.gas
"""
import math

from geo.common import DEPTH_M, RHO, t_reservoir_c

GLR = 0.8                      # gas-liquid ratio (GLR), Nm3 gas per m3 brine (Nm3 = normal cubic metre at 0 C, 1.01325 bar); challenge brief
Y_CH4, Y_CO2 = 0.80, 0.20      # mole fractions of methane and CO2 in the gas; from the challenge brief
V_M = 8.314462618 * 273.15 / 101325.0   # ideal-gas molar volume at 0 C and 1.01325 bar, m3/mol (22.414 L/mol)
M_CO2 = 44.0095e-3             # CO2 molar mass, kg/mol; source: NIST Chemistry WebBook, entry C124389
# methane lower calorific value (LHV), kJ/mol: NIST gross value 890.7 (WebBook entry C74828,
# https://webbook.nist.gov/cgi/cbook.cgi?ID=C74828&Mask=1) minus 2 x the latent heat of water (WebBook entry C7732185)
LHV_CH4 = 890.7 - 2 * (285.830 - 241.826)
SALT_G_L, M_NACL = 45.0, 58.44e-3      # NaCl in the brine, g/L (assumed, matches the 1 030 kg/m3 density); NaCl molar mass, kg/mol
# methane salting-out (Setschenow) constant, kg/mol; source: Sun et al. 2024, J. Chem. Eng. Data, PubMed Central PMC11472311
K_SALT_CH4 = 0.319
# Henry constants: Sander 2023, Atmos. Chem. Phys. 23, 10901, https://www.henrys-law.org
# H^cp at 298.15 K in mol/(m3 Pa) and its temperature slope dlnH/d(1/T) in K; values from Burkholder et al. 2019 on those pages
VANT_HOFF = {"CH4": (1.4e-5, 1600.0), "CO2": (3.4e-4, 2300.0)}
# H^cp = exp(A + B/T + C ln T): six CH4 and five CO2 measured fits from the same pages
FITS = {"CH4": [(-133.87698, 6629.95765, 17.62619), (-206.41149, 10058.76380, 28.34414), (-201.05778, 9920.37989, 27.48020),
                (-195.92029, 9624.35229, 26.74970), (-203.15923, 9951.76163, 27.82682), (-185.72813, 9197.97398, 25.21142)],
        "CO2": [(-144.44445, 8071.06256, 19.20040), (-167.86796, 9146.18176, 22.67310), (-126.83006, 7302.88057, 16.55553),
                (-140.70031, 7951.74051, 18.60965), (-138.54127, 7859.16691, 18.28487)]}
BASIS = ("GLR 0.8 Nm3/m3, 80/20 CH4/CO2 [D]; 22.414 L/mol ideal [C]; CH4 LHV 802.7 kJ/mol = NIST 890.7 - 2 x 44.0 [L, C]; bubble point "
         "= Henry's law at reservoir T (Sander compilation, henrys-law.org): central = mean of 6 CH4 / 5 CO2 measured fits, "
         "upper = van 't Hoff from 298 K; CH4 salted out by exp(0.319 x 0.77) = 1.28 (ln reading) or 1.76 (log10 reading) [L, A, TBC]; "
         "not a PVT model")


def conc_mol_m3(gas):
    """Dissolved CH4 or CO2, mol per m3 of brine."""
    return GLR * (Y_CH4 if gas == "CH4" else Y_CO2) / V_M


def henry_cp(gas, t_c, method="fits"):
    """Henry solubility H^cp at t_c, mol/(m3 Pa): mean of the measured fits, or van 't Hoff from 298.15 K."""
    t = t_c + 273.15
    if method == "vant_hoff":
        h, b = VANT_HOFF[gas]
        return h * math.exp(b * (1 / t - 1 / 298.15))
    fits = FITS[gas]
    return sum(math.exp(a + b / t + c * math.log(t)) for a, b, c in fits) / len(fits)


def salting_factor(convention="ln"):
    """Factor by which 45 g/L NaCl raises the CH4 bubble point: exp(k m) or 10^(k m); the paper's log base is unconfirmed."""
    km = K_SALT_CH4 * SALT_G_L / 1000 / M_NACL
    return 10 ** km if convention == "log10" else math.exp(km)


def p_bubble_bar(depth_m=DEPTH_M, method="fits", salt="ln"):
    """Bubble point, bar: pressure at which the brine just holds its CH4 and CO2 at reservoir temperature; salt None, "ln" or "log10"."""
    t = t_reservoir_c(depth_m)
    f = {"CH4": salting_factor(salt) if salt else 1.0, "CO2": 1.0}
    return sum(f[g] * conc_mol_m3(g) / henry_cp(g, t, method) for g in ("CH4", "CO2")) / 1e5


def gas_at(q_m3h, depth_m=DEPTH_M):
    """Dict of gas rates, methane fuel power (MW on LHV), CO2 mass flow and bubble points for one doublet at q_m3h."""
    gas = GLR * q_m3h
    ch4, co2 = Y_CH4 * gas, Y_CO2 * gas
    return {"q_m3h": q_m3h, "gas_Nm3h": gas, "CH4_Nm3h": ch4, "CO2_Nm3h": co2,
            "CH4_mol_per_kg": conc_mol_m3("CH4") / RHO, "CO2_mol_per_kg": conc_mol_m3("CO2") / RHO,
            "CH4_MW_LHV": ch4 / V_M * LHV_CH4 / 3600 / 1000, "CO2_in_gas_kg_h": co2 / V_M * M_CO2,
            "T_reservoir_C": t_reservoir_c(depth_m), "p_bubble_bar": p_bubble_bar(depth_m),
            "p_bubble_pure_water_bar": p_bubble_bar(depth_m, salt=None),
            "p_bubble_log10_reading_bar": p_bubble_bar(depth_m, salt="log10"), "p_bubble_upper_bar": p_bubble_bar(depth_m, "vant_hoff")}


if __name__ == "__main__":
    for k, v in gas_at(300.0).items():
        print(f"{k}: {v:.4g}")
