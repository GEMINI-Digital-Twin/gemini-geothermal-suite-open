"""Monte Carlo, tornado and design-comparison studies on ``gemini_design`` plants.

Every sample re-runs the full 365-day dispatch (``gemini_design.annual.run_year``)
with the sampled reservoir, demand and prices, so the dispatcher re-optimises
for each price set and the physics checks (flow, 40 K brine cooling, 330 days)
are re-applied. All designs see the same samples (common random numbers),
which makes paired comparisons such as "how often is design A cheaper than
design B" meaningful even with a few hundred samples.
"""

import dataclasses
import warnings
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from scipy import stats

from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_design.screening import candidate_designs
from gemini_uncertainty.economics import energy_prices, levelised_cost
from gemini_uncertainty.parameters import PARAMETERS, base_values, sample

OPERATIONAL_CHECKS = (
    "flow_within_50_300_m3h",
    "brine_cooling_within_40K",
    "production_equals_injection",
    "doublet_days_within_330",
    "doublets_within_1_3",
    "no_daily_violations",
)
OUTPUTS = (
    "demand_met",
    "heating_met",
    "cooling_met",
    "operational_ok",
    "unmet_heating_mwh",
    "unmet_cooling_mwh",
    "lcoe_eur_per_mwh",
    "capex_meur",
    "annual_energy_cost_meur",
    "co2_t_per_year",
    "co2_kg_per_mwh",
    "geothermal_share_of_heat",
    "purchased_gas_mwh",
    "grid_import_mwh",
    "reservoir_temperature_c",
    "productivity_index_m3h_per_bar",
)


def design_from_name(name, depths_m=None):
    """Return the screening-grid ``Design`` with this name (e.g. ``2D-3100m-boiler-electric``).

    The depth is read from the name, so any depth works, and equipment is
    sized with the same rules as ``gemini_design.screening.candidate_designs``.
    A ``+C12`` / ``+B33`` suffix resizes the chiller / boiler (see ``with_capacity``).
    """
    base_name, *sizes = name.split("+")
    if sizes:
        sized = {s[0]: float(s[1:]) for s in sizes if s[:1] in ("C", "B")}
        return with_capacity(design_from_name(base_name), sized.get("C"), sized.get("B"))
    try:
        depth = float(name.split("-")[1].rstrip("m"))
    except (IndexError, ValueError) as err:
        raise ValueError(f"Cannot read a depth from design name '{name}'") from err
    for d in candidate_designs(depths_m or (depth,)):
        if d.name == name:
            return d
    raise ValueError(
        f"Unknown design '{name}'. Use '<1-3>D-<depth>m-<boiler|heat_pump>-"
        "<electric|absorption>[-chp][+C<chiller MW>][+B<boiler MW>]'."
    )


def with_capacity(design, chiller_mw=None, boiler_mw=None):
    """Return a copy of ``design`` with resized chiller and/or boiler, named by its sizes.

    For example ``2D-3100m-boiler-electric+C12`` has a 12 MW chiller.
    """
    changes, suffix = {}, ""
    if chiller_mw is not None:
        changes["chiller_capacity_mw"] = float(chiller_mw)
        if design.cooling == "absorption":
            changes["electric_backup_mw"] = float(chiller_mw) / 2
        suffix += f"+C{chiller_mw:g}"
    if boiler_mw is not None:
        changes["boiler_capacity_mw"] = float(boiler_mw)
        suffix += f"+B{boiler_mw:g}"
    return dataclasses.replace(design, name=design.name + suffix, **changes)


def apply_values(values, demand, challenge=CHALLENGE, assumptions=ASSUMPTIONS, params=PARAMETERS):
    """Return (challenge, assumptions, demand) with sampled ``values`` applied.

    Values for parameters not in ``params`` are ignored, so a sample row
    can be passed as is. Prices that are derived (electricity import and
    export, purchased gas) are computed by ``economics.energy_prices``.
    """
    c, a = dict(challenge), dict(assumptions)
    dem = demand.copy()
    for p in params:
        if p.name not in values:
            continue
        v = float(values[p.name])
        if p.target == "challenge":
            c[p.name] = v
        elif p.target == "assumptions":
            a[p.name] = v
        elif p.name == "heating_scale":
            dem["heating_mw"] = dem["heating_mw"] * v
        elif p.name == "cooling_scale":
            dem["cooling_mw"] = dem["cooling_mw"] * v
    a = energy_prices(values, a)
    return c, a, dem


def evaluate(design, values, demand, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Run one design for one parameter set and return a flat dict of outcomes."""
    c, a, dem = apply_values(values, demand, challenge, assumptions)
    out = {"design": design.name}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, summary = run_year(design, dem, c, a)
    except Exception as err:  # a sample the physics cannot solve is a result, not a crash
        out.update({k: np.nan for k in OUTPUTS})
        out.update(demand_met=False, operational_ok=False, error=f"{type(err).__name__}: {err}")
        return out
    econ = levelised_cost(design, summary, a, values)
    e, k, checks = summary["energy_mwh"], summary["kpi"], summary["checks"]
    delivered = e["heating_delivered"] + e["cooling_delivered"]
    out.update(
        {
            "heating_met": bool(checks["heating_demand_met"]),
            "cooling_met": bool(checks["cooling_demand_met"]),
            "operational_ok": all(bool(checks[name]) for name in OPERATIONAL_CHECKS),
            "unmet_heating_mwh": e["unmet_heating"],
            "unmet_cooling_mwh": e["unmet_cooling"],
            "lcoe_eur_per_mwh": econ["lcoe_eur_per_mwh"],
            "capex_meur": econ["capex_eur"]["total"] / 1e6,
            "annual_energy_cost_meur": econ["annual_energy_cost_eur"] / 1e6,
            "co2_t_per_year": k["co2_t_per_year"],
            "co2_kg_per_mwh": k["co2_t_per_year"] * 1000.0 / max(delivered, 1e-9),
            "geothermal_share_of_heat": k["geothermal_share_of_heat"],
            "purchased_gas_mwh": e["purchased_gas_fuel"],
            "grid_import_mwh": e.get("grid_import", e["electricity"]),
            "reservoir_temperature_c": summary["reservoir"]["temperature_c"],
            "productivity_index_m3h_per_bar": summary["reservoir"][
                "productivity_index_m3h_per_bar"
            ],
            "error": "",
        }
    )
    out["demand_met"] = out["heating_met"] and out["cooling_met"]
    return out


def _evaluate_task(args):
    design, sample_id, values, demand = args
    result = evaluate(design, values, demand)
    result["sample"] = sample_id
    return result


def _run_tasks(tasks, workers):
    if workers == 1:
        return [_evaluate_task(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_evaluate_task, tasks, chunksize=4))


def monte_carlo(
    designs, demand, n=200, seed=2027, params=PARAMETERS, workers=None, fixed_values=None
):
    """Run every design on the same ``n`` Latin-hypercube samples.

    Parameters not in ``params`` are held at ``fixed_values`` (default:
    their sourced base value), so dropping a parameter from the sampling
    never silently falls back to the older ``gemini_design`` assumptions.

    Returns
    -------
    (pandas.DataFrame, pandas.DataFrame)
        Results (one row per design and sample, with the sampled values)
        and the sample table itself.
    """
    samples = sample(params, n, seed)
    sampled = {p.name for p in params}
    fixed = {k: v for k, v in base_values(PARAMETERS).items() if k not in sampled}
    fixed.update(fixed_values or {})
    tasks = [
        (d, int(i), {**fixed, **row.to_dict()}, demand)
        for d in designs
        for i, row in samples.iterrows()
    ]
    rows = _run_tasks(tasks, workers)
    results = pd.DataFrame(rows).merge(samples, left_on="sample", right_index=True)
    return results, samples


def base_case(designs, demand, params=PARAMETERS, workers=None):
    """Run every design at the sourced base values (median / mode of each parameter)."""
    values = base_values(params)
    rows = _run_tasks([(d, -1, values, demand) for d in designs], workers)
    return pd.DataFrame(rows)


def tornado(design, demand, params=PARAMETERS, low_q=0.1, high_q=0.9, workers=None):
    """One-at-a-time sensitivity: each parameter at its P10 and P90, the rest at base.

    Returns a DataFrame with one row per parameter: low/high input values,
    the outcome at each, and the swing in levelised cost, sorted by swing.
    """
    base = base_values(params)
    tasks = [(design, -1, base, demand)]
    for p in params:
        for q in (low_q, high_q):
            values = dict(base)
            values[p.name] = float(p.ppf(q))
            tasks.append((design, f"{p.name}@{q}", values, demand))
    rows = _run_tasks(tasks, workers)
    base_row, rest = rows[0], rows[1:]
    out = []
    for i, p in enumerate(params):
        lo, hi = rest[2 * i], rest[2 * i + 1]
        out.append(
            {
                "parameter": p.name,
                "label": p.label,
                "unit": p.unit,
                "input_low": float(p.ppf(low_q)),
                "input_high": float(p.ppf(high_q)),
                "lcoe_low": lo["lcoe_eur_per_mwh"],
                "lcoe_high": hi["lcoe_eur_per_mwh"],
                "co2_low": lo["co2_t_per_year"],
                "co2_high": hi["co2_t_per_year"],
                "demand_met_low": lo["demand_met"],
                "demand_met_high": hi["demand_met"],
                "unmet_mwh_low": lo["unmet_heating_mwh"] + lo["unmet_cooling_mwh"],
                "unmet_mwh_high": hi["unmet_heating_mwh"] + hi["unmet_cooling_mwh"],
            }
        )
    table = pd.DataFrame(out)
    table["lcoe_base"] = base_row["lcoe_eur_per_mwh"]
    table["co2_base"] = base_row["co2_t_per_year"]
    table["lcoe_swing"] = (table["lcoe_high"] - table["lcoe_low"]).abs()
    table["co2_swing"] = (table["co2_high"] - table["co2_low"]).abs()
    return table.sort_values("lcoe_swing", ascending=False).reset_index(drop=True)


def _q(series, q):
    s = series.dropna()
    return float(s.quantile(q)) if len(s) else float("nan")


def summarise(results):
    """Return a per-design summary table of the Monte Carlo results.

    ``p_demand_met`` is the share of samples in which every day's heating
    and cooling demand is met while every hard constraint holds.
    """
    rows = []
    for name, g in results.groupby("design", sort=False):
        ok = g["demand_met"].astype(bool) & g["operational_ok"].astype(bool)
        unmet = g["unmet_heating_mwh"] + g["unmet_cooling_mwh"]
        rows.append(
            {
                "design": name,
                "n": len(g),
                "failed_runs": int((g["error"].fillna("") != "").sum()),
                "p_demand_met": float(ok.mean()),
                "p_heating_met": float(g["heating_met"].astype(bool).mean()),
                "p_cooling_met": float(g["cooling_met"].astype(bool).mean()),
                "unmet_mwh_mean": float(unmet.mean()),
                "unmet_mwh_p90": _q(unmet, 0.9),
                "lcoe_p10": _q(g["lcoe_eur_per_mwh"], 0.1),
                "lcoe_p50": _q(g["lcoe_eur_per_mwh"], 0.5),
                "lcoe_p90": _q(g["lcoe_eur_per_mwh"], 0.9),
                "lcoe_mean": float(g["lcoe_eur_per_mwh"].mean()),
                "co2_kt_p10": _q(g["co2_t_per_year"], 0.1) / 1e3,
                "co2_kt_p50": _q(g["co2_t_per_year"], 0.5) / 1e3,
                "co2_kt_p90": _q(g["co2_t_per_year"], 0.9) / 1e3,
                "capex_meur_p50": _q(g["capex_meur"], 0.5),
                "geothermal_share_p50": _q(g["geothermal_share_of_heat"], 0.5),
            }
        )
    table = pd.DataFrame(rows)
    return table.sort_values(["p_demand_met", "lcoe_p50"], ascending=[False, True]).reset_index(
        drop=True
    )


def compare(results, design_a, design_b):
    """Paired comparison of two designs over the shared samples."""
    a = results[results["design"] == design_a].set_index("sample")
    b = results[results["design"] == design_b].set_index("sample")
    idx = a.index.intersection(b.index)
    a, b = a.loc[idx], b.loc[idx]
    d_lcoe = a["lcoe_eur_per_mwh"] - b["lcoe_eur_per_mwh"]
    d_co2 = a["co2_t_per_year"] - b["co2_t_per_year"]
    return {
        "design_a": design_a,
        "design_b": design_b,
        "n": int(len(idx)),
        "p_a_cheaper": float((d_lcoe < 0).mean()),
        "lcoe_diff_p10": _q(d_lcoe, 0.1),
        "lcoe_diff_p50": _q(d_lcoe, 0.5),
        "lcoe_diff_p90": _q(d_lcoe, 0.9),
        "p_a_lower_co2": float((d_co2 < 0).mean()),
        "co2_diff_kt_p50": _q(d_co2, 0.5) / 1e3,
    }


def rank_correlations(results, output="lcoe_eur_per_mwh", params=PARAMETERS):
    """Return Spearman rank correlation of each input with ``output``, per design."""
    rows = {}
    for name, g in results.groupby("design", sort=False):
        rows[name] = {}
        for p in params:
            ok = g[[p.name, output]].dropna()
            if len(ok) < 3 or ok[output].nunique() < 2:
                rows[name][p.name] = 0.0
                continue
            rows[name][p.name] = float(stats.spearmanr(ok[p.name], ok[output]).statistic)
    return pd.DataFrame(rows)
