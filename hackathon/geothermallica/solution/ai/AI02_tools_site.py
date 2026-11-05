"""Site and single-well tools: reservoir inputs, demand, one doublet, the injector and the heat pump."""
from AI02_tools_common import _esp, _need, _peaks, gwh, r2
from AI02_tools_gemini import INJECTOR_GEMINI, PRODUCER_GEMINI, gemini
from gemini_model.heatpump.heatpump_lift import HeatPumpLift
from geo.common import DEPTH_M, DT_BRINE_MAX_K, Q_MAX_M3H, Q_MIN_M3H, t_reservoir_c
from geo.plant import doublet_at
from geo.well import Producer, injector_at, reservoir_pressure
from geo import year


def site_inputs(supply_heat_c, supply_cold_c, depth_m=DEPTH_M):
    """Call first. Reservoir at depth_m (1500-4000 m): temperature from the 30 C/km gradient, pressure (the brief's 250 bar at 2500
    m, hydrostatic elsewhere), producer wellhead T at 300 m3/h; and whether the design tables cover the supply setpoints (built
    for 100 C heat / 20 C cold only). Any depth in range is supported: pass the same depth_m to every other tool [D, A]."""
    _need("depth_m", depth_m, 1500, 4000)
    _need("supply_heat_c", supply_heat_c, 60, 120)
    _need("supply_cold_c", supply_cold_c, 6, 25)
    w = Producer(depth_m=float(depth_m), stages=24)
    f = w.freq_for_wellhead(300.0)
    ok = supply_heat_c == 100 and supply_cold_c == 20
    problems = [] if ok else ["design tables assume 100 C heat / 20 C cold supply; other setpoints need the exchanger and heat pump "
                              "recomputed (not implemented)"]
    depth_msg = "" if abs(depth_m - DEPTH_M) < 1e-6 else (f" at {depth_m:.0f} m (24 ESP stages as at 2500 m [A]; "
                                                          "doublet price on the ThermoGIS depth curve [L])")
    return r2({"depth_m": depth_m, "T_reservoir_C": t_reservoir_c(depth_m), "T_reservoir_tag": "[D] 12 C + 30 C/km",
               "p_reservoir_bar": reservoir_pressure(depth_m),
               "p_reservoir_tag": "[D] brief" if abs(depth_m - DEPTH_M) < 1e-6 else "[A] hydrostatic",
               "T_wellhead_300m3h_C": w.run(300.0, f if f is not None else 60.0)["T_wellhead_C"],
               "wellhead_10bar_reached_at_60Hz": f is not None,
               "supply_heat_c": supply_heat_c, "supply_cold_c": supply_cold_c, "supported": ok,
               "message": ("design tables built for 100 C heat / 20 C cold supply" + depth_msg) if ok else "; ".join(problems),
               "tag": "[D, A]"}) | gemini(PRODUCER_GEMINI)


def demand_summary(peak_heat_MW=None, peak_cold_MW=None):
    """Heating and cooling demand of the brief's two daily CSV files for 2027, scaled to peak_heat_MW / peak_cold_MW if given (else
    the files as they are, 30 / 10 MW): peak MW, peak dates, annual GWh and the cooling season (first and last day with cold
    demand). Data from the brief [D]."""
    _peaks(peak_heat_MW, peak_cold_MW)
    h, c = year.scaled(year.heat, peak_heat_MW), year.scaled(year.cold, peak_cold_MW)
    season = c[c > 0].index
    return r2({"heat_peak_MW": h.max(), "heat_peak_date": str(h.idxmax().date()), "heat_GWh": gwh(h), "heat_min_MW": h.min(),
            "cold_peak_MW": c.max(), "cold_peak_date": str(c.idxmax().date()), "cold_GWh": gwh(c),
            "cooling_season_start": str(season[0].date()), "cooling_season_end": str(season[-1].date()), "tag": "[D]"})


def doublet_point(q_m3h, t_return_c, depth_m=DEPTH_M, esp_depth_m=None):
    """One doublet at flow q_m3h (50-300 m3/h) and network return t_return_c (30-70 C), reservoir at depth_m (default 2500 m),
    24-stage ESP to a 10 bar wellhead, exchanger then a brine-source heat pump lifting to 100 C: wellhead T, MW by source, ESP kW,
    COP, whether the pump is inside its 158-342 m3/h curve. GEMINI models plus our exchanger and Lorenz heat pump [C, A]."""
    _need("q_m3h", q_m3h, Q_MIN_M3H, Q_MAX_M3H)
    _need("t_return_c", t_return_c, 30, 70)
    _need("depth_m", depth_m, 1500, 4000)
    w = Producer(depth_m=float(depth_m), stages=24, esp_depth_m=_esp(esp_depth_m))
    p = doublet_at(w, float(q_m3h), float(t_return_c))
    return r2({"q_m3h": q_m3h, "depth_m": depth_m, "esp_freq_Hz": p["freq_hz"], "T_wellhead_C": p["T_wh_C"], "exchanger_MW": p["MW_hx"],
               "heat_pump_MW": p["MW_hp"], "heat_pump_electricity_MW": p["MW_el_hp"], "boiler_lift_MW": p["MW_boiler_lift"],
               "total_heat_MW": p["MW_out"], "esp_kW": p["kW_esp"], "heat_pump_COP": p["cop"],
               "in_pump_envelope": bool(w.q_min <= q_m3h <= w.q_max), "tag": "[C, A]"}) | gemini(PRODUCER_GEMINI)


def injector_point(q_m3h, depth_m=DEPTH_M):
    """Injection well at q_m3h (50-300 m3/h), reservoir at depth_m (default 2500 m), brine back at wellhead T minus 40 K: cold
    injectivity, bottomhole and wellhead pressure needed, injection pump kW, margin to the SodM 0.135 bar/m limit at that depth,
    and the wellhead pressure GEMINI's own friction sign would give [C, A]."""
    _need("q_m3h", q_m3h, Q_MIN_M3H, Q_MAX_M3H)
    _need("depth_m", depth_m, 1500, 4000)
    r = injector_at(float(q_m3h), float(depth_m))
    return r2({"q_m3h": q_m3h, "depth_m": depth_m, "T_inj_C": r["T_inj_C"], "injectivity_m3h_per_bar": r["II"], "p_bottomhole_bar": r["p_bh_req_bar"],
               "p_wellhead_bar": r["p_wh_bar"], "p_wellhead_gemini_sign_bar": r["p_wh_gemini_sign_bar"],
               "pump_kW": r["pump_kW"], "sodm_limit_bar": r["sodm_limit_bar"], "sodm_margin_bar": r["sodm_margin_bar"], "tag": "[C, A]"}) \
        | gemini(INJECTOR_GEMINI + ["producer for the brine T: " + ", ".join(PRODUCER_GEMINI)])


def heat_pump_point(t_brine_in_c, t_water_in_c, brine_m3h, water_m3h, t_brine_floor_c=None):
    """GEMINI's own heat pump (HeatpumpBasic, Lorenz mode, via our HeatPumpLift) lifting district water at t_water_in_c (40-99 C,
    water_m3h 50-600 m3/h) to 100 C on brine at t_brine_in_c (40-90 C, brine_m3h 50-600 m3/h) cooled no lower than t_brine_floor_c
    (the wellhead T - 40 K; omitted = t_brine_in_c - 40 K, right only with no exchanger upstream): COP, heat and electricity MW,
    brine and water out, and whether the floor binds (then the water falls short of 100 C). A cross-check of the plant tables, not
    used by the code plan [C, A]."""
    _need("t_brine_in_c", t_brine_in_c, 40, 90)
    _need("t_water_in_c", t_water_in_c, 40, 99)
    _need("brine_m3h", brine_m3h, 50, 600)
    _need("water_m3h", water_m3h, 50, 600)
    floor = t_brine_in_c - DT_BRINE_MAX_K if t_brine_floor_c is None else t_brine_floor_c
    _need("t_brine_floor_c", floor, t_brine_in_c - DT_BRINE_MAX_K - 50, t_brine_in_c)
    hp = HeatPumpLift()
    hp.calculate_output({"T_brine_in_C": t_brine_in_c, "brine_flow_m3h": brine_m3h, "T_brine_floor_C": floor,
                         "T_water_in_C": t_water_in_c, "water_flow_m3h": water_m3h})
    y = hp.get_output()
    return r2({"COP": y["COP"], "Q_th_MW": y["Q_th_MW"], "P_el_MW": y["P_el_MW"], "Q_brine_MW": y["Q_brine_MW"],
               "T_brine_floor_C": floor, "T_brine_out_C": y["T_brine_out_C"], "T_water_out_C": y["T_water_out_C"], "floor_binds": y["floor_binds"],
               "eta_lorenz": hp.parameters["eta_lorenz"], "tag": "[C, A]"}) \
        | gemini(["HeatpumpBasic (Lorenz) via HeatPumpLift, floor-branch root fixed"])
