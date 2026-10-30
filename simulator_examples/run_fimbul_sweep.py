"""Run the Fimbul.jl reservoir sweep and build the lookup table for the design agent.

Runs 30-year thermal simulations (JutulDarcy via Fimbul.jl) of a doublet at
3.1 km over well spacing and flow, plus checks of the scalings the lookup
relies on (permeability, injection temperature, depth, grid size) and the
likely-pick design (2 doublets at 3.1 km, boiler, electric chiller, CHP) on its
real monthly flow schedule from the
annual runner. Results are cached in ``src/gemini_design/fimbul/cache/``,
so re-running only simulates new cases. Writes:

* ``src/gemini_design/fimbul/fimbul_table.json``: the lookup table
* ``simulator_examples/outputs/fimbul/sweep_report.json``: checks and the
  2-doublet schedule runs, compared with the steady-state model

Needs Julia with Fimbul installed only for uncached cases:
    $env:GEMINI_JULIA="julia"; $env:GEMINI_FIMBUL_ENV="<env>"
    $env:PYTHONPATH="src"; python simulator_examples/run_fimbul_sweep.py
"""

import json
from pathlib import Path

import numpy as np

from gemini_design.annual import run_year, schedule_outages
from gemini_design.challenge import load_demand
from gemini_design.doublet import DoubletHydraulics
from gemini_design.fimbul.lifetime import lifetime_performance
from gemini_design.fimbul.lookup import TABLE, annual_series, load_table, simulate_doublet
from gemini_design.fimbul.runner import (
    FIMBUL_ASSUMPTIONS,
    default_inputs,
    run_fimbul,
    schedule_from_daily,
)
from gemini_design.plant import Design
from gemini_design.screening import chp_size_mw_el

INPUTS = Path(__file__).parent / "hackathon_inputs"
OUTPUTS = Path(__file__).parent / "outputs" / "fimbul"

SPACINGS = [800.0, 1000.0, 1200.0, 1500.0, 1800.0]
FLOWS = [75.0, 150.0, 225.0, 300.0]
T_INJ = 60.0
YEARS = 30

PICK = Design(
    n_doublets=2,
    depth_m=3100.0,
    upgrade="boiler",
    cooling="electric",
    boiler_capacity_mw=30.0,
    chiller_capacity_mw=10.0,
    chp_capacity_mw_el=chp_size_mw_el(2),
)


def grid_cases():
    """Return the (spacing, flow) grid cases in table order."""
    return [
        default_inputs(well_spacing_m=s, flow_m3h=q, injection_temperature_c=T_INJ, years=YEARS)
        for s in SPACINGS
        for q in FLOWS
    ]


def check_cases():
    """Return named single-doublet cases that test the lookup's scalings."""
    base = {"well_spacing_m": 1200.0, "flow_m3h": 150.0, "years": YEARS}
    return {
        "perm_100": default_inputs(**base, permeability_md=100.0, injection_temperature_c=T_INJ),
        "perm_400": default_inputs(**base, permeability_md=400.0, injection_temperature_c=T_INJ),
        "tinj_45": default_inputs(**base, injection_temperature_c=45.0),
        "depth_2500": default_inputs(**base, depth_m=2500.0, injection_temperature_c=T_INJ),
        "grid_25m_1200_300": default_inputs(
            well_spacing_m=1200.0,
            flow_m3h=300.0,
            years=YEARS,
            dx_m=25.0,
            injection_temperature_c=T_INJ,
        ),
        "grid_25m_800_300": default_inputs(
            well_spacing_m=800.0,
            flow_m3h=300.0,
            years=YEARS,
            dx_m=25.0,
            injection_temperature_c=T_INJ,
        ),
    }


def pick_schedule():
    """Return the likely pick's daily dispatch, availability and monthly schedule."""
    demand = load_demand(INPUTS)
    daily, summary = run_year(PICK, demand)
    availability = schedule_outages(demand, PICK)
    return daily, summary, schedule_from_daily(daily, availability, YEARS)


def schedule_cases(schedule):
    """Return named 2-doublet runs of the pick on its real monthly schedule."""
    cases = {}
    for spacing in (1000.0, 1200.0, 1500.0):
        cases[f"pick_L{int(spacing)}_D1500"] = default_inputs(
            n_doublets=2, well_spacing_m=spacing, doublet_separation_m=1500.0, schedule=schedule
        )
    cases["pick_L1200_D800"] = default_inputs(
        n_doublets=2, well_spacing_m=1200.0, doublet_separation_m=800.0, schedule=schedule
    )
    return cases


def theta(series, t_inj):
    """Return the normalised temperature drop of a producer series."""
    t0 = series["initial_temperature_c"]
    return [(t0 - t) / (t0 - t_inj) for t in series["temperature_c"]]


def build_table(results):
    """Return the lookup table dict from the grid results (table order)."""
    shape = (len(SPACINGS), len(FLOWS), YEARS)
    th, dd, dpi = np.zeros(shape), np.zeros(shape), np.zeros(shape)
    for n, res in enumerate(results):
        i, j = divmod(n, len(FLOWS))
        a = annual_series(res)
        th[i, j] = theta(a["Producer1"], T_INJ)
        dd[i, j] = a["Producer1"]["drawdown_bar"]
        dpi[i, j] = a["Injector1"]["overpressure_bar"]
    ref = results[0]["inputs"]
    meta = {
        "description": "30-year Fimbul.jl (JutulDarcy geothermal) single-doublet runs at 3.1 km",
        "permeability_md": ref["permeability_md"],
        "injection_temperature_c": T_INJ,
        "depth_m": ref["depth_m"],
        "reservoir_temperature_c": results[0]["wells"]["Producer1"]["initial_temperature_c"],
        "num_cells": results[0]["num_cells"],
        "assumptions": {
            **FIMBUL_ASSUMPTIONS,
            "thickness_m": ref["thickness_m"],
            "fluid": "pure water (IAPWS), permeability scaled to brine mobility",
            "wells": "vertical, fully penetrating, simple (sandface) wells",
        },
    }
    return {
        "meta": meta,
        "spacing_m": SPACINGS,
        "flow_m3h": FLOWS,
        "years": list(range(1, YEARS + 1)),
        "theta": th.tolist(),
        "drawdown_bar": dd.tolist(),
        "injection_overpressure_bar": dpi.tolist(),
    }


def compare_checks(checks):
    """Compare each scaling-check run with the lookup's prediction for it."""
    out = {}
    for name, res in checks.items():
        inp = res["inputs"]
        pred = simulate_doublet(
            depth_m=inp["depth_m"],
            flow_m3h=inp["schedule"][0]["flow_m3h"][0],
            well_spacing_m=inp["well_spacing_m"],
            permeability_md=inp["permeability_md"],
            injection_temperature_c=inp["schedule"][0]["injection_temperature_c"][0],
        )
        a = annual_series(res)
        sim_t = a["Producer1"]["temperature_c"]
        out[name] = {
            "max_abs_temperature_error_c": float(
                np.max(np.abs(np.asarray(sim_t) - pred["production_temperature_c"]))
            ),
            "year30_temperature_sim_c": sim_t[-1],
            "year30_temperature_lookup_c": pred["production_temperature_c"][-1],
            "year1_drawdown_sim_bar": a["Producer1"]["drawdown_bar"][0],
            "year1_drawdown_lookup_bar": pred["producer_drawdown_bar"][0],
            "year1_overpressure_sim_bar": a["Injector1"]["overpressure_bar"][0],
            "year1_overpressure_lookup_bar": pred["injector_overpressure_bar"][0],
        }
    return out


def steady_state_comparison(daily):
    """Return the steady-state model's numbers for the pick, for comparison."""
    hyd = DoubletHydraulics(PICK.depth_m)
    rows = {}
    for q in (150.0, 250.0, 300.0):
        prod, inj = hyd.producer(q), hyd.injector(q, 60.0)
        rows[f"{int(q)}_m3h"] = {
            "drawdown_bar": prod["drawdown_bar"],
            "injector_overpressure_bar": inj["bottomhole_pressure_bar"]
            - hyd.reservoir_pressure_bar,
        }
    active = daily[daily["n_active"] > 0]
    return {
        "reservoir_temperature_c": hyd.reservoir_temperature_c,
        "reservoir_pressure_bar": hyd.reservoir_pressure_bar,
        "productivity_index_m3h_per_bar": hyd.pi_m3h_per_bar,
        "production_temperature_c": "constant (no thermal depletion)",
        "by_flow": rows,
        "mean_active_flow_per_doublet_m3h": float(active["flow_per_doublet_m3h"].mean()),
    }


def summarise_schedule_runs(runs):
    """Return annual producer temperatures and peak pressures of the 2-doublet runs."""
    out = {}
    for name, res in runs.items():
        a = annual_series(res)
        keys = ("well_spacing_m", "doublet_separation_m")
        entry = {"inputs": {k: res["inputs"][k] for k in keys}}
        for w in ("Producer1", "Producer2"):
            entry[w] = {
                "initial_temperature_c": a[w]["initial_temperature_c"],
                "year_end_temperature_c": a[w]["temperature_c"],
            }
        for w in ("Producer1", "Producer2", "Injector1", "Injector2"):
            p = np.asarray(res["wells"][w]["bottomhole_pressure_bar"])
            p0 = res["wells"][w]["initial_pressure_bar"]
            entry[w + "_max_abs_dp_bar"] = float(np.max(np.abs(p - p0)))
        entry["wall_time_s"] = res["wall_time_s"]
        out[name] = entry
    return out


def main():
    """Run (or load) every case, write the table and the report."""
    daily, summary, schedule = pick_schedule()
    grid = grid_cases()
    checks = check_cases()
    sched = schedule_cases(schedule)
    names = list(checks) + list(sched)
    results = run_fimbul(grid + list(checks.values()) + list(sched.values()))
    grid_res = results[: len(grid)]
    named = dict(zip(names, results[len(grid) :]))

    TABLE.write_text(json.dumps(build_table(grid_res)))
    load_table.cache_clear()

    # equivalent constant-rate lookup for each doublet of the pick
    flows = np.asarray([p["flow_m3h"] for p in schedule[:12]])
    days = np.asarray([p["duration_days"] for p in schedule[:12]])
    mean_flow = (flows * days[:, None]).sum(axis=0) / days.sum()
    report = {
        "checks": compare_checks({k: named[k] for k in checks}),
        "pick_schedule_runs": summarise_schedule_runs({k: named[k] for k in sched}),
        "pick_mean_flow_per_doublet_m3h": mean_flow.tolist(),
        "pick_lookup_equivalent": {
            f"L{int(s)}": simulate_doublet(
                flow_m3h=float(mean_flow.mean()), well_spacing_m=s, injection_temperature_c=59.3
            )["production_temperature_c"]
            for s in (1000.0, 1200.0, 1500.0)
        },
        "steady_state_model": steady_state_comparison(daily),
        "pick_summary_lcoe_eur_per_mwh": summary["economics"]["lcoe_eur_per_mwh"],
        "pick_lifetime": {
            f"L{int(s)}": lifetime_performance(PICK, load_demand(INPUTS), well_spacing_m=s)
            for s in (1000.0, 1200.0)
        },
    }
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "sweep_report.json").write_text(json.dumps(report, indent=2, default=float))
    print(json.dumps(report["checks"], indent=1))
    for name, r in report["pick_schedule_runs"].items():
        t = r["Producer1"]["year_end_temperature_c"]
        print(name, f"year 1 {t[0]:.2f} C, year 30 {t[-1]:.2f} C")
    for name, life in report["pick_lifetime"].items():
        for year, r in life["by_year"].items():
            print(
                f"{PICK.name} {name} year {year}: drop {r['production_temperature_drop_c']:.2f} K,"
                f" LCOE {r['lcoe_eur_per_mwh']:.2f} EUR/MWh, CO2 {r['co2_t_per_year']:,.0f} t,"
                f" constraints met {r['all_hard_constraints_met']}"
            )
    print(f"Wrote {TABLE} and {OUTPUTS / 'sweep_report.json'}")


if __name__ == "__main__":
    main()
