"""Bubble point of the associated gas dissolved in the brine.

The brief gives the gas as a gas-liquid ratio (Nm3 of gas per m3 of brine)
with its CH4/CO2 split. That gas is dissolved at reservoir pressure and
comes out of solution once the flowing pressure drops below the bubble
point. An ESP must not see free gas at its intake (gas interference and
gas lock), so the bubble point sets how deep the pump has to hang.

Method: Henry's law with the IAPWS G7-04 (2004) Henry's constants of CH4
and CO2 in water (Fernandez-Prini, Alvarez and Harvey, 2003), the
Wagner-Pruss water vapour pressure, and a Setschenow salting-out
correction for the brine's NaCl-equivalent salinity. Ideal-gas partial
pressures are used, which is within a few percent at 30-50 bar and
100 degC. It is an estimate: a measured bubble point from a PVT sample
should replace it.
"""

import math

from gemini_design.challenge import ASSUMPTIONS, CELSIUS_TO_KELVIN, CHALLENGE

_NORMAL_MOLAR_VOLUME = 22.414e-3  # Nm3/mol
_MOL_WATER_PER_KG = 55.508
_T_CRIT_K = 647.096
_P_CRIT_MPA = 22.064

# IAPWS G7-04, Table 2: ln(kH / p1*) = A/Tr + B tau^0.355 / Tr + C Tr^-0.41 exp(tau)
_IAPWS_HENRY = {
    "ch4": (-10.44708, 4.66491, 12.12986),
    "co2": (-8.55445, 4.01195, 9.52345),
}


def water_vapour_pressure_mpa(temperature_c):
    """Return the saturation pressure of water (MPa), Wagner and Pruss (2002)."""
    t_k = temperature_c + CELSIUS_TO_KELVIN
    tau = 1.0 - t_k / _T_CRIT_K
    a = (-7.85951783, 1.84408259, -11.7866497, 22.6807411, -15.9618719, 1.80122502)
    s = (
        a[0] * tau
        + a[1] * tau**1.5
        + a[2] * tau**3
        + a[3] * tau**3.5
        + a[4] * tau**4
        + a[5] * tau**7.5
    )
    return _P_CRIT_MPA * math.exp(_T_CRIT_K / t_k * s)


def henry_constant_bar(gas, temperature_c):
    """Return Henry's constant kH (bar per mole fraction) of ``gas`` in pure water."""
    a, b, c = _IAPWS_HENRY[gas]
    t_r = (temperature_c + CELSIUS_TO_KELVIN) / _T_CRIT_K
    tau = 1.0 - t_r
    ln_ratio = a / t_r + b * tau**0.355 / t_r + c * t_r**-0.41 * math.exp(tau)
    return math.exp(ln_ratio) * water_vapour_pressure_mpa(temperature_c) * 10.0


def bubble_point_bar(temperature_c, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Return the bubble point (bar a) of the brine's dissolved gas at ``temperature_c``.

    Returns a dict with ``bubble_point_bar`` and the partial pressures of
    CH4, CO2 and water vapour (bar).
    """
    gas_mol_per_kg = (
        challenge["gas_liquid_ratio"] / _NORMAL_MOLAR_VOLUME / challenge["brine_density"]
    )
    salinity = assumptions.get("brine_salinity_mol_per_kg", 0.0)
    x_total = _MOL_WATER_PER_KG + gas_mol_per_kg
    parts = {}
    for gas, fraction_key, setschenow_key in (
        ("ch4", "ch4_mol_fraction", "setschenow_ch4_kg_per_mol"),
        ("co2", "co2_mol_fraction", "setschenow_co2_kg_per_mol"),
    ):
        x_gas = challenge[fraction_key] * gas_mol_per_kg / x_total
        salting_out = 10.0 ** (assumptions.get(setschenow_key, 0.0) * salinity)
        parts[f"{gas}_partial_pressure_bar"] = (
            x_gas * henry_constant_bar(gas, temperature_c) * salting_out
        )
    parts["water_vapour_pressure_bar"] = water_vapour_pressure_mpa(temperature_c) * 10.0
    parts["bubble_point_bar"] = sum(parts.values())
    return parts
