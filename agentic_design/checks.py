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
    if getattr(a, "maintenance_mode", "staggered") == "simultaneous":
        out_days = daily.loc[daily["doublets_available"] == 0, "date"]
        out.append(_finding("I1_GEOTHERMAL_OUTAGE", "info",
                            f"Geothermal source available 330 days (organisers, 1 Nov): one plant-wide "
                            f"{a.maintenance_days_per_doublet}-day outage"
                            + (f" from {out_days.iloc[0].date()} to {out_days.iloc[-1].date()}" if len(out_days) else "")
                            + "; boilers and electric chillers meet all demand then. An unplanned outage could hit "
                              f"the peak: full backup needs {daily['heating_mw'].max():.0f} MW boilers and "
                              f"{daily['cooling_mw'].max():.0f} MW electric chillers."))
    else:
        out.append(_finding("I1_330_DAYS_INTERPRETATION", "info",
                            "330 operating days per doublet with staggered "
                            f"{a.maintenance_days_per_doublet}-day shut-ins, so the other doublets keep running "
                            "(allowed by the organisers, 2 Nov). Shared surface equipment then needs maintenance "
                            "without a full shutdown (e.g. spare filter) - state this in the report."))
    # C7 heating demand met at 100 degC
    supplied = (daily["heat_geothermal_mw"] + daily["heat_pump_mw"] + daily["heat_assoc_gas_boiler_mw"]
                + daily["heat_ng_boiler_mw"])
    short = daily["heating_mw"] - supplied > a.demand_tolerance_mw
    if short.any():
        out.append(_finding("C7_HEATING_UNMET", "violation",
                            f"heating short by {kpis['heating_unmet_gwh']:.2f} GWh/yr.", dates[short]))
    # C8 cooling demand met at 20 degC
    cshort = daily["cooling_mw"] - daily["cooling_supplied_mw"] > a.demand_tolerance_mw
    if cshort.any():
        cause = ("the design has NO cooling technology; add absorption and/or electric chillers - more doublets or "
                 "deeper wells alone cannot fix this" if design.cooling == "none" else
                 f"cooling capacity ({design.cooling}) too small on peak days or absorption lacks drive heat; "
                 f"peak cooling demand is {daily['cooling_mw'].max():.1f} MW")
        out.append(_finding("C8_COOLING_UNMET", "violation",
                            f"cooling short by {kpis['cooling_unmet_gwh']:.2f} GWh/yr: {cause}.", dates[cshort]))
    # P1 energy balance closes
    over = supplied - daily["heating_mw"] > a.demand_tolerance_mw
    if over.any():
        out.append(_finding("P1_ENERGY_BALANCE", "violation", "heat supplied exceeds demand (balance error).", dates[over]))
    # P2 HX temperatures physically consistent
    t_sup = CHALLENGE["heating_supply_temperature_c"]
    # A fixed-size HX may run below its design approach at part load (that is
    # physical); only a temperature CROSS (negative approach) is impossible.
    hot_end = daily["t_hx_brine_in_c"] - daily["t_network_after_hx_c"]
    cold_end = daily["t_hx_brine_out_c"] - a.heating_return_temperature_c
    has_heat = daily["heat_geothermal_mw"] > 1e-9
    bad_hx = active & has_heat & ((hot_end < -1e-6) | (cold_end < -1e-6))
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
    # P7 heat pump and chillers within physical bounds
    hp = daily["heat_pump_mw"] > 1e-9
    if hp.any() and ((daily.loc[hp, "heat_pump_cop"] < 1) | (daily.loc[hp, "heat_pump_cop"] > 10)).any():
        out.append(_finding("P7_HEAT_PUMP_COP", "violation", "heat pump COP outside 1-10."))
    ab = daily["cooling_absorption_mw"] > 1e-9
    if ab.any() and ((daily.loc[ab, "absorption_cop"] <= 0) | (daily.loc[ab, "absorption_cop"] >= 1)).any():
        out.append(_finding("P7_ABSORPTION_COP", "violation", "absorption chiller COP outside 0-1."))
    cool_bal = (daily["cooling_absorption_mw"] + daily["cooling_electric_mw"] + daily["cooling_unmet_mw"]
                - daily["cooling_mw"]).abs() > a.demand_tolerance_mw
    if cool_bal.any():
        out.append(_finding("P1_ENERGY_BALANCE", "violation", "cooling balance does not close.", dates[cool_bal]))
    # P8 oversized / unused components (costs are not modelled, so this is the only brake on oversizing)
    for label, cap, col in (("heat pump", design.heat_pump_mw, "heat_pump_mw"),
                            ("absorption chiller", design.absorption_mw, "cooling_absorption_mw"),
                            ("electric chiller", design.electric_chiller_mw, "cooling_electric_mw")):
        if cap > 0:
            peak_use = float(daily[col].max())
            energy = float(daily[col].sum() * 24 / 1e3)
            if peak_use < 0.5 * cap:
                out.append(_finding("P8_OVERSIZED", "warning",
                                    f"{label} {cap:g} MW: peak use {peak_use:.1f} MW, {energy:.1f} GWh/yr. Oversized"
                                    + (" or unnecessary" if energy < 0.01 * cap * 8.76 else "")
                                    + f"; choose about {max(peak_use, 0.0):.1f} MW or remove it (an oversized unit only adds cost)."))
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
