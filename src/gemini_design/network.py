"""District network return temperatures as a design choice, and what they cost.

The organisers leave the heating and cooling return temperatures to the
designer (answer of 1 Nov 2026), within the hard rules. Inside the plant a
return temperature changes the HEX, heat pump, chiller, free cooling, ATES
and pit-store physics (all read ``heating_return_c`` / ``cooling_return_c``).
Outside the plant it changes two things this module prices, *relative to a
reference network* (40 degC heating return, 26 degC cooling return), so a
design at the reference temperatures costs exactly what it did before:

1. Customer substations. Each building connects through a counter-flow
   plate heat exchanger to its own circuit (heating ``building_heating_*``,
   cooling ``building_cooling_*``). A district return closer to the building
   circuit's return needs more plate area (area ~ 1 / LMTD); a return
   further away needs less. The HEX-area part of the substation cost scales
   with ``LMTD_ref / LMTD``; the rest of the substation does not change.
   The district return can not come closer than
   ``substation_min_approach_k`` to the building circuit.
2. Network pumping. The circulation flow is Q / (rho cp dT); its pump power
   is flow x ``*_network_dp_bar`` / pump efficiency, so a wider supply-return
   difference pumps less water. Only the difference to the reference
   network's pumping is booked (grid electricity, with its price and CO2).

Every number here is a stated, low-confidence assumption (see
``gemini_design.challenge.ASSUMPTIONS``); the agent can override them.
"""

import math

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE

RETURN_KEYS = ("heating_return_c", "cooling_return_c")


def design_assumptions(design, assumptions=ASSUMPTIONS):
    """Return ``assumptions`` with the design's own return temperatures, if it sets them."""
    own = {k: getattr(design, k, None) for k in RETURN_KEYS}
    own = {k: float(v) for k, v in own.items() if v is not None}
    if not own or all(assumptions.get(k) == v for k, v in own.items()):
        return assumptions
    return {**assumptions, **own}


def _lmtd(dt_a, dt_b):
    if dt_a <= 0 or dt_b <= 0:
        return 0.0
    if abs(dt_a - dt_b) < 1e-9:
        return dt_a
    return (dt_a - dt_b) / math.log(dt_a / dt_b)


def heating_substation_lmtd(t_return, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """LMTD (K) of a customer heating substation: district supply -> t_return,
    building circuit return -> building supply."""
    a = assumptions
    hot_end = challenge["heating_supply_c"] - a["building_heating_supply_c"]
    cold_end = t_return - a["building_heating_return_c"]
    return _lmtd(hot_end, cold_end)


def cooling_substation_lmtd(t_return, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """LMTD (K) of a customer cooling substation: district supply -> t_return,
    building circuit return (warm) -> building supply (cold)."""
    a = assumptions
    warm_end = a["building_cooling_return_c"] - t_return
    cold_end = a["building_cooling_supply_c"] - challenge["cooling_supply_c"]
    return _lmtd(warm_end, cold_end)


def check_returns(challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Raise ValueError if a return temperature leaves no room for the substations."""
    a = assumptions
    gap = a["substation_min_approach_k"]
    lo = a["building_heating_return_c"] + gap
    if not lo <= a["heating_return_c"] < challenge["heating_supply_c"]:
        raise ValueError(
            f"heating_return_c must be within {lo:g}-{challenge['heating_supply_c']:g} degC "
            f"(building heating circuit returns at {a['building_heating_return_c']:g} degC, "
            f"substation approach at least {gap:g} K)"
        )
    hi = a["building_cooling_return_c"] - gap
    if not challenge["cooling_supply_c"] < a["cooling_return_c"] <= hi:
        raise ValueError(
            f"cooling_return_c must be within {challenge['cooling_supply_c']:g}-{hi:g} degC "
            f"(building cooling circuit returns at {a['building_cooling_return_c']:g} degC, "
            f"substation approach at least {gap:g} K)"
        )


def delta_costs(heating_w, cooling_w, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Return the network costs of the chosen returns minus those of the reference network.

    ``heating_w`` / ``cooling_w`` are the daily demand arrays (W). Returns a
    dict: ``substation_capex_eur`` (one-off), ``pumping_mwh_el`` (per year;
    negative = less pumping than the reference) and the LMTDs used.
    """
    a, c = assumptions, challenge
    ref_h, ref_c = a["network_reference_heating_return_c"], a["network_reference_cooling_return_c"]
    rho_cp = a["water_density"] * a["water_cp"]
    eta = c["pump_efficiency"]
    peak_h_kw = max(heating_w) / 1e3 if len(heating_w) else 0.0
    peak_c_kw = max(cooling_w) / 1e3 if len(cooling_w) else 0.0

    out = {"substation_capex_eur": 0.0, "pumping_mwh_el": 0.0}
    if a["heating_return_c"] != ref_h:
        lm, lm_ref = heating_substation_lmtd(a["heating_return_c"], c, a), heating_substation_lmtd(
            ref_h, c, a
        )
        out["heating_substation_lmtd_k"] = lm
        out["substation_capex_eur"] += (
            peak_h_kw * a["heating_substation_hex_cost_eur_per_kw"] * (lm_ref / lm - 1.0)
        )
        dt, dt_ref = c["heating_supply_c"] - a["heating_return_c"], c["heating_supply_c"] - ref_h
        flow_m3 = sum(heating_w) * 86400.0 / rho_cp  # m3 per year per K of dT
        out["pumping_mwh_el"] += (
            flow_m3 * (1.0 / dt - 1.0 / dt_ref) * a["heating_network_dp_bar"] * 1e5 / eta / 3.6e9
        )
    if a["cooling_return_c"] != ref_c:
        lm, lm_ref = cooling_substation_lmtd(a["cooling_return_c"], c, a), cooling_substation_lmtd(
            ref_c, c, a
        )
        out["cooling_substation_lmtd_k"] = lm
        out["substation_capex_eur"] += (
            peak_c_kw * a["cooling_substation_hex_cost_eur_per_kw"] * (lm_ref / lm - 1.0)
        )
        dt, dt_ref = a["cooling_return_c"] - c["cooling_supply_c"], ref_c - c["cooling_supply_c"]
        flow_m3 = sum(cooling_w) * 86400.0 / rho_cp
        out["pumping_mwh_el"] += (
            flow_m3 * (1.0 / dt - 1.0 / dt_ref) * a["cooling_network_dp_bar"] * 1e5 / eta / 3.6e9
        )
    return out
