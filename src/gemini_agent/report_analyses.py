"""Robustness, alternatives, sensitivity and break-even analyses for the report.

Reads the design selected by ``report_figures``
(docs_geohackathon2026/figures/selected_design.json),
re-uses the same site weather, and writes robustness.json + sensitivity.json next to it.

  PYTHONPATH=src python -m gemini_agent.report_analyses
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from gemini_agent.optimize import monte_carlo, right_size_boiler, stress_test
from gemini_agent.physics.design import DesignSpec
from gemini_agent.sensitivity import break_even, tornado
from gemini_agent.service import DesignService, default_weather

OUT = Path("docs_geohackathon2026/figures")


def _spec(summary_label_source: dict, **update) -> DesignSpec:
    return DesignSpec(**summary_label_source).model_copy(update=update)


def weather_effect(spec: DesignSpec, wx) -> dict:
    """Same design with a constant 27 C cooling-tower temperature vs the site's ERA5 weather."""
    out = {}
    for name, svc in (("constant_27c", DesignService()), ("era5", DesignService(weather=wx))):
        ev = svc.evaluate(spec)
        out[name] = {
            "lcoe_eur_per_mwh": ev.economics["lcoe_eur_per_mwh"],
            "co2_t": ev.kpis["co2_t"],
            "electricity_gwh": ev.kpis["electricity_gwh"],
            "feasible": bool(ev.checks["passed"]),
        }
    cw = wx.cooling_water_c()
    out["cooling_water_c"] = {"min": min(cw), "max": max(cw), "mean": round(sum(cw) / len(cw), 1)}
    out["source"] = wx.source
    return out


def main():
    """Compute and write robustness.json and sensitivity.json for the selected design."""
    sel = json.loads((OUT / "selected_design.json").read_text())
    svc = DesignService(weather=default_weather())
    final_spec = DesignSpec(**sel["selected_spec"])
    search_spec = DesignSpec(**sel["search_best_spec"])
    final, base = svc.evaluate(final_spec), final_spec.model_dump()

    t0 = time.time()
    rob = {
        "doublet_trip_on_peak_day": stress_test(svc, final_spec, "doublet_trip_on_peak_day"),
        "demand_plus_10": stress_test(svc, search_spec, "demand_plus_10"),
        "demand_plus_20": stress_test(svc, final_spec, "demand_plus_20"),
        "monte_carlo": monte_carlo(svc, search_spec, n=30),
        "robust_demand_plus_10": stress_test(svc, final_spec, "demand_plus_10"),
        "robust_monte_carlo": monte_carlo(svc, final_spec, n=30),
        "robust_summary": final.summary(),
        "search_best_summary": svc.evaluate(search_spec).summary(),
    }
    rob["mc_s"] = round(time.time() - t0, 1)

    cool = final_spec.electric_chiller_mw
    alt_specs = {
        "cheapest_1x3100_gasburn": _spec(base, n_doublets=1, gas_handling="separate_and_burn"),
        "2x2500_HP": _spec(base, well_depth_m=2500.0, heat_pump_mw=10.0),
        "2x2500_HP_absorption": _spec(
            base,
            well_depth_m=2500.0,
            heat_pump_mw=10.0,
            absorption_chiller_mw=5.0,
            electric_chiller_mw=cool - 5.0,
        ),
        "2x3100_absorption": _spec(base, absorption_chiller_mw=6.0, electric_chiller_mw=cool - 4.5),
        "2x3100_gas_burned": _spec(base, gas_handling="separate_and_burn"),
        "3x3400": _spec(base, n_doublets=3, well_depth_m=3400.0),
    }
    alts = {k: right_size_boiler(svc, s) for k, s in alt_specs.items()}
    rob["alternatives"] = {k: e.summary() for k, e in alts.items()}
    (OUT / "robustness.json").write_text(json.dumps(rob, indent=1, default=str))
    print("robustness done", rob["mc_s"], "s", flush=True)

    hp, ab, one = (
        alts["2x2500_HP"].spec,
        alts["2x3100_absorption"].spec,
        alts["cheapest_1x3100_gasburn"].spec,
    )
    sens = {
        "tornado": tornado(svc, final_spec),
        "break_even": {
            "deep_vs_hp_drilling": break_even(
                svc, final_spec, hp, "well_cost_eur_per_m", 1000, 6000
            ),
            "deep_vs_hp_hpcapex": break_even(
                svc, final_spec, hp, "heat_pump_capex_eur_per_mw", 100e3, 800e3
            ),
            "electric_vs_absorption_elec_price": break_even(
                svc, final_spec, ab, "electricity_eur_per_mwh", 50, 600
            ),
            "two_vs_one_doublet_co2_price": break_even(
                svc, final_spec, one, "co2_eur_per_t", 0, 400
            ),
        },
        "weather_effect": weather_effect(final_spec, svc.weather),
        "designs": {
            "selected": final_spec.model_dump(),
            "hp": hp.model_dump(),
            "abs": ab.model_dump(),
            "one": one.model_dump(),
        },
    }
    (OUT / "sensitivity.json").write_text(json.dumps(sens, indent=1, default=str))
    print(json.dumps({k: v.get("break_even") for k, v in sens["break_even"].items()}))
    print(
        json.dumps(
            {
                k: (v["lcoe_eur_per_mwh"], v["co2_t_per_year"], v["feasible"])
                for k, v in rob["alternatives"].items()
            }
        )
    )
    print(
        json.dumps(
            {
                k: rob[k]
                for k in ("doublet_trip_on_peak_day", "demand_plus_10", "robust_demand_plus_10")
            },
            default=str,
        )
    )
    print(
        json.dumps(
            {
                k: rob[k]["probability_demand_fully_met"]
                for k in ("monte_carlo", "robust_monte_carlo")
            }
        ),
        rob["robust_monte_carlo"]["lcoe_eur_per_mwh"],
    )


if __name__ == "__main__":
    main()
