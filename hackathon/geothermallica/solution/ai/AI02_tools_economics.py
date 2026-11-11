"""Cost and design tools: economics, layout and storage alternatives, gas, lifetime and the optimiser."""
from AI02_tools_common import _esp, _heat, _mode, _need, _peaks, gwh, r2
from AI02_tools_gemini import PRODUCER_GEMINI, gemini
from geo.common import DEPTH_M, Q_MAX_M3H, Q_MIN_M3H
from geo.well import Producer
from geo import cost, gas, lifetime, optimise, storage, year


def economics(n_doublets, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, esp_depth_m=None, outage_mode="staggered",
              gas_handling=None):
    """Cost of 1-3 doublets at a 30-70 C return over 2027, reservoir at depth_m (default 2500 m; doublet price from the ThermoGIS
    well-cost curve at that depth, 9.33 MEUR at 2500 m), demand scaled to the given peaks: CAPEX in MEUR by item (doublets, heat
    pump, 16 MW backup boiler, chillers, tower, absorption), annual cost in MEUR, levelised cost of heat lcoh_EUR_MWh (doublets,
    heat pump, boiler, ESP and injection electricity, gas, CO2) and of cold lcoc_EUR_MWh, electricity, gas; CO2 kt from the boiler gas
    (co2_kt), grid electricity at 0.3 kg/kWh, the associated gas as handled by gas_handling (vent, flare, engine, boiler or
    reinject; omit for the plan's choice: the gas rule reinjects when that adds under 1 % to the LCoH, else the engine, and says
    why in gas_choice; reinject adds its compression electricity, associated_gas_compression_GWh, to the bill and the grid CO2)
    and the total; 5.2 % real, 30/20 yr lives, sourced prices [C, L, A]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _peaks(peak_heat_MW, peak_cold_MW)
    _need("depth_m", depth_m, 1500, 4000)
    if gas_handling is not None and gas_handling not in gas.OPTIONS:
        raise ValueError(f"gas_handling={gas_handling} not one of {gas.OPTIONS}")
    e = cost.economics(int(n_doublets), float(t_return_c), peak_heat_MW, peak_cold_MW, depth_m=float(depth_m), esp_depth_m=_esp(esp_depth_m),
                       outage_mode=_mode(outage_mode), gas_handling=gas_handling)
    cap, ann = e["capex_MEUR"], e["annual_cost_MEUR"]
    flat = {**{f"capex_{k}_MEUR": v for k, v in cap.items()},
            **{f"annual_{side}_{k}_MEUR": v for side in ("heating", "cooling") for k, v in ann[side].items()},
            "annual_total_MEUR": ann["total"]}
    keys = ("n_doublets", "heat_served_GWh", "cold_served_GWh", "lcoh_EUR_MWh", "lcoc_EUR_MWh", "electricity_GWh", "gas_GWh", "co2_kt",
            "co2_electricity_kt", "co2_associated_gas_kt", "co2_total_kt", "gas_handling", "associated_gas_q_m3h",
            "associated_gas_electricity_GWh", "associated_gas_heat_GWh", "associated_gas_compression_GWh", "esp_GWh", "outage_mode")
    return {**r2({**{k: e[k] for k in keys}, **flat}), **({"gas_choice": e["gas_choice"]} if "gas_choice" in e else {}),
            "tag": "[C]", "basis": e["basis"]}


def layout_compare(n_doublets, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, esp_depth_m=None):
    """Price the two ways to reach 100 C for 1-3 doublets at a 30-70 C return, reservoir at depth_m (default 2500 m), demand scaled
    to the given peaks: B = exchanger then a brine-source heat pump (our design), A = exchanger then a gas boiler lifts the
    network water from wellhead T minus 3 K to 100 C (no heat pump); per layout LCoH EUR/MWh, boiler and gas GWh, CO2 kt (boiler gas,
    and co2_total_kt with grid electricity and associated gas),
    electricity GWh, geothermal share, heat-pump and total CAPEX MEUR; chosen = the lower LCoH, delta_lcoh_EUR_MWh = A minus B
    [C]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _peaks(peak_heat_MW, peak_cold_MW)
    _need("depth_m", depth_m, 1500, 4000)
    out, esp = {}, _esp(esp_depth_m)
    for hp, key in ((True, "B"), (False, "A")):
        e = cost.economics(int(n_doublets), float(t_return_c), peak_heat_MW, peak_cold_MW, depth_m=float(depth_m), heat_pump=hp, esp_depth_m=esp)
        d = year.heating_year(int(n_doublets), float(t_return_c), peak_heat_MW=peak_heat_MW, depth_m=float(depth_m), heat_pump=hp, esp_depth_m=esp)
        out[key] = r2({"layout": e["layout"], "lcoh_EUR_MWh": e["lcoh_EUR_MWh"], "boiler_GWh": gwh(d.boiler),
                       "boiler_share_pct": 100 * gwh(d.boiler) / gwh(d.demand - d.unmet), "gas_GWh": e["gas_GWh"], "co2_kt": e["co2_kt"],
                       "co2_electricity_kt": e["co2_electricity_kt"], "co2_total_kt": e["co2_total_kt"],
                       "electricity_GWh": e["electricity_GWh"], "geothermal_share_pct": 100 * (gwh(d.geo) + gwh(d.hp) - gwh(d.el_hp)) / gwh(d.demand),
                       "capex_heat_pump_MEUR": e["capex_MEUR"]["heat_pump"], "capex_total_MEUR": e["capex_MEUR"]["total"]})
    delta = round(out["A"]["lcoh_EUR_MWh"] - out["B"]["lcoh_EUR_MWh"], 2)
    return {"n_doublets": int(n_doublets), "t_return_c": float(t_return_c), "B": out["B"], "A": out["A"],
            "chosen": out["B"]["layout"] if delta > 0 else out["A"]["layout"], "delta_lcoh_EUR_MWh": delta, "tag": "[C]"}


def storage_point(n_doublets, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, outage_days=7, esp_depth_m=None):
    """A steel heat-storage tank as the alternative to the 16 MW backup boiler for 1-3 doublets at a 30-70 C return, reservoir at
    depth_m (default 2500 m), heat demand scaled to peak_heat_MW: tank MWh for the peak with every doublet on, tank MWh, number of
    175 MWh / 2.9 MW units and MEUR for one doublet out over outage_days (1-35, default 7 [A]) in winter at 3 000 EUR/MWh [L,
    DEA], the boiler's MEUR, and a verdict sentence; daily data make the peak tank a lower bound [C, L, A]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _peaks(peak_heat_MW, None)
    _need("depth_m", depth_m, 1500, 4000)
    _need("outage_days", outage_days, 1, 35)
    s = storage.storage_case(int(n_doublets), float(t_return_c), peak_heat_MW, depth_m=float(depth_m), outage_days=int(outage_days),
                             esp_depth_m=_esp(esp_depth_m))
    return r2(s)


def gas_point(q_m3h, depth_m=DEPTH_M, esp_depth_m=None):
    """Gas dissolved in the brine of one doublet at q_m3h (50-300 m3/h), reservoir at depth_m (default 2500 m): GLR 0.8 Nm3/m3 of
    80/20 CH4/CO2 [D] as gas, CH4 and CO2 Nm3/h, CH4 fuel power MW (LHV), CO2 kg/h in the gas, the same per year over 330
    operating days, a Henry's-law bubble point (pure water, not a PVT model; salt raises it) against the ESP intake pressure
    (free_gas_at_intake true means gas breaks out before the pump), and five handling options (vent, flare, gas engine, site boiler,
    reinjection) with CO2 t/yr, energy credit or compression duty; the chosen option (gas engine) in kt and GWh per doublet-year
    against the ESP electricity at the same flow [C, L, A]."""
    _need("q_m3h", q_m3h, Q_MIN_M3H, Q_MAX_M3H)
    _need("depth_m", depth_m, 1500, 4000)
    g = gas.gas_at(float(q_m3h), float(depth_m))
    w = Producer(depth_m=float(depth_m), stages=24, esp_depth_m=_esp(esp_depth_m))
    f = w.freq_for_wellhead(float(q_m3h))
    run = w.run(float(q_m3h), f if f is not None else 60.0)
    p_in = run["p_esp_intake_bar"]
    hours = gas.OPERATING_DAYS * 24
    opts = gas.handling_options(float(q_m3h), float(depth_m), esp_kW=run["esp_electric_kW"])
    ch = next(o for o in opts if o["option"] == gas.GAS_HANDLING)
    return {**r2({**g, "depth_m": depth_m, "gas_Mm3_per_yr": g["gas_Nm3h"] * hours / 1e6, "CH4_GWh_LHV_per_yr": g["CH4_MW_LHV"] * hours / 1000,
                  "CO2_in_gas_t_per_yr": g["CO2_in_gas_kg_h"] * hours / 1000, "esp_depth_m": w.esp_depth_m, "p_esp_intake_bar": p_in,
                  "intake_margin_bar": p_in - g["p_bubble_bar"],
                  "free_gas_at_intake": bool(p_in < g["p_bubble_bar"]), "free_gas_at_intake_upper_bound": bool(p_in < g["p_bubble_upper_bar"]),
                  "gas_handling": gas.GAS_HANDLING, "handling_CO2_kt_per_yr": ch["CO2e_t_per_yr"] / 1000,
                  "handling_electricity_GWh_per_yr": ch["electricity_MWh_per_yr"] / 1000, "handling_heat_GWh_per_yr": ch["heat_MWh_per_yr"] / 1000,
                  "esp_GWh_per_yr": run["esp_electric_kW"] * hours / 1e6}),
            "handling_options": [r2(o) for o in opts],
            "handling_reason": "gas engine: same CO2 as a flare, its electricity covers the ESP load; the organisers allow any option",
            "CH4_mol_per_kg": round(g["CH4_mol_per_kg"], 4), "CO2_mol_per_kg": round(g["CO2_mol_per_kg"], 4),
            "basis": gas.BASIS + f"; handling: GWP100 fossil CH4 {gas.GWP100_CH4_FOSSIL} [L, GHG Protocol AR6 table], CHP electric share 1/3 "
                     f"[D, GEMINI chp.py], CHP total {gas.CHP_TOTAL_EFF} [A], separator {gas.P_SEPARATOR_BAR:g} bar [A], "
                     "permit for reinjection [A]", "tag": "[C, L, A]"} | gemini(PRODUCER_GEMINI)


def lifetime_point(n_doublets, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, spacing_m=1500, doublet_spacing_m=None, esp_depth_m=None):
    """Lifetime of 1-3 doublets at a 30-70 C return, reservoir at depth_m (default 2500 m), heat demand scaled to peak_heat_MW:
    Gringarten-Sauty thermal breakthrough t_BT in years at the mean running flow of heating_year and at the 300 m3/h cap for
    producer-injector spacing_m (500-3000 m, default 1500 m), the spacing that gives 30 and 50 yr, and the extra injector pressure
    from the neighbouring doublets placed side by side doublet_spacing_m apart (default = spacing_m) against the SodM margin [C,
    L, A]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _peaks(peak_heat_MW, None)
    _need("depth_m", depth_m, 1500, 4000)
    _need("spacing_m", spacing_m, 500, 3000)
    _need("doublet_spacing_m", doublet_spacing_m, 300, 5000)
    d = _heat(int(n_doublets), float(t_return_c), peak_heat_MW, float(depth_m), esp_depth_m)
    q_mean = float(d.q_m3h[d.doublets_on > 0].mean())
    dp = lifetime.interference_bar(int(n_doublets), Q_MAX_M3H, float(spacing_m), doublet_spacing_m)
    sodm = min(year.injector_rows(float(depth_m)), key=lambda r: r["sodm_margin_bar"])["sodm_margin_bar"]
    return {**r2({"n_doublets": int(n_doublets), "spacing_m": spacing_m,
                  "doublet_spacing_m": spacing_m if doublet_spacing_m is None else doublet_spacing_m,
                  "q_mean_running_m3h": q_mean, "t_bt_mean_flow_yr": lifetime.t_bt_yr(q_mean, float(spacing_m)),
                  "t_bt_300m3h_yr": lifetime.t_bt_yr(Q_MAX_M3H, float(spacing_m)),
                  "spacing_for_30yr_at_300m3h_m": lifetime.spacing_for_yr(30, Q_MAX_M3H),
                  "spacing_for_50yr_at_300m3h_m": lifetime.spacing_for_yr(50, Q_MAX_M3H), "interference_worst_injector_bar": max(dp),
                  "sodm_margin_bar": sodm, "sodm_margin_after_interference_bar": sodm - max(dp)}),
            "interference_per_injector_bar": [round(x, 2) for x in dp], "basis": lifetime.BASIS, "tag": "[C, L, A]"}


def optimise_point(peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, priority="lcoh", esp_depth_m=None, max_doublets=3):
    """Search doublet count (1-3), network return (50-70 C), ESP depth (300-1250 m) and the associated-gas handling (gas engine or
    reinjection) for the lowest LCoH and the lowest CO2 at once, reservoir at depth_m (default 2500 m), demand scaled to the given
    peaks: a coarse grid then a pattern search, feasible = all 17 checks pass and the doublet rule (no unmet heat, peak covered,
    boiler at most 5 %); returns the Pareto front (rows no other beats on both LCoH and CO2, each with gas_handling and the
    breakthrough time), best_lcoh and best_co2 rows, best_on_priority for priority 'lcoh' (the gas rule's row: reinject when it
    adds under 1 % to the cheapest LCoH, else the engine) or 'co2', gas_choice = the rule's sentence, the number of designs
    evaluated and the seconds taken [C]."""
    _peaks(peak_heat_MW, peak_cold_MW)
    _need("depth_m", depth_m, 1500, 4000)
    if priority not in ("lcoh", "co2"):
        raise ValueError(f"priority must be 'lcoh' or 'co2', got {priority!r}")
    _need("max_doublets", max_doublets, 1, 3)
    r = optimise.optimise(peak_heat_MW, peak_cold_MW, float(depth_m), _esp(esp_depth_m), n_max=int(max_doublets))
    row = lambda p: None if p is None else r2({k: v for k, v in p.items() if k != "fails"})
    return {"priority": priority, "front": [row(p) for p in r["front"]], "best_lcoh": row(r["best_lcoh"]), "best_co2": row(r["best_co2"]),
            "best_on_priority": row((r["best_rule"] or r["best_lcoh"]) if priority == "lcoh" else r["best_co2"]),
            "gas_choice": r["gas_choice"], "n_evaluated": r["n_evaluated"],
            "n_feasible": r["n_feasible"], "seconds": r["seconds"], "basis": r["basis"], "tag": "[C]"}
