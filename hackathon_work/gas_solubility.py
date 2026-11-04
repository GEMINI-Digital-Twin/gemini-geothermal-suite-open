"""Can the reinjected gas dissolve in the injected brine? (check on the gas-handling options)

Method (DERIVED, each piece cited):
  - Henry's constant of CO2 and CH4 in pure water, mole-fraction basis, 0-360 C:
    IAPWS G7-04 (2004) / Fernandez-Prini, Alvarez & Harvey, J. Phys. Chem. Ref. Data 32 (2003) 903,
    ln(kH / p_sat) = A/Tr + B tau^0.355 / Tr + C Tr^-0.41 exp(tau), Tr = T/647.096 K, tau = 1 - Tr.
  - Water vapour pressure: Wagner & Pruss, J. Phys. Chem. Ref. Data 31 (2002) 387 (IAPWS-95 sat. line).
  - Pressure correction of kH (Krichevsky-Kasarnovsky / Poynting): kH(P) = kH(p_sat) exp(v_inf (P - p_sat) / RT),
    partial molar volumes at infinite dilution ASSUMED 35 cm3/mol (CO2) and 37 cm3/mol (CH4).
  - Salting-out: Weisenberger & Schumpe, AIChE J. 42 (1996) 298, log10(c0/c) = sum_i (h_i + h_G) c_i,
    h_G = h_G0 + h_T (T - 298.15) (fitted 273-363 K for CO2/CH4; extrapolated above).
  - Gas-phase fugacity: Peng-Robinson (1976) for CO2-CH4(-free water), k_ij = 0.09 (ASSUMED, typical fit);
    water vapour by Raoult (y_w = p_sat / P).
  - Salinity from the OFFICIAL density 1030 kg/m3 read as NaCl at 20 C (DERIVED, 4.45 wt% = 0.80 mol/kg);
    conservative bound: 1030 kg/m3 at reservoir temperature (ASSUMED reading, ~2.0 mol/kg). The check uses the
    conservative bound.

Margin = factor by which the reinjected gas per m3 of brine could grow before the bubble point reaches the
available pressure (margin >= 1: all gas dissolves). Evaluated at the injector wellhead (lowest pressure on the
injection path; hottest injection day) and at reservoir conditions. Where the wellhead margin is < 1, the gas
must be co-injected through a dip tube below the depth where hydrostatic pressure reaches the bubble point.
"""

from __future__ import annotations

import math

from scipy.optimize import brentq

R = 8.314462618
T_C_WATER, P_C_WATER = 647.096, 220.64  # K, bar
NM3_PER_MOL = 0.022414                   # DERIVED (0 C, 1.01325 bar)
M_NACL = 0.058443                        # kg/mol
P_ATM_BAR = 1.01325

IAPWS_G704 = {"CO2": (-8.55445, 4.01195, 9.52345), "CH4": (-10.44708, 4.66491, 12.12986)}
V_INF_M3_MOL = {"CO2": 35e-6, "CH4": 37e-6}                       # ASSUMED
WS_GAS = {"CO2": (-0.0172, -0.338e-3), "CH4": (0.0022, -0.524e-3)}  # (h_G0, h_T) m3/kmol
WS_ION = {"Na+": 0.1143, "Cl-": 0.0318}                             # m3/kmol
PR = {"CO2": (304.13, 73.77, 0.224), "CH4": (190.56, 45.99, 0.011)}  # Tc K, Pc bar, omega
K_IJ = 0.09                                                          # ASSUMED CO2-CH4


def p_sat_bar(t_k: float) -> float:
    tau = 1 - t_k / T_C_WATER
    a = (-7.85951783, 1.84408259, -11.7866497, 22.6807411, -15.9618719, 1.80122502)
    e = (1, 1.5, 3, 3.5, 4, 7.5)
    return P_C_WATER * math.exp(T_C_WATER / t_k * sum(ai * tau ** ei for ai, ei in zip(a, e)))


def henry_bar(gas: str, t_k: float, p_bar: float) -> float:
    """kH = f / x in bar at T and P (pure water)."""
    a, b, c = IAPWS_G704[gas]
    tr = t_k / T_C_WATER
    tau = 1 - tr
    ps = p_sat_bar(t_k)
    k_sat = ps * math.exp(a / tr + b * tau ** 0.355 / tr + c * tr ** -0.41 * math.exp(tau))
    return k_sat * math.exp(V_INF_M3_MOL[gas] * (p_bar - ps) * 1e5 / (R * t_k))


def salting_out_factor(gas: str, t_k: float, nacl_mol_per_l: float) -> float:
    """c0 / c (>= 1): pure-water solubility over brine solubility."""
    h0, ht = WS_GAS[gas]
    h_g = h0 + ht * (t_k - 298.15)
    return 10 ** (sum((h + h_g) * nacl_mol_per_l for h in WS_ION.values()))


def pr_fugacity_coefficients(y: dict, t_k: float, p_bar: float) -> dict:
    """Peng-Robinson fugacity coefficients of the gas phase (vapour root)."""
    names = list(y)
    ai, bi = {}, {}
    for n in names:
        tc, pc, w = PR[n]
        kappa = 0.37464 + 1.54226 * w - 0.26992 * w ** 2
        alpha = (1 + kappa * (1 - math.sqrt(t_k / tc))) ** 2
        ai[n] = 0.45724 * R ** 2 * tc ** 2 / (pc * 1e5) * alpha
        bi[n] = 0.07780 * R * tc / (pc * 1e5)
    aij = {(i, j): math.sqrt(ai[i] * ai[j]) * (1 - (K_IJ if i != j else 0.0)) for i in names for j in names}
    a = sum(y[i] * y[j] * aij[i, j] for i in names for j in names)
    b = sum(y[i] * bi[i] for i in names)
    p = p_bar * 1e5
    A, B = a * p / (R * t_k) ** 2, b * p / (R * t_k)
    # Z^3 - (1-B) Z^2 + (A - 3B^2 - 2B) Z - (AB - B^2 - B^3) = 0, largest real root
    c2, c1, c0 = -(1 - B), A - 3 * B ** 2 - 2 * B, -(A * B - B ** 2 - B ** 3)
    z = max(1.0, B + 1e-9)
    for _ in range(100):
        f = z ** 3 + c2 * z ** 2 + c1 * z + c0
        z_new = z - f / (3 * z ** 2 + 2 * c2 * z + c1)
        if abs(z_new - z) < 1e-12:
            break
        z = z_new
    s2 = math.sqrt(2)
    phi = {}
    for i in names:
        sum_a = sum(y[j] * aij[i, j] for j in names)
        ln_phi = (bi[i] / b * (z - 1) - math.log(z - B)
                  - A / (2 * s2 * B) * (2 * sum_a / a - bi[i] / b) * math.log((z + (1 + s2) * B) / (z + (1 - s2) * B)))
        phi[i] = math.exp(ln_phi)
    return phi


def _residual(molality: dict, t_k: float, p_bar: float, nacl_mol_kg: float, nacl_mol_l: float) -> float:
    """sum(y) - 1 of the gas phase in equilibrium with the brine at p_bar; > 0 means a gas phase forms."""
    n_water = 1 / 0.018015
    x = {g: m / (n_water + 2 * nacl_mol_kg + sum(molality.values())) for g, m in molality.items()}
    f = {g: henry_bar(g, t_k, p_bar) * salting_out_factor(g, t_k, nacl_mol_l) * x[g] for g in x}
    y = {g: f[g] / p_bar for g in f}
    for _ in range(50):  # successive substitution on the PR fugacity coefficients
        s = sum(y.values())
        phi = pr_fugacity_coefficients({g: v / s for g, v in y.items()}, t_k, p_bar)
        y_new = {g: f[g] / (phi[g] * p_bar) for g in f}
        if max(abs(y_new[g] - y[g]) for g in y) < 1e-12:
            break
        y = y_new
    return sum(y.values()) + p_sat_bar(t_k) / p_bar - 1


def bubble_point_bar(molality: dict, t_k: float, nacl_mol_kg: float, nacl_mol_l: float) -> float:
    """Pressure (bar abs) at which brine holding ``molality`` (mol/kg water) of each gas first releases a gas phase."""
    lo = p_sat_bar(t_k) * 1.0001 + 1e-6
    hi = max(2 * lo, 10.0)
    while _residual(molality, t_k, hi, nacl_mol_kg, nacl_mol_l) > 0:
        lo, hi = hi, hi * 2
    return brentq(lambda p: _residual(molality, t_k, p, nacl_mol_kg, nacl_mol_l), lo, hi)


def margin(molality: dict, t_k: float, p_bar: float, nacl_mol_kg: float, nacl_mol_l: float) -> float:
    """Multiplier s with bubble_point(s * molality) = p_bar (bar abs): the brine's capacity over the gas it must hold."""
    def g(s):
        return _residual({k: s * m for k, m in molality.items()}, t_k, p_bar, nacl_mol_kg, nacl_mol_l)
    hi = 1.0
    while g(hi) < 0:
        hi *= 2
    return brentq(g, 1e-9, hi)


def nacl_from_density(rho_kg_m3: float, t_c: float) -> tuple[float, float]:
    """(mol/kg water, mol/L) NaCl that gives ``rho`` at t_c. Linear NaCl-density slope 7.15 kg/m3 per wt%
    (DERIVED from 4 wt% = 1026.8 kg/m3 at 20 C, CRC Handbook), pure-water density from the Kell (1975) fit."""
    t = t_c
    rho_w = ((((-2.8054253e-10 * t + 1.0556302e-7) * t - 4.6170461e-5) * t - 7.9870401e-3) * t + 16.945176) * t + 999.83952
    rho_w /= 1 + 16.879850e-3 * t
    wt = max(0.0, (rho_kg_m3 - rho_w) / 7.15)
    m = wt * 10 / (M_NACL * 1000 * (1 - wt / 100))
    return m, wt * 10 * rho_kg_m3 / 1000 / (M_NACL * 1000)


def dissolution_check(mode: str, x_ch4: float, glr_nm3_m3: float, rho: float, wellhead: dict, reservoir: dict,
                      reservoir_depth_m: float, compression_kwh_per_kg: float) -> dict:
    """Wellhead and reservoir dissolution margins for co2_reinject (CO2 only) or reinject_all (CO2 + CH4).

    wellhead / reservoir: {"p_bar_g", "t_c"}; returns the margins and a PASS/FAIL row for the annual checks."""
    gases = {"co2_reinject": {"CO2": 1 - x_ch4}, "reinject_all": {"CO2": 1 - x_ch4, "CH4": x_ch4}}[mode]
    bounds = {"surface": nacl_from_density(rho, 20.0), "reservoir": nacl_from_density(rho, reservoir["t_c"])}
    out = {"mode": mode, "method": "IAPWS G7-04 Henry + Poynting, Weisenberger-Schumpe salting-out, Peng-Robinson gas phase",
           "gas_Nm3_per_m3_brine": {g: glr_nm3_m3 * f for g, f in gases.items()}, "salinity": {}, "points": {}}
    for label, (m_kg, m_l) in bounds.items():
        water_kg = rho / (1 + m_kg * M_NACL)  # per m3 brine
        molality = {g: glr_nm3_m3 * f / NM3_PER_MOL / water_kg for g, f in gases.items()}
        out["salinity"][label] = {"NaCl_mol_per_kg": m_kg, "dissolved_mol_per_kg_water": molality}
        for where, cond in (("wellhead", wellhead), ("reservoir", reservoir)):
            t_k, p_abs = cond["t_c"] + 273.15, cond["p_bar_g"] + P_ATM_BAR
            out["points"][f"{where}@{label}"] = {
                "p_bar_g": cond["p_bar_g"], "t_c": cond["t_c"],
                "bubble_point_bar_g": bubble_point_bar(molality, t_k, m_kg, m_l) - P_ATM_BAR,
                "margin": margin(molality, t_k, p_abs, m_kg, m_l)}
    wh, res = out["points"]["wellhead@reservoir"], out["points"]["reservoir@reservoir"]
    # Gas dissolves on the way down once P_wh + rho g z >= bubble point (friction neglected, small at these rates).
    dip_m = max(0.0, (wh["bubble_point_bar_g"] - wh["p_bar_g"]) * 1e5 / (rho * 9.81))
    out["dip_tube_depth_m"] = dip_m
    mw = sum(f * {"CO2": 44.01, "CH4": 16.04}[g] for g, f in gases.items()) / sum(gases.values()) / 1000
    p_to = max(wh["bubble_point_bar_g"], wh["p_bar_g"]) + P_ATM_BAR
    # DERIVED minimum: isothermal ideal-gas compression from 1 atm to the injection pressure at 40 C, /0.7 (ASSUMED eff.)
    out["compression_kWh_per_kg_derived"] = R * 313.15 * math.log(p_to / P_ATM_BAR) / mw / 0.7 / 3.6e6
    out["compression_kWh_per_kg_assumed"] = compression_kwh_per_kg
    ok = res["margin"] >= 1 and dip_m < reservoir_depth_m
    how = (f"dissolves at the wellhead (margin {wh['margin']:.2f})" if wh["margin"] >= 1 else
           f"wellhead margin {wh['margin']:.2f} < 1: co-inject through a dip tube reaching >= {dip_m:.0f} m (bubble point {wh['bubble_point_bar_g']:.1f} bar(g))")
    if out["compression_kWh_per_kg_derived"] > compression_kwh_per_kg:
        how += (f"; ASSUMED compression {compression_kwh_per_kg:g} kWh/kg is below the DERIVED minimum "
                f"{out['compression_kWh_per_kg_derived']:.3f} kWh/kg to {p_to - P_ATM_BAR:.0f} bar(g)")
    out["check"] = {"check": "gas_dissolution", "scope": "injector_well", "status": "PASS" if ok else "FAIL",
                    "value": res["margin"], "limit": ">= 1 at reservoir conditions; dip-tube depth < well depth",
                    "reason": f"{'+'.join(gases)} {sum(out['gas_Nm3_per_m3_brine'].values()):.2f} Nm3/m3: {how}; "
                              f"reservoir margin {res['margin']:.1f} (conservative salinity {bounds['reservoir'][0]:.2f} mol/kg)"}
    return out
