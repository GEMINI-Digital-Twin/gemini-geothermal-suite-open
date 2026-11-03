"""GEMINI hackathon tasks 3-5: simulate 2027 for each design candidate, compare and rank.

Run in GEMINI repository root:
    $env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/run_candidates.py

Reads projects/candidates_2027.json, runs the daily model (daily_model.py)
for all 365 days per candidate (base case + each sensitivity), ranks the
candidates (CLAUDE.md ranking rule) and writes to outputs/candidates/:
  <case>/<name>/{daily.csv, summary.json, daily_supply.png},
  <case>/comparison.{csv,md}, ranking.json.
"""

from __future__ import annotations

import copy
import csv
import functools
import json
import subprocess
import time
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from constraints import PASS  # noqa: E402
from daily_model import CANDIDATES_PATH, HP_COP_REL_TOLERANCE, Plant  # noqa: E402
from demand_baseline import load_demand  # noqa: E402
from doublet_model import REPO, ROOT, load_json  # noqa: E402

OUT = ROOT / "outputs" / "candidates"
BASE_CASE = "base"

# Reference palette (dataviz skill, light mode), categorical slots in fixed order.
SURFACE, TEXT, TEXT_2, GRID, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#8a8984"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def annual_summary(candidate: dict, plant: Plant, result: dict) -> dict:
    rows = result["rows"]

    def gwh(key):
        return sum(r[key] for r in rows) * 24 / 1000

    def peak(*keys):
        return max(sum(r[k] for k in keys) for r in rows)

    on = [r for r in rows if r["n_active"] > 0]
    hp_checked = [r for r in rows if r["hp_COP_heatpumpbasic"] is not None]
    hp_agree = [r for r in hp_checked if abs(r["hp_COP_heatpumpbasic"] - r["hp_COP"]) <= HP_COP_REL_TOLERANCE * r["hp_COP"]]
    fail_days = [r for r in rows if not r["constraints_pass"]]
    fail_checks = sorted({c.split("@")[0] for r in fail_days for c in r["constraint_failures"].split(";") if c})
    heat_demand = gwh("heating_demand_MW")
    return {
        "candidate": candidate,
        "heat_pump": plant.hp,
        "esp": plant.settings["esp_options"][candidate["esp"]],
        "esp_max_flow_m3h": plant.max_flow_m3h,
        "esp_setting_depth_m": plant.esp_placement["esp_depth_m"],
        "esp_intake_at_max_flow_bar": plant.esp_placement["intake_bar"],
        "tubing_velocity_at_max_flow_m_s": next(c["value"] for c in plant.engineering if c["check"] == "tubing_velocity"),
        "flow_cap_m3h": plant.flow_cap_m3h,
        "depth_m": plant.depth_m,
        "reservoir_temperature_C": plant.reservoir_temperature_c,
        "reservoir_pressure_bar": plant.reservoir_pressure_bar,
        "drilled_m": 2 * candidate["n_doublets"] * plant.depth_m,  # producer + injector per doublet, vertical
        "maintenance_windows": [f"{s[0]}..{s[-1]}" for s in result["schedule"]],
        "heating_demand_GWh": heat_demand,
        "heat_hex_GWh": gwh("heat_hex_MW"),
        "heat_hp_GWh": gwh("heat_hp_MW"),
        "heat_chp_GWh": gwh("heat_chp_MW"),
        "heat_boiler_produced_gas_GWh": gwh("heat_boiler_produced_gas_MW"),
        "heat_boiler_external_gas_GWh": gwh("heat_boiler_external_gas_MW"),
        "heat_unmet_GWh": gwh("heat_unmet_MW"),
        "geothermal_heat_share": (gwh("heat_hex_MW") + gwh("heat_hp_MW")) / heat_demand,
        "cooling_demand_GWh": gwh("cooling_demand_MW"),
        "cool_absorption_GWh": gwh("cool_absorption_MW"),
        "cool_electric_GWh": gwh("cool_electric_MW"),
        "cool_unmet_GWh": gwh("cool_unmet_MW"),
        "el_load_GWh": gwh("el_load_MW"),
        "el_esp_GWh": gwh("el_esp_MW"),
        "el_injector_GWh": gwh("el_injector_MW"),
        "el_hp_GWh": gwh("el_hp_MW"),
        "el_chiller_GWh": gwh("el_chiller_MW"),
        "el_chp_GWh": gwh("el_chp_MW"),
        "grid_import_GWh": gwh("el_grid_import_MW"),
        "grid_export_GWh": gwh("el_grid_export_MW"),
        "produced_gas_fuel_GWh": gwh("produced_gas_fuel_MW"),
        "produced_gas_chp_GWh": gwh("produced_gas_chp_MW"),
        "produced_gas_boiler_GWh": gwh("produced_gas_boiler_MW"),
        "produced_gas_flared_GWh": gwh("produced_gas_flared_MW"),
        "external_gas_fuel_GWh": gwh("external_gas_fuel_MW"),
        "external_gas_Mm3": sum(r["external_gas_Nm3_day"] for r in rows) / 1e6,
        "emissions_t": sum(r["emission_produced_gas_t"] + r["emission_external_gas_t"] + r["emission_electricity_t"] for r in rows),
        "emissions_produced_gas_t": sum(r["emission_produced_gas_t"] for r in rows),
        "emissions_external_gas_t": sum(r["emission_external_gas_t"] for r in rows),
        "emissions_electricity_t": sum(r["emission_electricity_t"] for r in rows),
        "capacity_MW": {
            "heat_pump_th": peak("heat_hp_MW"),
            "absorption_chiller_cool": peak("cool_absorption_MW"),
            "electric_chiller_cool": peak("cool_electric_MW"),
            "chp_th": peak("heat_chp_MW"),
            "chp_el": peak("el_chp_MW"),
            "boiler_th": peak("heat_boiler_produced_gas_MW", "heat_boiler_external_gas_MW"),  # backup sizing
            "boiler_external_gas_th": peak("heat_boiler_external_gas_MW"),
            "external_gas_fuel": peak("external_gas_fuel_MW"),
        },
        "max_brine_dT_K": max(r["brine_dT_K"] for r in on),
        "flow_min_when_on_m3h": min(r["flow_per_doublet_m3h"] for r in on),
        "flow_max_m3h": max(r["flow_per_doublet_m3h"] for r in on),
        "doublet_days_active": sum(r["n_active"] for r in rows),
        # design attributes, not constraints (organizer clarification 2026-11-01: backup may cover the source outage)
        "days_without_geothermal": sum(1 for r in rows if r["n_active"] == 0),
        "days_all_doublets_in_maintenance": len(set.intersection(*({str(d) for d in span} for span in result["schedule"]))),
        "days_geothermal_meets_need": sum(r["geothermal_meets_need"] for r in rows),
        "days_hex_bypass": sum(r["hex_bypass"] for r in rows),
        "hp_seasonal_COP": gwh("heat_hp_MW") / gwh("el_hp_MW") if gwh("el_hp_MW") else None,
        "hp_days": sum(1 for r in rows if r["hp_COP"] is not None),
        "hp_days_capped": sum(1 for r in rows if r["hp_COP_capped"]),
        "hp_days_heatpumpbasic_checked": len(hp_checked),
        "hp_days_heatpumpbasic_agrees": len(hp_agree),
        "days_failing_daily_checks": len(fail_days),
        "failing_checks": fail_checks,
        "annual_checks": result["annual_checks"],
        "feasible": not fail_days and all(c["status"] == PASS for c in result["annual_checks"]),
    }


# Lexicographic ranking metrics with tie tolerances (absolute, relative): differences
# within max(abs, rel * value) are numerical noise (e.g. the 0.05 K dispatch
# tolerance leaves ~0.004 GWh of external gas), so the next metric decides.
RANK_TIE_TOLERANCE = [
    ("external_gas_fuel_GWh", 0.01, 0.01),
    ("emissions_t", 10.0, 0.01),
    ("grid_import_GWh", 0.01, 0.01),
    ("n_doublets", 0.0, 0.0),
    ("drilled_m", 0.0, 0.0),
]


def tie_tolerance(metric: str, a: float, b: float) -> float:
    _, abs_tol, rel_tol = next(t for t in RANK_TIE_TOLERANCE if t[0] == metric)
    return max(abs_tol, rel_tol * max(abs(a), abs(b)))


def threshold_test(metric: str, base: float, new: float, threshold: float) -> tuple[bool, bool]:
    """(meets, marginal) for a parsimony threshold on ``metric``. The saving must exceed
    threshold * base by more than the metric's tie tolerance; a saving within the tie
    tolerance of the threshold is marginal and counts as NOT meeting it (conservative:
    drilling cost and risk are not modelled). Only a saving that is itself larger than
    the tie tolerance (a real improvement) can be marginal."""
    if base <= 0:
        return False, False
    saving = base - new
    excess = saving - threshold * base
    tol = tie_tolerance(metric, base, new)
    return bool(excess > tol), bool(saving > tol and abs(excess) <= tol)


def _rank_value(s: dict, metric: str) -> float:
    return s["candidate"]["n_doublets"] if metric == "n_doublets" else s[metric]


def deciding_metric(a: dict, b: dict) -> str | None:
    """First ranking metric on which ``a`` and ``b`` differ beyond its tie tolerance."""
    for metric, abs_tol, rel_tol in RANK_TIE_TOLERANCE:
        va, vb = _rank_value(a, metric), _rank_value(b, metric)
        if abs(va - vb) > max(abs_tol, rel_tol * max(abs(va), abs(vb))):
            return metric
    return None


def compare_ranked(a: dict, b: dict) -> int:
    """-1 if ``a`` ranks better than ``b``, 1 if worse, 0 if tied on every metric."""
    metric = deciding_metric(a, b)
    if metric is None:
        return 0
    return -1 if _rank_value(a, metric) < _rank_value(b, metric) else 1


def rank(summaries: list[dict], min_improvement: float, depth_min_improvement: float | None = None) -> dict:
    """CLAUDE.md ranking rule. Returns {name: {"status", "reason", "rank"}}.

    Hard constraints pass/fail; then minimize external gas -> emissions -> net
    grid electricity -> number of doublets -> total drilled metres, where values
    within RANK_TIE_TOLERANCE count as equal. Parsimony: candidates are walked
    in order of (doublets, depth); a candidate with more doublets replaces the
    incumbent only if it ranks better AND improves external gas or emissions by
    >= ``min_improvement``; a deeper one only if it ranks better AND improves
    emissions by >= ``depth_min_improvement`` versus the accepted depth. An
    improvement within the tie tolerance of a threshold does not meet it
    (threshold_test); such candidates are flagged "marginal".
    """
    depth_min_improvement = min_improvement if depth_min_improvement is None else depth_min_improvement
    def key(s):
        return functools.cmp_to_key(compare_ranked)(s)

    def name(s):
        return s["candidate"]["name"]

    def improvement(base, new):
        return (base - new) / base if base > 0 else 0.0

    verdicts = {}
    feasible = [s for s in summaries if s["feasible"]]
    for s in summaries:
        if not s["feasible"]:
            verdicts[name(s)] = {"status": "REJECTED", "reason": f"fails hard constraints: {', '.join(s['failing_checks']) or 'annual checks'}"}

    def level(s):
        return (s["candidate"]["n_doublets"], s.get("depth_m", 2500))

    best_per_level = {}
    for s in sorted(feasible, key=key):
        if level(s) not in best_per_level:
            best_per_level[level(s)] = s
            continue
        b = best_per_level[level(s)]
        decided = deciding_metric(s, b)
        tied = [m for m, _, _ in RANK_TIE_TOLERANCE[: [m for m, _, _ in RANK_TIE_TOLERANCE].index(decided)]] if decided else []
        verdicts[name(s)] = {"status": "REJECTED", "reason": (
            f"same doublet count and depth as {name(b)} but ranks lower on {decided or 'no metric (full tie)'}"
            + (f" (tied within tolerance on {', '.join(tied)})" if tied else "") + f": external gas {s['external_gas_fuel_GWh']:.4f} vs "
            f"{b['external_gas_fuel_GWh']:.4f} GWh, emissions {s['emissions_t']:.0f} vs {b['emissions_t']:.0f} t, "
            f"grid import {s['grid_import_GWh']:.2f} vs {b['grid_import_GWh']:.2f} GWh, "
            f"drilled {s['drilled_m']:.0f} vs {b['drilled_m']:.0f} m")}

    incumbent = None
    for lvl in sorted(best_per_level):
        s = best_per_level[lvl]
        if incumbent is None:
            incumbent = s
            continue
        gas_gain = improvement(incumbent["external_gas_fuel_GWh"], s["external_gas_fuel_GWh"])
        em_gain = improvement(incumbent["emissions_t"], s["emissions_t"])
        better = compare_ranked(s, incumbent) < 0
        tests, details, marginal = [better], [f"ranks {'better' if better else 'not better'} than {name(incumbent)}"], False
        marginal_note = " - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case)"
        if level(s)[0] > level(incumbent)[0]:
            gas_ok, gas_marginal = threshold_test("external_gas_fuel_GWh", incumbent["external_gas_fuel_GWh"], s["external_gas_fuel_GWh"], min_improvement)
            em_ok, em_marginal = threshold_test("emissions_t", incumbent["emissions_t"], s["emissions_t"], min_improvement)
            step_marginal = not (gas_ok or em_ok) and (gas_marginal or em_marginal)
            marginal |= step_marginal
            tests.append(gas_ok or em_ok)
            details.append(f"extra doublet: external gas {gas_gain * 100:+.1f}%, emissions {em_gain * 100:+.1f}% "
                           f"(needs >= {min_improvement * 100:.0f}% on either, beyond the tie tolerance)" + (marginal_note if step_marginal else ""))
        if level(s)[1] > level(incumbent)[1]:
            extra_m = s["drilled_m"] - incumbent["drilled_m"]
            abatement = (incumbent["emissions_t"] - s["emissions_t"]) / extra_m if extra_m else float("nan")
            em_ok, em_marginal = threshold_test("emissions_t", incumbent["emissions_t"], s["emissions_t"], depth_min_improvement)
            step_marginal = not em_ok and em_marginal
            marginal |= step_marginal
            tests.append(em_ok)
            details.append(f"deeper {level(incumbent)[1]:g} -> {level(s)[1]:g} m: emissions {em_gain * 100:+.3f}% "
                           f"(needs >= {depth_min_improvement * 100:.0f}% beyond the tie tolerance), marginal abatement {abatement:.3f} t CO2/yr "
                           f"per extra metre drilled" + (marginal_note if step_marginal else ""))
        detail = "; ".join(details)
        if all(tests):
            verdicts[name(incumbent)] = {"status": "REJECTED", "reason": f"superseded by {name(s)}: {detail}"}
            incumbent = s
        else:
            verdicts[name(s)] = {"status": "REJECTED", "reason": f"parsimony rule not met: {detail}", "marginal": marginal}
    if incumbent is not None:
        verdicts[name(incumbent)] = {"status": "ACCEPTED", "reason": (
            f"selected: feasible; external gas {incumbent['external_gas_fuel_GWh']:.4f} GWh, emissions "
            f"{incumbent['emissions_t']:.0f} t, grid import {incumbent['grid_import_GWh']:.2f} GWh, "
            f"{incumbent['candidate']['n_doublets']} doublets, {incumbent['drilled_m']:.0f} m drilled")}

    # Final rank follows the verdict: selected first, then the rest by the lexicographic key.
    order = sorted(summaries, key=lambda s: (verdicts[name(s)]["status"] != "ACCEPTED", not s["feasible"], key(s)))
    for i, s in enumerate(order, 1):
        verdicts[name(s)]["rank"] = i
    return verdicts


def plot_supply(title: str, rows: list[dict], schedule, path):
    days = [datetime.fromisoformat(r["date"]) for r in rows]
    fig, (ax_h, ax_c) = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True, facecolor=SURFACE)
    panels = [
        (ax_h, "Heating supply vs demand (MW, daily average)",
         [("HEX (geothermal)", "heat_hex_MW"), ("Heat pump", "heat_hp_MW"), ("CHP, produced gas", "heat_chp_MW"),
          ("Boiler, external gas", "heat_boiler_external_gas_MW"), ("Boiler, produced gas", "heat_boiler_produced_gas_MW")],
         "heating_demand_MW", "Heating demand", "upper center"),
        (ax_c, "Cooling supply vs demand (MW, daily average)",
         [("Absorption chiller (hot brine)", "cool_absorption_MW"), ("Electric chiller", "cool_electric_MW")],
         "cooling_demand_MW", "Cooling demand", "upper left"),
    ]
    for ax, panel_title, series, demand_key, demand_label, legend_loc in panels:
        ax.set_facecolor(SURFACE)
        for i, span in enumerate(schedule):
            ax.axvspan(datetime.fromisoformat(str(span[0])), datetime.fromisoformat(str(span[-1])), color=MUTED, alpha=0.12, lw=0,
                       label="Doublet maintenance" if i == 0 else None)
        ax.stackplot(days, *[[r[key] for r in rows] for _, key in series], labels=[label for label, _ in series],
                     colors=SERIES[: len(series)], edgecolor=SURFACE, linewidth=0.6)
        ax.plot(days, [r[demand_key] for r in rows], color=TEXT, lw=1.5, label=demand_label)
        ax.set_title(panel_title, loc="left", color=TEXT, fontsize=11)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=TEXT_2, labelsize=9)
        ax.set_ylim(bottom=0)
        ax.legend(loc=legend_loc, ncol=1 if legend_loc == "upper left" else 3, frameon=False, fontsize=9, labelcolor=TEXT_2)
    ax_c.xaxis.set_major_locator(mdates.MonthLocator())
    ax_c.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.suptitle(title, x=0.01, ha="left", color=TEXT, fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


COMPARISON = [
    ("Doublets / ESP / UA", lambda s: f"{s['candidate']['n_doublets']} / s={s['esp']['flow_scale']} ({s['esp']['no_stages']} st) / {s['candidate']['hex_ua_W_K'] / 1e3:.0f} kW/K"),
    ("Heat pump (eta, COP cap)", lambda s: f"{s['heat_pump']['eta_lorenz']}, {s['heat_pump'].get('cop_cap') or 'none'}"),
    ("Unmet heat / cooling (GWh)", lambda s: f"{s['heat_unmet_GWh']:.3f} / {s['cool_unmet_GWh']:.3f}"),
    ("Heat: HEX / HP / CHP / boiler-ext (GWh)", lambda s: f"{s['heat_hex_GWh']:.1f} / {s['heat_hp_GWh']:.1f} / {s['heat_chp_GWh']:.1f} / {s['heat_boiler_external_gas_GWh']:.2f}"),
    ("Cooling: absorption / electric (GWh)", lambda s: f"{s['cool_absorption_GWh']:.2f} / {s['cool_electric_GWh']:.2f}"),
    ("External gas (GWh fuel / Mm3)", lambda s: f"{s['external_gas_fuel_GWh']:.4f} / {s['external_gas_Mm3']:.4f}"),
    ("Produced gas: CHP / boiler / flared (GWh fuel)", lambda s: f"{s['produced_gas_chp_GWh']:.2f} / {s['produced_gas_boiler_GWh']:.2f} / {s['produced_gas_flared_GWh']:.2f}"),
    ("Electricity load (GWh): ESP / inj / HP / chiller", lambda s: f"{s['el_esp_GWh']:.2f} / {s['el_injector_GWh']:.3f} / {s['el_hp_GWh']:.2f} / {s['el_chiller_GWh']:.2f}"),
    ("CHP electricity (GWh)", lambda s: f"{s['el_chp_GWh']:.2f}"),
    ("Net grid import / export (GWh)", lambda s: f"{s['grid_import_GWh']:.2f} / {s['grid_export_GWh']:.2f}"),
    ("HP seasonal COP (days at cap)", lambda s: f"{s['hp_seasonal_COP']:.2f} ({s['hp_days_capped']})" if s["hp_seasonal_COP"] else "-"),
    ("Emissions (t CO2/yr): total", lambda s: f"{s['emissions_t']:.0f}"),
    ("  produced gas / external gas / grid el.", lambda s: f"{s['emissions_produced_gas_t']:.0f} / {s['emissions_external_gas_t']:.0f} / {s['emissions_electricity_t']:.0f}"),
    ("Peak HP (MWth)", lambda s: f"{s['capacity_MW']['heat_pump_th']:.2f}"),
    ("Peak absorption / electric chiller (MWcool)", lambda s: f"{s['capacity_MW']['absorption_chiller_cool']:.2f} / {s['capacity_MW']['electric_chiller_cool']:.2f}"),
    ("Peak CHP (MWth / MWel) / boiler (MWth)", lambda s: f"{s['capacity_MW']['chp_th']:.2f} / {s['capacity_MW']['chp_el']:.2f} / {s['capacity_MW']['boiler_th']:.2f}"),
    ("Peak external gas (MW fuel)", lambda s: f"{s['capacity_MW']['external_gas_fuel']:.2f}"),
    ("Max brine dT (K)", lambda s: f"{s['max_brine_dT_K']:.3f}"),
    ("Flow when on (m3/h)", lambda s: f"{s['flow_min_when_on_m3h']:.0f}-{s['flow_max_m3h']:.0f}"),
    ("Days geothermal + CHP meet need", lambda s: f"{s['days_geothermal_meets_need']}/365"),
    ("Days without geothermal (all in maintenance)", lambda s: f"{s['days_without_geothermal']} ({s['days_all_doublets_in_maintenance']})"),
    ("Hard constraints (daily + annual)", lambda s: "PASS" if s["feasible"] else f"FAIL ({', '.join(s['failing_checks'])})"),
    ("Rank", lambda s: str(s["ranking"]["rank"])),
    ("Verdict", lambda s: s["ranking"]["status"]),
]


def run_case(case_name: str, settings: dict, heating: dict, cooling: dict, commit: str | None) -> list[dict]:
    folder = OUT / case_name
    folder.mkdir(parents=True, exist_ok=True)
    summaries = []
    for candidate in settings["candidates"]:
        start = time.time()
        plant = Plant(candidate, settings)
        result = plant.simulate_year(heating, cooling)
        summary = annual_summary(candidate, plant, result)
        summary.update(case=case_name, run_utc=datetime.now(timezone.utc).isoformat(), git_commit=commit, runtime_s=time.time() - start)
        cand_folder = folder / candidate["name"]
        cand_folder.mkdir(exist_ok=True)
        with (cand_folder / "daily.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(result["rows"][0]))
            writer.writeheader()
            writer.writerows(result["rows"])
        plot_supply(f"{candidate['name']} ({case_name}): daily 2027 supply by source", result["rows"], result["schedule"], cand_folder / "daily_supply.png")
        summaries.append((summary, cand_folder))
        print(f"[{case_name}] {candidate['name']}: {summary['runtime_s']:.0f} s; "
              f"HeatpumpBasic agrees on {summary['hp_days_heatpumpbasic_agrees']}/{summary['hp_days_heatpumpbasic_checked']} uncapped HP days")

    verdicts = rank([s for s, _ in summaries], settings["ranking"]["extra_doublet_min_improvement"],
                    settings["ranking"]["depth_step_min_improvement"])
    for summary, cand_folder in summaries:
        summary["ranking"] = verdicts[summary["candidate"]["name"]]
        (cand_folder / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    summaries = [s for s, _ in summaries]

    header = ["Metric"] + [s["candidate"]["name"] for s in summaries]
    table = [[label] + [fmt(s) for s in summaries] for label, fmt in COMPARISON]
    with (folder / "comparison.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([header] + table)
    md = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(row) + " |" for row in table]
    md += ["", "Ranking verdicts:"] + [f"- **{s['candidate']['name']}**: {s['ranking']['status']} - {s['ranking']['reason']}" for s in summaries]
    (folder / "comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (folder / "ranking.json").write_text(json.dumps({s["candidate"]["name"]: s["ranking"] for s in summaries}, indent=2), encoding="utf-8")

    print()
    widths = [max(len(str(row[i])) for row in [header] + table) for i in range(len(header))]
    for row in [header] + table:
        print("  ".join(str(cell).ljust(w) for cell, w in zip(row, widths)))
    print("Ranking verdicts:")
    for s in summaries:
        print(f"  {s['candidate']['name']}: {s['ranking']['status']} - {s['ranking']['reason']}")
    print()
    return summaries


def main():
    settings = load_json(CANDIDATES_PATH)
    heating = load_demand("GEMINI_Heating_Demand_Daily_2027.csv", "heating_demand_MWth")
    cooling = load_demand("GEMINI_Cooling_Demand_Daily_2027.csv", "cooling_demand_MWcool")
    commit = git_commit()
    run_case(BASE_CASE, settings, heating, cooling, commit)
    for sensitivity in settings.get("sensitivities", []):
        case_settings = copy.deepcopy(settings)
        case_settings["heat_pump"].update(sensitivity["heat_pump"])
        run_case(sensitivity["name"], case_settings, heating, cooling, commit)
    print(f"OUTPUTS: {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
