"""Constraint checker: every challenge rule plus physical sanity checks.

Returns structured findings so an agent can read them, react (change the
design) and quote them in its explanation. Severity:

* ``violation`` - breaks a hard challenge rule or demand is not met
* ``warning``   - physically questionable or an operational concern
* ``info``      - interpretation/assumption the report must disclose
"""

import numpy as np

from agentic_design.config import CHALLENGE, Assumptions

TOL = 1e-6


def _finding(code, severity, message, days=None):
    f = {"code": code, "severity": severity, "message": message}
    if days is not None and len(days):
        f["n_days"] = int(len(days))
        f["first_dates"] = [str(d.date()) for d in days[:5]]
    return f


def check(daily, kpis, design, a: Assumptions):
    out = []
    dates = daily["date"]
    active = daily["doublets_on"] > 0

    # C1 number of doublets
    if not CHALLENGE["n_doublets_min"] <= design.n_doublets <= CHALLENGE["n_doublets_max"]:
        out.append(_finding("C1_DOUBLET_COUNT", "violation",
                            f"{design.n_doublets} doublets; challenge allows 1-3."))
    # C2 / C3 flow limits per doublet
    hi = active & (daily["q_per_doublet_m3h"] > CHALLENGE["max_flow_m3h_per_doublet"] + TOL)
    if hi.any():
        out.append(_finding("C2_MAX_FLOW", "violation",
                            f"flow above {CHALLENGE['max_flow_m3h_per_doublet']:.0f} m3/h per doublet.", dates[hi]))
    lo = active & (daily["q_per_doublet_m3h"] < CHALLENGE["min_flow_m3h_per_doublet"] - TOL)
    if lo.any():
        out.append(_finding("C3_MIN_FLOW", "violation",
                            f"active doublet below {CHALLENGE['min_flow_m3h_per_doublet']:.0f} m3/h.", dates[lo]))
    # C4 brine cooling producer -> injector
    cool = active & (daily["brine_cooling_c"] > CHALLENGE["max_brine_cooling_c"] + 1e-3)
    if cool.any():
        out.append(_finding("C4_BRINE_COOLING", "violation",
                            f"brine cooled by up to {daily.loc[cool, 'brine_cooling_c'].max():.2f} degC "
                            f"(cap {CHALLENGE['max_brine_cooling_c']:.0f} degC).", dates[cool]))
    # C5 production/injection volume balance
    imb = (daily["production_m3h"] - daily["injection_m3h"]).abs() > TOL
    if imb.any():
        out.append(_finding("C5_VOLUME_BALANCE", "violation", "produced and injected volumes differ.", dates[imb]))
    # C6 operating days per doublet
    for i, n in enumerate(kpis["operating_days_per_doublet"]):
        if n > CHALLENGE["max_operating_days_per_doublet"]:
            out.append(_finding("C6_OPERATING_DAYS", "violation",
                                f"doublet {i + 1} runs {n} days (> {CHALLENGE['max_operating_days_per_doublet']})."))
    out.append(_finding("I1_330_DAYS_INTERPRETATION", "info",
                        "'330 daily steps' interpreted as max 330 operating days per doublet "
                        f"({a.maintenance_days_per_doublet}-day maintenance window each). Confirm with organisers."))
    # C7 heating demand met at 100 degC
    supplied = daily["heat_geothermal_mw"] + daily["heat_assoc_gas_boiler_mw"] + daily["heat_ng_boiler_mw"]
    short = daily["heating_mw"] - supplied > a.demand_tolerance_mw
    if short.any():
        out.append(_finding("C7_HEATING_UNMET", "violation",
                            f"heating short by {kpis['heating_unmet_gwh']:.2f} GWh/yr.", dates[short]))
    # C8 cooling demand met at 20 degC
    cshort = daily["cooling_mw"] - daily["cooling_supplied_mw"] > a.demand_tolerance_mw
    if cshort.any():
        out.append(_finding("C8_COOLING_UNMET", "violation",
                            f"cooling short by {kpis['cooling_unmet_gwh']:.2f} GWh/yr "
                            f"(design cooling='{design.cooling}').", dates[cshort]))
    # P1 energy balance closes
    over = supplied - daily["heating_mw"] > a.demand_tolerance_mw
    if over.any():
        out.append(_finding("P1_ENERGY_BALANCE", "violation", "heat supplied exceeds demand (balance error).", dates[over]))
    # P2 HX temperatures physically consistent
    t_sup = CHALLENGE["heating_supply_temperature_c"]
    # A fixed-size HX may run below its design approach at part load (that is
    # physical); only a temperature CROSS (negative approach) is impossible.
    t_brine_in = daily["t_wellhead_c"] - a.surface_temperature_loss_c
    hot_end = t_brine_in - daily["t_network_after_hx_c"]
    cold_end = daily["t_injection_c"] - a.heating_return_temperature_c
    bad_hx = active & ((hot_end < -1e-6) | (cold_end < -1e-6))
    if bad_hx.any():
        out.append(_finding("P2_HX_TEMPERATURE_CROSS", "violation",
                            "heat exchanger temperature cross (heat flowing cold to hot).", dates[bad_hx]))
    if (daily["t_network_after_hx_c"] > t_sup + 1e-6).any():
        out.append(_finding("P2_HX_TEMPERATURE_CROSS", "violation", "network heated above the 100 degC supply."))
    # P3 ESP intake above minimum
    low_in = active & (daily["esp_intake_bar"] < a.min_esp_intake_pressure_bar)
    if low_in.any():
        out.append(_finding("P3_ESP_INTAKE", "warning",
                            f"ESP intake below {a.min_esp_intake_pressure_bar:.0f} bar: gas breakout/cavitation risk; "
                            "set the ESP deeper.", dates[low_in]))
    # P4 injector would run on vacuum without back-pressure
    choke = active & daily["injection_choke_needed"]
    if choke.any():
        out.append(_finding("P4_INJECTION_CHOKE", "info",
                            "injector needs less pressure than the surface delivers on these days: "
                            "a choke/back-pressure valve keeps the gas in solution.", dates[choke]))
    # P5 associated gas wasted
    if kpis["assoc_gas_unused_share"] > 0.01:
        out.append(_finding("P5_ASSOC_GAS_UNUSED", "warning",
                            f"{kpis['assoc_gas_unused_share']:.0%} of associated gas is not used (would be flared)."))
    # P6 temperatures within physical bounds
    t_res = daily["t_wellhead_c"].max()
    if active.any() and (daily.loc[active, "t_injection_c"] > daily.loc[active, "t_wellhead_c"] + 1e-6).any():
        out.append(_finding("P6_TEMPERATURE_ORDER", "violation", "injection hotter than production."))
    if np.isfinite(t_res) and t_res > CHALLENGE["surface_temperature_c"] + CHALLENGE["geothermal_gradient_c_per_km"] * design.well.depth_m / 1000 + 1e-6:
        out.append(_finding("P6_TEMPERATURE_ORDER", "violation", "wellhead hotter than the reservoir."))
    return out


def summarize(findings):
    sev = {"violation": 0, "warning": 0, "info": 0}
    for f in findings:
        sev[f["severity"]] += 1
    return sev
