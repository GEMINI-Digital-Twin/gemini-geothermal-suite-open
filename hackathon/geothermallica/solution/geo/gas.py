"""Gas dissolved in the brine: rates, fuel power and CO2 per doublet, a Henry's-law bubble point, and five ways to handle the gas.

Henry's-law constants: Sander 2023, Atmos. Chem. Phys. 23, 10901, https://www.henrys-law.org . Parameter sources are in the inline comments.
gas_at() returns gas rates (Nm3/h), methane fuel power (MW), CO2 (kg/h) and bubble points (bar); handling_options() returns one dict
per handling option (vent, flare, engine, boiler, reinject) with CO2 per year, energy credit or duty, and a note. Run: python -m geo.gas
"""
import math

import numpy as np

from geo.common import DEPTH_M, RHO, t_reservoir_c

GLR = 0.8                      # gas-liquid ratio (GLR), Nm3 gas per m3 brine (Nm3 = normal cubic metre at 0 C, 1.01325 bar); challenge brief
Y_CH4, Y_CO2 = 0.80, 0.20      # mole fractions of methane and CO2 in the gas; from the challenge brief
M_CO2 = 44.0095e-3             # CO2 molar mass, kg/mol; source: NIST Chemistry WebBook, entry C124389
M_CH4 = 16.0425e-3             # methane molar mass, kg/mol; source: NIST Chemistry WebBook, entry C74828
R_GAS = 8.314462618            # molar gas constant, J/(mol K), exact; source: NIST CODATA, https://physics.nist.gov/cgi-bin/cuu/Value?r
V_M = R_GAS * 273.15 / 101325.0   # ideal-gas molar volume at 0 C and 1.01325 bar, m3/mol (22.414 L/mol)
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
OPERATING_DAYS = 330           # days a doublet runs per year; from the challenge brief
# global warming potential over 100 years (GWP100) of fossil methane, kg CO2-equivalent per kg; source: GHG Protocol, IPCC Global
# Warming Potential Values, August 2024, AR6 column (IPCC Sixth Assessment Report, WG1 7.6.1.1), the value for "methane emissions
# from fossil fuel fugitive emission sources",
# https://ghgprotocol.org/sites/default/files/2024-08/Global-Warming-Potential-Values%20%28August%202024%29.pdf
GWP100_CH4_FOSSIL = 29.8
# electrical share of the fuel power in a gas engine with heat recovery, a combined heat and power (CHP) unit; source: GEMINI,
# CHP.ELECTRICAL_POWER_FRACTION in src/gemini_model/chp/chp.py (development branch, commit d86e8bb)
CHP_EL_SHARE = 1 / 3
CHP_TOTAL_EFF = 0.90           # CHP electricity plus recovered heat per unit of fuel power on LHV; assumed, no source
P_SEPARATOR_BAR = 10.0         # pressure of the degasser that releases the gas at the surface, bar; assumed, no source
# default handling: the engine burns the methane, so it emits the same CO2 as a flare, and its electricity covers the pumps' load;
# the organisers allow any option (organiser answer on Discord, 3 Nov 2026)
GAS_HANDLING = "engine"
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


def compression_kWh_per_Nm3(p_from_bar, p_to_bar, t_c):
    """Isothermal compression work of one Nm3 of ideal gas from p_from_bar to p_to_bar at t_c, kWh."""
    return R_GAS * (t_c + 273.15) * math.log(p_to_bar / p_from_bar) / V_M / 3.6e6


def handling_options(q_m3h, depth_m=DEPTH_M, days=OPERATING_DAYS, esp_kW=None, p_inj_wh_bar=None, t_inj_c=None):
    """One dict per gas handling option at q_m3h over days: CO2 and CO2-equivalent t/yr, energy credit or duty MWh/yr, a note."""
    from geo.cost import BOILER_EFF                          # imported here: cost imports this module through year
    if p_inj_wh_bar is None or t_inj_c is None:
        from geo import year
        rows = year.injector_rows(depth_m)
        p_inj_wh_bar = float(np.interp(q_m3h, year.Q_INJ, [r["p_wh_bar"] for r in rows])) if p_inj_wh_bar is None else p_inj_wh_bar
        t_inj_c = float(np.interp(q_m3h, year.Q_INJ, [r["T_inj_C"] for r in rows])) if t_inj_c is None else t_inj_c
    g, hours = gas_at(q_m3h, depth_m), days * 24
    co2_gas = g["CO2_in_gas_kg_h"] * hours / 1000                          # t/yr
    co2_burn = g["CH4_Nm3h"] / V_M * M_CO2 * hours / 1000                  # one mol CO2 per mol CH4 burned, t/yr
    ch4 = g["CH4_Nm3h"] / V_M * M_CH4 * hours / 1000                       # t/yr
    lhv = g["CH4_MW_LHV"] * hours                                          # MWh/yr
    burned = co2_gas + co2_burn
    kwh = compression_kWh_per_Nm3(P_SEPARATOR_BAR, p_inj_wh_bar, t_inj_c)
    row = lambda name, co2, co2e=None, el=0.0, heat=0.0, duty=0.0, note="": {
        "option": name, "CO2_t_per_yr": co2, "CO2e_t_per_yr": co2 if co2e is None else co2e, "electricity_MWh_per_yr": el,
        "heat_MWh_per_yr": heat, "compression_MWh_per_yr": duty, "note": note}
    opts = [row("vent", co2_gas, co2_gas + GWP100_CH4_FOSSIL * ch4,
                note=f"degasser, CH4 and CO2 to air: {ch4:.0f} t CH4/yr x GWP100 {GWP100_CH4_FOSSIL} (fossil, AR6)"),
            row("flare", burned, note="degasser and flare: CH4 burned to CO2, no energy recovered"),
            row("engine", burned, el=CHP_EL_SHARE * lhv, heat=(CHP_TOTAL_EFF - CHP_EL_SHARE) * lhv,
                note=f"degasser and gas engine (CHP): electricity {CHP_EL_SHARE:.3f} and heat {CHP_TOTAL_EFF - CHP_EL_SHARE:.3f} of LHV, "
                     "derating on a 20 % CO2 gas not modelled"),
            row("boiler", burned, heat=BOILER_EFF * lhv, note=f"degasser and the site boiler: heat {BOILER_EFF} of LHV"),
            row("reinject", 0.0, duty=kwh * g["gas_Nm3h"] * hours / 1000,
                note=f"isothermal compression {P_SEPARATOR_BAR:g} -> {p_inj_wh_bar:.1f} bar at {t_inj_c:.1f} C, {kwh:.4f} kWh/Nm3: "
                     "a lower bound; reinjecting CH4-rich gas needs a permit (assumed)")]
    if esp_kW is not None:
        esp = esp_kW * hours / 1000
        for o in opts:
            o["esp_MWh_per_yr"] = esp
        opts[2]["note"] += f"; covers {100 * opts[2]['electricity_MWh_per_yr'] / esp:.0f} % of the ESP's {esp:.0f} MWh/yr"
    return opts


def handling(q_m3h, depth_m=DEPTH_M, days=OPERATING_DAYS, option=GAS_HANDLING, **kw):
    """The dict of one handling option (default GAS_HANDLING) from handling_options()."""
    return next(o for o in handling_options(q_m3h, depth_m, days, **kw) if o["option"] == option)


if __name__ == "__main__":
    for k, v in gas_at(300.0).items():
        print(f"{k}: {v:.4g}")
    print(f"\nhandling options, one doublet at 300 m3/h, {OPERATING_DAYS} days (default {GAS_HANDLING}):")
    for o in handling_options(300.0):
        print(f"{o['option']:9s} CO2 {o['CO2_t_per_yr']:7.0f} t/yr  CO2e {o['CO2e_t_per_yr']:7.0f} t/yr  el {o['electricity_MWh_per_yr']:6.0f} MWh  "
              f"heat {o['heat_MWh_per_yr']:6.0f} MWh  compression {o['compression_MWh_per_yr']:5.0f} MWh  {o['note']}")
