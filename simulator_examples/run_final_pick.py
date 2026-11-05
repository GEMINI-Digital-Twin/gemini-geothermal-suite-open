"""Numbers for the final pick: aquifer cold storage design on real weather.

4 Nov 2026 (after the external review, Sa'eed's go): the wells go 3.1 -> 3.2 km and the
backup chiller 9 -> 10 MW, to buy margin. At 3.1 km the zero-boiler year rested on a
~0.5 K wellhead margin and the 9 MW chiller missed cooling in warm years with +1-2 K
(KNMI 2020, 2014) or +10 % cooling. 3.2 km + 10 MW meets demand in all of those.

The final pick (chosen 31 Oct 2026) keeps the screened plant (2 doublets
at 3.1 km, HEX, CHP on the co-produced gas, gas boiler) and replaces the
12 MW chiller with an air-cooled screw chiller of 6 MW, a free-cooling
economizer and 3 shallow aquifer cold-storage (ATES) well pairs. It is run
on a weather year with the wells' corrosion mitigation priced and the
two doublets taking their 35-day stops at different times in summer
(staggered maintenance, Sa'eed's choice of 2 Nov after the organisers said
the schedule is ours; ``geothermal_outage_common`` = 0) and a 33 MW boiler,
10 % above the 30 MW heating peak, so that even a whole-source trip on the
coldest day is covered. That is the basis of the report's headline. The
doublet operating rules (start/stop times, start cost, wellbore warm-up) are
a variant. Every case goes through the agent's ToolBox, so it passes the
physics gate (incl. the GEMINI Solver cross-check) and gets a run id.

    PYTHONPATH=src python simulator_examples/run_final_pick.py \
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt \
        --year 2025 [--mc 400 [--mc-weather]]

(``--epw <file>`` takes an EnergyPlus typical year instead; the IWEC file used on
1 Nov may not be redistributed and is not in the repository. ``--inputs DIR`` runs
on other demand files.)
``--mc-weather`` also samples the weather year (one of the 35 KNMI years per sample).

Writes simulator_examples/outputs/final_pick/: runs.csv, runs.md, pick.json
(KPIs, CAPEX and cost terms, reference plant, payback and NPV),
pick_daily.csv and, with ``--mc``, the Monte Carlo, base case and tornado
on the sourced price basis (gemini_uncertainty), plus fig_tornado_pick.png.
"""

import argparse
import csv
import json
import shutil
import warnings
from pathlib import Path

import pandas as pd

from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.tools import ToolBox, make_design
from gemini_design import prices
from gemini_design.annual import run_year
from gemini_design.challenge import (
    ASSUMPTIONS,
    CHALLENGE,
    CHILLER_TYPES,
    add_inputs_argument,
    default_inputs_dir,
    load_demand,
)
from gemini_design.climate import read_epw_daily, read_knmi_daily, with_climate
from gemini_design.doublet import DoubletHydraulics
from gemini_design.economics import capital_recovery_factor
from gemini_design.plant import Design, Plant

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "final_pick"
EARLIER_PICK = {
    "n_doublets": 2,
    "depth_m": 3100,
    "upgrade": "boiler",
    "cooling": "electric",
    "chp": True,
    "chiller_capacity_mw": 12.0,
}
# Backup chiller: 6 MW covered one ATES well pair out on the IWEC peak day
# (10 MW - (3 - 1) x ~2.35 MW), but on measured KNMI Schiphol weather it
# misses cooling in 12 of 35 years (1991-2025): after warm winters the heat
# balance throttles the cold store to ~1.3 MW and hot days give no free
# cooling. 9 MW is the smallest size (0.5 MW steps) that meets cooling in all
# 35 years (simulator_examples/run_weather_years.py). That was sized in-sample: with
# 2020 weather +2 K it misses 77 MWh, with 2020 cooling +10 % 32 MWh. 10 MW (+~EUR 0.2/MWh)
# meets both (4 Nov stress table, run_stress_margin.py).
PICK = {
    **EARLIER_PICK,
    "depth_m": 3200,  # 3.1 km left ~0.5 K wellhead margin above 100 degC (review, 4 Nov)
    "chiller_type": "air_cooled_screw",
    "free_cooling": True,
    "ates_doublets": 3,
    "chiller_capacity_mw": 10.0,
    # 30 MW (= peak) leaves no headroom if both doublets trip on the coldest day and misses
    # 98 MWh with heating +6 %; 33 MW covers it (run_outage_study.py), ~EUR 0.2/MWh.
    "boiler_capacity_mw": 33.0,
}
# the 2-4 Nov headline, for comparison
PREVIOUS_PICK = {**PICK, "depth_m": 3100, "chiller_capacity_mw": 9.0}
# the cheapest type of design in the full screen: screw chiller + dry cooler, no free
# cooling or ATES, same wells and heat plant as the pick
# (chiller sized at the cooling peak, as in the screen)
SCREW = {
    "n_doublets": 2,
    "depth_m": PICK["depth_m"],
    "upgrade": "boiler",
    "cooling": "electric",
    "chp": True,
    "chiller_type": "screw_dry_cooler",
    "boiler_capacity_mw": PICK["boiler_capacity_mw"],
}
RULES = {"operating_rules": True}
HOURS_PER_DAY = 24.0


def aged_wellbore_multiplier():
    """Heat-loss multiplier the operating-rules runs use for a well in steady flow."""
    from gemini_design.operations import OperatingRules, WellboreModel

    return WellboreModel(ASSUMPTIONS).multiplier(OperatingRules().reference_age_days)


def cases():
    """(label, design request, assumption overrides)."""
    pick = PICK
    return [
        ("final pick", pick, None),
        ("final pick, with operating rules", {**PICK, **RULES}, None),
        (
            "final pick, aged-wellbore heat loss only (no rules)",
            pick,
            {"wellbore_heat_loss_multiplier": aged_wellbore_multiplier()},
        ),
        ("previous headline (3.1 km, 9 MW backup chiller)", PREVIOUS_PICK, None),
        ("2D screw chiller + dry cooler, same wells (no free cooling, no ATES)", SCREW, None),
        ("earlier pick (legacy 12 MW chiller)", EARLIER_PICK, None),
        ("earlier pick + free cooling", {**EARLIER_PICK, "free_cooling": True}, None),
        (
            "air-cooled 12 MW + free cooling, no ATES",
            {**pick, "ates_doublets": 0, "chiller_capacity_mw": 12.0},
            None,
        ),
        ("final pick, ATES well pair cost x2", pick, {"ates_well_pair_cost_eur": 1.2e6}),
        ("final pick, ATES well pair cost x0.5", pick, {"ates_well_pair_cost_eur": 3.0e5}),
        ("final pick, ATES cold losses doubled", pick, {"ates_loss_fraction_per_day": 0.003}),
        (
            "final pick, corrosion mitigation free",
            pick,
            {"corrosion_resistant_liner_cost_eur_per_m": 0.0},
        ),
        ("final pick, 1 doublet", {**pick, "n_doublets": 1}, None),
    ]


def reference_plant(climate, assumptions=ASSUMPTIONS, challenge=CHALLENGE):
    """Gas boiler (30 MW) + air-cooled chiller (12 MW) meeting the same demand.

    Uses the same Plant model with no doublet running, so the boiler buys
    all the gas and the chiller sees the same weather. Ledger prices.
    """
    a = assumptions
    design = Design(
        n_doublets=1,
        depth_m=3100.0,
        upgrade="boiler",
        cooling="electric",
        boiler_capacity_mw=30.0,
        chiller_capacity_mw=12.0,
        chiller_type="air_cooled_screw",
    )
    plant = Plant(design, DoubletHydraulics(3100.0, challenge, a), challenge, a)
    # same daily electricity prices as the pick (None when the daily-price option is off)
    day_prices = prices.daily_prices(climate, a)
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for i, (_, day) in enumerate(climate.iterrows()):
            kw = {}
            if day_prices is not None:
                kw = {"electricity_price": float(day_prices[0][i]),
                      "export_price": float(day_prices[1][i])}
            r = plant.evaluate(
                day["heating_mw"] * 1e6,
                day["cooling_mw"] * 1e6,
                0,
                0.0,
                ambient_c=day["ambient_c"],
                wet_bulb_c=day["wet_bulb_c"],
                **kw,
            )
            rows.append(r)
    daily = pd.DataFrame(rows)
    unmet = (daily["unmet_heat_w"].sum() + daily["unmet_cooling_w"].sum()) / 1e6 * HOURS_PER_DAY
    capex = (
        30.0 * a["boiler_cost_eur_per_mw"]
        + 12.0 * CHILLER_TYPES["air_cooled_screw"]["cost_eur_per_mw"]
    )
    crf = capital_recovery_factor(a["discount_rate"], a["lifetime_years"])
    energy = float(daily["cost_eur_s"].sum()) * 86400.0
    om = capex * a["fixed_om_fraction"]
    delivered = (
        float(daily["heat_delivered_w"].sum() + daily["cooling_delivered_w"].sum())
        / 1e6
        * HOURS_PER_DAY
    )
    return {
        "design": "30 MW gas boiler (90 %) + 12 MW air-cooled screw chiller",
        "unmet_mwh": unmet,
        "purchased_gas_mwh": float(daily["purchased_gas_w"].sum()) / 1e6 * HOURS_PER_DAY,
        "electricity_mwh": float(daily["electricity_w"].sum()) / 1e6 * HOURS_PER_DAY,
        "co2_t_per_year": float(daily["co2_kg_s"].sum()) * 86400.0 / 1000.0,
        "capex_eur": capex,
        "annual_capital_eur": capex * crf,
        "annual_fixed_om_eur": om,
        "annual_energy_cost_eur": energy,
        "lcoe_eur_per_mwh": (capex * crf + om + energy) / delivered,
    }


def payback(pick_econ, ref, assumptions=ASSUMPTIONS):
    """Simple payback and NPV of the pick against the reference plant (ledger prices)."""
    a = assumptions
    extra_capex = pick_econ["capex_eur"]["total"] - ref["capex_eur"]
    pick_running = (
        pick_econ["annual_fixed_om_eur"]
        + pick_econ["annual_energy_cost_eur"]
        + pick_econ.get("annual_start_cost_eur", 0.0)
    )
    ref_running = ref["annual_fixed_om_eur"] + ref["annual_energy_cost_eur"]
    saving = ref_running - pick_running
    annuity = 1.0 / capital_recovery_factor(a["discount_rate"], a["lifetime_years"])
    return {
        "extra_capex_eur": extra_capex,
        "annual_saving_eur": saving,
        "simple_payback_years": extra_capex / saving if saving > 0 else float("inf"),
        "npv_eur": saving * annuity - extra_capex,
        "discount_rate": a["discount_rate"],
        "lifetime_years": a["lifetime_years"],
    }


def pick_kpis(summary, daily):
    """The numbers the report quotes for the final pick."""
    e, k, econ = summary["energy_mwh"], summary["kpi"], summary["economics"]
    heat = e["heating_delivered"]
    hex_heat = float(daily["hex_heat_w"].sum()) / 1e6 * HOURS_PER_DAY
    chiller_cooling = e["cooling_delivered"] - e["free_cooling"] - e["ates_cooling"]
    active = daily[daily["n_active"] > 0]
    return {
        "design": summary["design"]["name"],
        "all_hard_constraints_met": summary["all_hard_constraints_met"],
        "days_with_violations": int((daily["violations"].fillna("") != "").sum()),
        "heating_demand_mwh": e["heating_demand"],
        "heating_delivered_mwh": heat,
        "cooling_demand_mwh": e["cooling_demand"],
        "cooling_delivered_mwh": e["cooling_delivered"],
        "heat_share_hex_chp_boiler": [
            hex_heat / heat,
            e["chp_heat"] / heat,
            e["boiler_heat"] / heat,
        ],
        "cooling_free_ates_chiller_mwh": [e["free_cooling"], e["ates_cooling"], chiller_cooling],
        "max_chiller_load_mw": float(
            (daily["cooling_delivered_w"] - daily["free_cooling_w"] - daily["ates_cooling_w"]).max()
        )
        / 1e6,
        "mean_chiller_cop": (
            float(daily["electric_chiller_cop"].dropna().mean())
            if "electric_chiller_cop" in daily
            else None
        ),
        "purchased_gas_mwh": e["purchased_gas_fuel"],
        "associated_gas_flared_mwh": e["associated_gas_flared"],
        "electricity_used_mwh": e["electricity"],
        "chp_electricity_mwh": e["chp_electricity"],
        "grid_import_mwh": e["grid_import"],
        "grid_export_mwh": e["grid_export"],
        "co2_t_per_year": k["co2_t_per_year"],
        "max_flow_per_doublet_m3h": k["max_flow_per_doublet_m3h"],
        "min_running_flow_m3h": float(active["flow_per_doublet_m3h"].min()),
        "max_brine_cooling_k": k["max_brine_cooling_k"],
        "doublet_operating_days": k["doublet_operating_days"],
        "geothermal_source_days": k.get("geothermal_source_days"),
        "days_without_geothermal": k.get("days_without_geothermal"),
        "esp_setting_depth_m": k["esp_setting_depth_m"],
        "max_esp_dp_bar": k["max_esp_dp_bar"],
        "max_injector_wellhead_pressure_bar": k["max_injector_wellhead_pressure_bar"],
        "wellhead_temperature_c": [
            float(active["wellhead_temperature_c"].min()),
            float(active["wellhead_temperature_c"].max()),
        ],
        "capex_eur": econ["capex_eur"],
        "annual_capital_eur": econ["annual_capital_eur"],
        "annual_fixed_om_eur": econ["annual_fixed_om_eur"],
        "annual_energy_cost_eur": econ["annual_energy_cost_eur"],
        "annual_start_cost_eur": econ.get("annual_start_cost_eur", 0.0),
        "annual_total_cost_eur": econ["annual_total_cost_eur"],
        "lcoe_eur_per_mwh": econ["lcoe_eur_per_mwh"],
        "ates": summary.get("ates"),
        "operations": summary.get("operations"),
    }


def run_cases(climate, ws):
    """Run every case through the ToolBox; return result rows and the pick's run id."""
    ledger, notes = RunLedger(ws), ProjectNotes(ws)
    rows = []
    for label, request, overrides in cases():
        tb = ToolBox(climate, ledger, notes, ws, workers=1)
        req = dict(request)
        if overrides:
            req["assumptions"] = overrides
        head = tb.call("run_design", req)
        if "error" in head:
            raise RuntimeError(f"{label}: {head}")
        s = ledger.summary(head["run_id"])
        e, econ = s["energy_mwh"], s["economics"]
        rows.append(
            {
                "case": label,
                "run_id": head["run_id"],
                "design": head["design"],
                "operating_rules": bool(request.get("operating_rules")),
                "physics_gate": head["physics_gate"],
                "meets_all_hard_rules": head["meets_all_hard_rules"],
                "unmet_cooling_mwh": round(e["unmet_cooling"], 1),
                "free_cooling_mwh": round(e.get("free_cooling", 0.0)),
                "ates_cooling_mwh": round(e.get("ates_cooling", 0.0)),
                "grid_import_mwh": round(head["grid_import_mwh"]),
                "doublet_starts": head.get("doublet_starts", ""),
                "co2_t_per_year": round(head["co2_t_per_year"]),
                "capex_meur": round(head["capex_meur"], 2),
                "lcoe_eur_per_mwh": round(econ["lcoe_eur_per_mwh"], 2),
            }
        )
        print(
            f"{head['run_id']} {label}: {econ['lcoe_eur_per_mwh']:.2f} EUR/MWh, "
            f"{head['co2_t_per_year']:.0f} t, gate {head['physics_gate']}"
        )
    return rows


def monte_carlo_study(climate, n_samples, out, weather=None):
    """Sourced-basis base case, Monte Carlo and tornado.

    Designs: the pick, the previous headline (3.1 km, 9 MW backup chiller) and the
    2D screw + dry cooler design on the same wells (the cheapest type in the screen),
    all on the same samples. ``weather`` ({year: climate}) also samples the weather year.
    """
    from gemini_uncertainty import plots
    from gemini_uncertainty.study import base_case, compare, monte_carlo, summarise, tornado

    peaks = float(climate["heating_mw"].max()), float(climate["cooling_mw"].max())
    pick = make_design(PICK, *peaks)
    previous = make_design(PREVIOUS_PICK, *peaks)
    screw = make_design(SCREW, *peaks)
    designs = [pick, previous, screw]
    base = base_case(designs, climate)
    base.to_csv(out / "sourced_base_case.csv", index=False)
    results, _ = monte_carlo(designs, climate, n_samples, weather=weather)
    results.to_csv(out / "mc_results.csv", index=False)
    summary = summarise(results)
    summary.to_csv(out / "mc_summary.csv", index=False)
    paired = {
        "pick_vs_previous": compare(results, pick.name, previous.name),
        "pick_vs_screw": compare(results, pick.name, screw.name),
    }
    tor = tornado(pick, climate)
    tor.to_csv(out / "tornado_pick.csv", index=False)
    plots.tornado_chart(tor, pick.name, out / "fig_tornado_pick.png")
    return {
        "n_samples": n_samples,
        "sourced_base_case": base[
            ["design", "demand_met", "lcoe_eur_per_mwh", "co2_t_per_year", "capex_meur"]
        ].to_dict("records"),
        "summary": summary.to_dict("records"),
        "weather_sampled": sorted(weather) if weather else None,
        "paired": paired,
        "tornado_top6": tor.head(6)[["parameter", "lcoe_low", "lcoe_high", "lcoe_swing"]].to_dict(
            "records"
        ),
    }


def main():
    """Run the study and write the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--epw", help="EnergyPlus weather file")
    src.add_argument("--knmi", help="KNMI etmgeg daily file")
    parser.add_argument("--year", type=int, default=2025, help="year to take from a KNMI file")
    parser.add_argument("--mc", type=int, default=0, help="Monte Carlo samples (0: skip)")
    add_inputs_argument(parser)
    parser.add_argument(
        "--mc-weather",
        action="store_true",
        help="with --knmi: also sample the weather year (every full year in the file)",
    )
    args = parser.parse_args()
    weather = read_epw_daily(args.epw) if args.epw else read_knmi_daily(args.knmi, args.year)
    source = Path(args.epw or args.knmi).name + ("" if args.epw else f" ({args.year})")
    climate = with_climate(load_demand(args.inputs), weather, "max")

    shutil.rmtree(OUT / "ws", ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = run_cases(climate, OUT / "ws")
    with open(OUT / "runs.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    cols = list(rows[0])
    lines = [f"# Final pick and variants, weather: {source}", ""]
    lines += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    (OUT / "runs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    peaks = float(climate["heating_mw"].max()), float(climate["cooling_mw"].max())
    pick_design = make_design(PICK, *peaks)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        daily, summary = run_year(pick_design, climate)
    daily.to_csv(OUT / "pick_daily.csv", index=False)
    kpis = pick_kpis(summary, daily)
    gated = rows[0]
    assert abs(gated["lcoe_eur_per_mwh"] - round(kpis["lcoe_eur_per_mwh"], 2)) < 0.011, gated
    ref = reference_plant(climate)
    result = {
        "weather": source,
        "pick_run_id": gated["run_id"],
        "pick": kpis,
        "reference": ref,
        "pick_vs_reference": payback(summary["economics"], ref),
        "co2_avoided_t_per_year": ref["co2_t_per_year"] - kpis["co2_t_per_year"],
    }
    if args.mc:
        weather_years = None
        if args.mc_weather and args.knmi:
            demand = load_demand(args.inputs)
            weather_years = {
                y: with_climate(demand, read_knmi_daily(args.knmi, y), "max")
                for y in range(1991, 2026)
            }
        result["uncertainty"] = monte_carlo_study(climate, args.mc, OUT, weather_years)
    (OUT / "pick.json").write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "pick"}, indent=2, default=float))
    return result


if __name__ == "__main__":
    main()
