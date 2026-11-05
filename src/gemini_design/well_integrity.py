"""Well integrity: CO2 corrosion and erosion of the doublet wells, with GEMINI's own models.

The brine carries 0.8 Nm3/m3 of gas with 20 mol% CO2, so the casing sees
dissolved CO2 all the way from the reservoir to the injector. This module
runs GEMINI's corrosion and erosion models (``gemini_model.corrosion`` and
``gemini_model.erosion``, used by GEMINI's WIMS application) on three
points of a doublet at full flow:

1. producer bottom (reservoir temperature, bottomhole pressure),
2. producer wellhead (wellhead temperature; the gas is still dissolved
   up to the separator),
3. injector (the brine after the separator at the coldest injection
   temperature the 40 K cap allows).

The CO2 partial pressure comes from GEMINI's ``CO2PartialPressureModel``
(Henry's law). Upstream of the separator the "sample" is the brief's own
GLR definition: 0.8 Nm3/m3 liberated at normal conditions (0 degC,
1.01325 bar), plus the CO2 still dissolved in the water at those
conditions. Downstream of the separator only the CO2 dissolved at
separator pressure and temperature is left (conservatively at the
overall 20 mol% CO2 in the separated gas). Corrosion rates come from
NORSOK M-506 (the design basis, with
the brine pH from bicarbonate and salinity) and de Waard-Lotz-Dugstad
1995 (a cross-check); the higher of the two is used, for uninhibited
carbon steel. Erosion is checked against the API RP 14E velocity limit
(the brief gives no sand rate, so the sand-erosion models are not run).

The mitigation is the cheapest one, over the plant life, that keeps the
wall loss within ``corrosion_allowance_mm``: bare carbon steel, carbon
steel with continuous inhibitor dosing (``corrosion_inhibitor_efficiency``),
or a corrosion-resistant liner (GRE-lined casing) in both wells.
"""

import math

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, CELSIUS_TO_KELVIN
from gemini_design.doublet import DoubletHydraulics
from gemini_model.corrosion.co2_corrosion import CO2Corrosion
from gemini_model.corrosion.correlation.co2_partial_pressure_model import (
    CO2PartialPressureModel,
)
from gemini_model.erosion.erosion_model import ErosionModel

R_GAS = 8.314462618  # J/(mol.K)
NACL_G_PER_MOL = 58.44
_M_CH4, _M_CO2 = 16.04, 44.01


def _gas_molar_mass(challenge):
    return challenge["ch4_mol_fraction"] * _M_CH4 + challenge["co2_mol_fraction"] * _M_CO2


NORMAL_PRESSURE_BAR, NORMAL_TEMPERATURE_C = 1.01325, 0.0


def co2_partial_pressure_bar(
    temperature_c,
    sample_pressure_bar,
    sample_temperature_c,
    gas_water_ratio,
    challenge=CHALLENGE,
):
    """CO2 partial pressure (bar) of the brine at ``temperature_c``, via GEMINI's model.

    The sample is where the gas-water ratio is defined: normal conditions
    with ``gas_water_ratio`` = the brief's 0.8 Nm3/m3 upstream of the
    separator; the separator itself with ``gas_water_ratio`` = 0 after it.
    """
    m = _gas_molar_mass(challenge)
    rho_gas = (
        sample_pressure_bar * 1e5 * m * 1e-3 / (R_GAS * (sample_temperature_c + CELSIUS_TO_KELVIN))
    )
    model = CO2PartialPressureModel()
    model.calculate_output(
        {
            "gas_pressure": sample_pressure_bar,
            "co2_mol_fraction": challenge["co2_mol_fraction"],
            "gas_water_ratio": gas_water_ratio,
            "gas_density": rho_gas,
            "gas_molecular_weight": m,
            "temperature_sample": sample_temperature_c,
            "temperature_system": temperature_c,
        },
        None,
    )
    return model.get_output()["CO2 Partial Pressure [bar]"]


def corrosion_rates_mm_per_year(
    temperature_c, pressure_bar, co2_pressure_bar, flow_m3h, challenge, assumptions
):
    """Return uninhibited carbon-steel CO2 corrosion rates (mm/yr): NORSOK M-506 and DLD 1995."""
    a = assumptions
    diameter = a["well_inner_diameter_m"]
    rates = {}
    norsok = CO2Corrosion()
    norsok.update_parameters(
        {"corrosion_model": "NORSOK", "diameter": diameter, "roughness": a["well_roughness_m"]}
    )
    norsok.calculate_output(
        {
            "co2_partial_pressure": co2_pressure_bar,
            "pressure": pressure_bar,
            "temperature": temperature_c,
            "water_density": challenge["brine_density"],
            "water_viscosity": challenge["brine_viscosity"] * 1e3,  # cP
            "water_flow_rate": flow_m3h * 24.0,  # m3/day
            "bicarb_concentration": a["brine_bicarbonate_mg_per_l"],
            "ionic_strength": a["brine_salinity_mol_per_kg"] * NACL_G_PER_MOL,  # g/l
        },
        None,
    )
    rates["norsok"] = float(norsok.get_output()["corrosion_rate"])
    dld = CO2Corrosion()
    dld.update_parameters({"corrosion_model": "DLD", "diameter": diameter})
    dld.calculate_output(
        {
            "co2_partial_pressure": co2_pressure_bar,
            "pressure": pressure_bar,
            "temperature": temperature_c,
            "flow_rate": flow_m3h / 3600.0,
        },
        None,
    )
    rates["dld"] = float(dld.get_output()["corrosion_rate"])
    rates["design"] = max(rates.values())
    return rates


def erosion_check(flow_m3h, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """API RP 14E erosional velocity limit vs the casing velocity at ``flow_m3h``."""
    model = ErosionModel()
    model.update_parameters({"erosion_model": "API"})
    model.calculate_output({"rho_fluid": challenge["brine_density"]}, None)
    limit = model.get_output()["erosion_velocity_ms"]
    area = math.pi * assumptions["well_inner_diameter_m"] ** 2 / 4.0
    velocity = flow_m3h / 3600.0 / area
    return {
        "velocity_ms": velocity,
        "api_rp14e_limit_ms": limit,
        "ratio": velocity / limit,
        "ok": velocity <= limit,
    }


def assess(depth_m, flow_m3h=None, challenge=CHALLENGE, assumptions=ASSUMPTIONS, hydraulics=None):
    """Corrosion, erosion and the chosen mitigation for one doublet at ``depth_m``.

    Rates are taken at ``flow_m3h`` (default: the 300 m3/h cap, the worst
    case for flow-driven corrosion and erosion).
    """
    c, a = challenge, assumptions
    q = c["flow_max_m3h"] if flow_m3h is None else flow_m3h
    hyd = DoubletHydraulics(depth_m, c, a) if hydraulics is None else hydraulics
    prod = hyd.producer(q)
    t_bh = hyd.production_temperature_c
    t_wh = prod["wellhead_temperature_c"]
    p_sep = a["producer_wellhead_pressure_bar"]
    t_inj = t_wh - c["brine_cooling_max_k"]
    inj = hyd.injector(q, t_inj)

    normal = (NORMAL_PRESSURE_BAR, NORMAL_TEMPERATURE_C, c["gas_liquid_ratio"])
    separator = (p_sep, t_wh, 0.0)
    points = {
        "producer_bottom": (t_bh, prod["bottomhole_pressure_bar"], normal),
        "producer_wellhead": (t_wh, prod["wellhead_pressure_bar"], normal),
        "injector": (t_inj, inj["bottomhole_pressure_bar"], separator),
    }
    out = {"flow_m3h": q, "points": {}}
    for name, (t, p, sample) in points.items():
        pco2 = co2_partial_pressure_bar(t, *sample, c)
        rates = corrosion_rates_mm_per_year(t, p, pco2, q, c, a)
        out["points"][name] = {
            "temperature_c": t,
            "pressure_bar": p,
            "co2_partial_pressure_bar": pco2,
            "corrosion_mm_per_year": rates,
        }
    out["erosion"] = erosion_check(q, c, a)
    worst = max(pt["corrosion_mm_per_year"]["design"] for pt in out["points"].values())
    out["worst_corrosion_mm_per_year"] = worst
    out["mitigation"] = choose_mitigation(worst, depth_m, a)
    return out


def choose_mitigation(rate_mm_per_year, depth_m, assumptions=ASSUMPTIONS):
    """Cheapest mitigation (per doublet) that keeps the life wall loss within the allowance."""
    a = assumptions
    life, allowance = a["lifetime_years"], a["corrosion_allowance_mm"]
    rate_crf = a["discount_rate"] * (1 + a["discount_rate"]) ** life
    crf = rate_crf / ((1 + a["discount_rate"]) ** life - 1)
    liner_capex = a["corrosion_resistant_liner_cost_eur_per_m"] * depth_m * 2  # both wells
    options = [
        ("carbon steel", rate_mm_per_year, 0.0, 0.0),
        (
            "carbon steel + inhibitor",
            rate_mm_per_year * (1 - a["corrosion_inhibitor_efficiency"]),
            0.0,
            a["corrosion_inhibitor_cost_eur_per_doublet_year"],
        ),
        ("GRE-lined casing", 0.0, liner_capex, 0.0),
    ]
    feasible = []
    for name, rate, capex, opex in options:
        wall_loss = rate * life
        annual = capex * crf + capex * a["fixed_om_fraction"] + opex
        row = {
            "option": name,
            "life_wall_loss_mm": wall_loss,
            "years_to_allowance": allowance / rate if rate > 0 else float("inf"),
            "capex_eur_per_doublet": capex,
            "opex_eur_per_doublet_year": opex,
            "annual_cost_eur_per_doublet": annual,
        }
        if wall_loss <= allowance + 1e-12:
            feasible.append(row)
    best = min(feasible, key=lambda r: r["annual_cost_eur_per_doublet"])
    return best


_CACHE = {}


def _key(depth_m, challenge, assumptions):
    items = tuple(sorted((k, v) for k, v in {**challenge, **assumptions}.items()))
    return (round(float(depth_m), 3), items)


def mitigation_cost(design, assumptions=ASSUMPTIONS, challenge=CHALLENGE):
    """Return (capex EUR, opex EUR/yr) of corrosion mitigation for all of a design's doublets.

    Zero when ``assumptions["well_integrity_costs"]`` is off.
    """
    if not assumptions.get("well_integrity_costs", True):
        return 0.0, 0.0
    depths = design.well_depths_m() if hasattr(design, "well_depths_m") else None
    capex = opex = 0.0
    for depth in depths or [design.depth_m] * design.n_doublets:
        key = _key(depth, challenge, assumptions)
        if key not in _CACHE:
            _CACHE[key] = assess(depth, None, challenge, assumptions)["mitigation"]
        capex += _CACHE[key]["capex_eur_per_doublet"]
        opex += _CACHE[key]["opex_eur_per_doublet_year"]
    return capex, opex
