"""What to do with the co-produced gas: burn it, keep it in the brine, re-inject it, or sell it.

The brine carries 0.8 Nm3/m3 of gas (80 mol% CH4, 20 mol% CO2). The base
plant flashes it in a separator at the producer wellhead pressure and
burns it in the CHP and the boiler (flaring the rest), which puts all of
its carbon into the air: about 2 kg CO2 per kg of gas, from the CH4 burned
and the CO2 it already holds. This module prices the alternatives:

``burn`` (base)
    Separator, CHP / boiler, flare.
``keep_dissolved``
    Keep the whole loop above the bubble point, so the gas never leaves
    the brine and goes back into the reservoir through the injector (as
    the Bavarian Molasse plants do). The producer wellhead and the ESP
    intake must stay above the bubble point; the fuel is lost.
``co_inject``
    Separate at the wellhead as now, compress the gas and put it back into
    the injection stream below the depth where the brine pressure exceeds
    the bubble point (a dip tube, as CarbFix does with CO2), so it
    re-dissolves; the fuel is lost.
``disposal_well``
    Separate, compress and inject the gas into a separate formation
    through a dedicated well (a saline aquifer or a depleted gas field),
    with storage-permit monitoring. ``disposal_well_co2_only`` first
    splits the CO2 off with a membrane and burns the CH4 as now.
``export``
    Upgrade the gas with a membrane, sell the CH4 to the regional gas
    grid and vent the CO2 split off; the plant buys natural gas instead.

The bubble point comes from :mod:`gemini_design.gas_solubility` (Henry's
law with the IAPWS constants, Setschenow salting-out, water vapour
pressure). Compression power comes from GEMINI's ``Compressor`` model.
"""

import math

from gemini_design import gas_solubility
from gemini_design.annual import run_year
from gemini_design.challenge import (
    ASSUMPTIONS,
    CHALLENGE,
    GRAVITY,
    associated_gas_properties,
)
from gemini_design.economics import capital_recovery_factor
from gemini_model.compressor.compressor import Compressor

R_GAS = 8.314462618
M_CH4, M_CO2 = 16.04, 44.01
NORMAL_MOLAR_VOLUME = 22.414e-3  # Nm3/mol

# Team assumptions (low confidence) for the gas options.
GAS_OPTION_ASSUMPTIONS = {
    "bubble_point_margin_bar": 5.0,
    "compressor_efficiency": 0.75,
    "compressor_stages_max": 4,
    "compressor_cost_eur": 5.0e5,  # small reciprocating unit, ~500 Nm3/h
    "disposal_well_depth_m": 2000.0,
    "disposal_wellhead_pressure_bar": 190.0,  # gas into a hydrostatic aquifer at 2 km
    "disposal_mmv_eur_per_year": 2.0e5,  # monitoring, measurement, verification + permit
    "membrane_upgrading_cost_eur": 1.5e6,  # biogas-type membrane unit, ~500 Nm3/h raw gas
    "membrane_power_kwh_per_nm3": 0.25,
    "grid_connection_cost_eur": 3.0e5,
}


def bubble_point_bar(t_c, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Pressure (bar) below which the brine's gas starts to come out of solution at ``t_c``.

    The same estimate the doublet model uses for the ESP setting depth
    (:func:`gemini_design.gas_solubility.bubble_point_bar`).
    """
    return gas_solubility.bubble_point_bar(t_c, challenge, assumptions)["bubble_point_bar"]


def compressor_power_w(mass_flow_kg_s, p_in_bar, p_out_bar, t_in_c, challenge=CHALLENGE, opts=None):
    """Shaft power (W) to compress the produced gas mixture, with GEMINI's Compressor."""
    opts = {**GAS_OPTION_ASSUMPTIONS, **(opts or {})}
    if mass_flow_kg_s <= 0 or p_out_bar <= p_in_bar:
        return 0.0
    m = challenge["ch4_mol_fraction"] * M_CH4 + challenge["co2_mol_fraction"] * M_CO2
    ratio = math.log(p_out_bar / p_in_bar) / math.log(4.0)
    stages = max(1, min(opts["compressor_stages_max"], math.ceil(ratio)))
    model = Compressor()
    model.update_parameters(
        {
            "number_of_stages": stages,
            "compressor_efficiency": opts["compressor_efficiency"],
            "mechanical_efficiency": 0.97,
            "specific_heat_ratio": 1.3,
            "gas_constant": R_GAS / (m / 1000.0),  # J/(kg.K)
        }
    )
    model.calculate_output(
        {
            "mass_flow": mass_flow_kg_s,
            "pressure_in": p_in_bar,
            "pressure_out": p_out_bar,
            "temperature_in": t_in_c,
        }
    )
    return float(model.get_output()["compressor_power"])


def _annual(summary):
    e = summary["economics"]
    delivered = (
        summary["energy_mwh"]["heating_delivered"] + summary["energy_mwh"]["cooling_delivered"]
    )
    return e["annual_total_cost_eur"], delivered, summary["kpi"]["co2_t_per_year"]


def compare(design, demand, challenge=CHALLENGE, assumptions=ASSUMPTIONS, opts=None):
    """Run the base design and price every gas option; return one row per option."""
    o = {**GAS_OPTION_ASSUMPTIONS, **(opts or {})}
    a, c = assumptions, challenge
    gas = associated_gas_properties(c)
    crf = capital_recovery_factor(a["discount_rate"], a["lifetime_years"])
    annuity = crf + a["fixed_om_fraction"]
    el_price, el_co2 = a["electricity_price_eur_per_mwh"], a["electricity_emission_kg_per_kwh"]
    co2_price = a["co2_price_eur_per_t"]

    daily, base = run_year(design, demand, c, a)
    base_cost, delivered, base_co2 = _annual(base)
    brine_m3 = float((daily["n_active"] * daily["flow_per_doublet_m3h"]).sum()) * 24.0
    gas_nm3 = brine_m3 * c["gas_liquid_ratio"]
    gas_kg = gas_nm3 * gas["density"]
    co2_inherent_t = gas_kg * gas["co2_mass_fraction"] / 1000.0
    co2_from_gas_t = (
        gas_kg * (gas["co2_mass_fraction"] + gas["ch4_mass_fraction"] * M_CO2 / M_CH4) / 1000.0
    )
    t_wh = float(daily["wellhead_temperature_c"].dropna().max())
    t_inj = float(daily["injection_temperature_c"].dropna().min())
    p_b = bubble_point_bar(t_wh, c, a)
    p_b_inj = bubble_point_bar(t_inj, c, a)
    hours = float((daily["n_active"] > 0).sum()) * 24.0
    gas_kg_s = gas_kg / (hours * 3600.0) if hours else 0.0
    wi_annual = base["economics"]["capex_eur"].get("well_integrity", 0.0) * annuity

    rows = [
        {
            "option": "burn",
            "annual_cost_eur": base_cost,
            "co2_t": base_co2,
            "notes": f"separator at {a['producer_wellhead_pressure_bar']:.0f} bar, CHP + boiler",
        }
    ]

    def no_gas_run(extra_assumptions):
        c0 = dict(c, gas_liquid_ratio=0.0)
        a0 = dict(a, well_integrity_costs=False, **extra_assumptions)
        d0 = type(design)(**{**design.as_dict(), "chp_capacity_mw_el": 0.0, "name": ""})
        _, s0 = run_year(d0, demand, c0, a0)
        cost0, _, co2_0 = _annual(s0)
        return cost0 + wi_annual, co2_0, s0  # corrosion mitigation as in the base

    # keep dissolved: pressurised loop above the bubble point at the wellhead temperature
    p_loop = p_b + o["bubble_point_margin_bar"]
    cost_b, co2_b, s_b = no_gas_run(
        {"producer_wellhead_pressure_bar": p_loop, "esp_intake_pressure_min_bar": p_loop}
    )
    rows.append(
        {
            "option": "keep_dissolved",
            "annual_cost_eur": cost_b,
            "co2_t": co2_b,
            "notes": f"loop held at {p_loop:.0f} bar (bubble point {p_b:.0f} bar at "
            f"{t_wh:.0f} degC); ESP set at {s_b['kpi']['esp_setting_depth_m']:.0f} m",
        }
    )

    # co-inject: separate at the wellhead, compress to the bubble point (+ margin) of the
    # injection stream and inject it through a dip tube where the brine pressure is that high
    cost_c0, co2_c0, _ = no_gas_run({})
    p_dip = p_b_inj + o["bubble_point_margin_bar"]
    comp_w = compressor_power_w(gas_kg_s, a["producer_wellhead_pressure_bar"], p_dip, t_wh, c, o)
    comp_mwh = comp_w * hours / 1e6
    comp_cost = (
        comp_mwh * el_price + comp_mwh * el_co2 * co2_price + o["compressor_cost_eur"] * annuity
    )
    dip_depth = max(0.0, (p_dip - 10.0) * 1e5 / (c["brine_density"] * GRAVITY))
    rows.append(
        {
            "option": "co_inject",
            "annual_cost_eur": cost_c0 + comp_cost,
            "co2_t": co2_c0 + comp_mwh * el_co2,
            "notes": f"gas compressed to {p_dip:.0f} bar ({comp_w / 1e3:.0f} kW), dip tube to "
            f"~{dip_depth:.0f} m in the injector",
        }
    )

    # dedicated disposal well, all gas
    well = a["well_cost_fixed_eur"] + a["well_cost_per_m_eur"] * o["disposal_well_depth_m"]
    p_disp = o["disposal_wellhead_pressure_bar"]
    comp_d_w = compressor_power_w(gas_kg_s, a["producer_wellhead_pressure_bar"], p_disp, t_wh, c, o)
    comp_d_mwh = comp_d_w * hours / 1e6
    fixed_d = (well + o["compressor_cost_eur"]) * annuity + o["disposal_mmv_eur_per_year"]
    rows.append(
        {
            "option": "disposal_well",
            "annual_cost_eur": cost_c0
            + fixed_d
            + comp_d_mwh * el_price
            + comp_d_mwh * el_co2 * co2_price,
            "co2_t": co2_c0 + comp_d_mwh * el_co2,
            "notes": f"{o['disposal_well_depth_m']:.0f} m well, {p_disp:.0f} bar "
            f"({comp_d_w / 1e3:.0f} kW), storage permit + monitoring",
        }
    )

    # dedicated disposal well, CO2 only (membrane), CH4 still burned as in the base
    co2_kg_s = gas_kg_s * gas["co2_mass_fraction"]
    comp_co2_w = compressor_power_w(
        co2_kg_s, 1.5, p_disp, 30.0, dict(c, ch4_mol_fraction=0.0, co2_mol_fraction=1.0), o
    )
    comp_co2_mwh = comp_co2_w * hours / 1e6
    membrane_mwh = gas_nm3 * o["membrane_power_kwh_per_nm3"] / 1000.0
    el_d2 = comp_co2_mwh + membrane_mwh
    fixed_d2 = (well + o["compressor_cost_eur"] + o["membrane_upgrading_cost_eur"]) * annuity
    rows.append(
        {
            "option": "disposal_well_co2_only",
            "annual_cost_eur": base_cost
            + fixed_d2
            + o["disposal_mmv_eur_per_year"]
            + el_d2 * el_price
            + (el_d2 * el_co2 - co2_inherent_t) * co2_price,
            "co2_t": base_co2 - co2_inherent_t + el_d2 * el_co2,
            "notes": "membrane splits the CO2 off; the CH4 still goes to the CHP / boiler "
            "(approximation: the CH4-rich gas burns as before)",
        }
    )

    # export the upgraded CH4 to the gas grid; the split-off CO2 is vented
    ch4_mwh = gas_kg * gas["ch4_mass_fraction"] * 50.0 / 3600.0  # LHV 50 MJ/kg
    revenue = ch4_mwh * a["gas_price_eur_per_mwh"]
    fixed_e = (o["membrane_upgrading_cost_eur"] + o["grid_connection_cost_eur"]) * annuity
    rows.append(
        {
            "option": "export",
            "annual_cost_eur": cost_c0
            + fixed_e
            + membrane_mwh * el_price
            + (membrane_mwh * el_co2 + co2_inherent_t) * co2_price
            - revenue,
            "co2_t": co2_c0 + co2_inherent_t + membrane_mwh * el_co2,
            "notes": f"sells {ch4_mwh:,.0f} MWh of CH4 (its CO2 is then emitted by the buyer)",
        }
    )

    exported_ch4_co2_t = gas_kg * gas["ch4_mass_fraction"] * M_CO2 / M_CH4 / 1000.0
    for r in rows:
        r["lcoe_eur_per_mwh"] = r["annual_cost_eur"] / delivered
        # global: the buyer burns the exported CH4, so its CO2 still reaches the air
        r["global_co2_t"] = r["co2_t"] + (exported_ch4_co2_t if r["option"] == "export" else 0.0)
        r["co2_saved_t"] = base_co2 - r["global_co2_t"]
        extra = r["annual_cost_eur"] - base_cost
        if r["co2_saved_t"] > 1.0:
            r["abatement_eur_per_t"] = extra / r["co2_saved_t"]
            r["break_even_co2_price_eur_per_t"] = co2_price + r["abatement_eur_per_t"]
        else:
            r["abatement_eur_per_t"] = None
            r["break_even_co2_price_eur_per_t"] = None
    info = {
        "design": design.name,
        "bubble_point_bar_at_wellhead": p_b,
        "bubble_point_bar_at_injection": p_b_inj,
        "wellhead_temperature_c": t_wh,
        "gas_nm3_per_year": gas_nm3,
        "co2_from_associated_gas_t": co2_from_gas_t,
        "co2_inherent_t": co2_inherent_t,
        "co2_price_eur_per_t": co2_price,
    }
    return rows, info


def _round_or_none(x):
    return None if x is None else round(float(x))


def summary_table(rows):
    """Plain dict rows rounded for reports."""
    out = []
    for r in rows:
        out.append(
            {
                "option": r["option"],
                "lcoe_eur_per_mwh": round(r["lcoe_eur_per_mwh"], 2),
                "co2_t_per_year": round(float(r["co2_t"])),
                "global_co2_t_per_year": round(float(r["global_co2_t"])),
                "co2_saved_t": round(float(r["co2_saved_t"])),
                "abatement_eur_per_t": _round_or_none(r["abatement_eur_per_t"]),
                "break_even_co2_price_eur_per_t": _round_or_none(
                    r["break_even_co2_price_eur_per_t"]
                ),
                "notes": r["notes"],
            }
        )
    return out


__all__ = [
    "GAS_OPTION_ASSUMPTIONS",
    "bubble_point_bar",
    "compare",
    "compressor_power_w",
    "summary_table",
]
