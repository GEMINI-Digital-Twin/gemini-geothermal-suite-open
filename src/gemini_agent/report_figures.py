"""Render report/video figures (PNG) from the same Plotly charts the cockpit shows.

PYTHONPATH=src python -m gemini_agent.report_figures
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from gemini_agent.optimize import search, stress_test
from gemini_agent.physics.design import DesignSpec
from gemini_agent.physics.gemini_project import verify_day
from gemini_agent.service import DesignService, default_weather
from gemini_agent.ui import charts

OUT = Path("docs_geohackathon2026/figures")


def _png(fig, name: str, width: int = 1100, height: int | None = None):
    html = OUT / f"_{name}.html"
    fig.update_layout(width=width, height=height or fig.layout.height)
    fig.write_html(html, include_plotlyjs=True, full_html=True, config={"displayModeBar": False})
    from playwright.sync_api import sync_playwright

    # GEODESIGN_CHROME=/path/to/chrome if Playwright's own browser is not installed
    exe = [os.environ["GEODESIGN_CHROME"]] if os.environ.get("GEODESIGN_CHROME") else []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe[0] if exe else None, args=["--no-sandbox"])
        pg = b.new_page(
            viewport={"width": width + 40, "height": (height or fig.layout.height) + 40},
            device_scale_factor=2,
        )
        pg.goto(html.resolve().as_uri())
        pg.wait_for_timeout(1500)
        pg.locator(".plotly-graph-div").first.screenshot(path=str(OUT / f"{name}.png"))
        b.close()
    html.unlink()


def main():
    """Search (balanced, site weather), apply the robustness gate, render figures + summary JSON.

    Robustness gate (same rule the risk-verifier applies): the design must still meet demand at
    +10 % load; if not, the electric chiller is raised in 0.5 MW steps until it does.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    svc = DesignService(weather=default_weather())
    out = search(svc, "balanced")
    best, margin_steps = out["best"], []
    selected = sys.argv[1] if len(sys.argv) > 1 else None  # spec.json of the agent's final design
    if selected:  # the report presents the design the agent produced (evidence session S1)
        best = svc.evaluate(DesignSpec(**json.loads(Path(selected).read_text())))
        gate = {
            "rule": "agent session: +10 % load failed, add_capacity_margin on cooling",
            "source": str(Path(selected).resolve()).split("/gemini/", 1)[-1],
            "electric_chiller_mw": [
                out["best"].spec.electric_chiller_mw,
                best.spec.electric_chiller_mw,
            ],
        }
    else:
        while (
            not stress_test(svc, best.spec, "demand_plus_10")["feasible"] and len(margin_steps) < 10
        ):
            spec = best.spec.model_copy(
                update={"electric_chiller_mw": best.spec.electric_chiller_mw + 0.5}
            )
            best = svc.evaluate(spec)
            margin_steps.append(spec.electric_chiller_mw)
        gate = {"rule": "meet demand at +10 % load", "electric_chiller_steps_mw": margin_steps}
    res = best.result
    _png(charts.heat_supply(res), "heat_supply")
    _png(charts.cooling_supply(res), "cooling_supply")
    _png(charts.brine_operation(res), "brine_operation", height=500)
    _png(charts.sankey(res), "sankey", height=420)
    _png(charts.availability(res), "availability", height=220)
    _png(
        charts.pareto(
            [e.pareto_row() for e in out["ranked"]] + [best.pareto_row()], best.spec.key()
        ),
        "pareto",
        height=420,
    )
    sens = OUT / "sensitivity.json"
    if sens.exists():  # tornado without inputs that do not move LCOE
        t = json.loads(sens.read_text())["tornado"]
        t["rows"] = [r for r in t["rows"] if r["lcoe_swing"] >= 0.05]
        _png(charts.tornado(t), "tornado", height=360)
    v = verify_day(best, max(range(365), key=lambda i: svc.demand.heating_mw[i]), svc.brief)
    summary = {
        "selected": best.summary(),
        "economics": best.economics,
        "checks": best.checks,
        "n_evaluated": out["n_evaluated"],
        "search_best": out["best"].summary(),
        "selected_spec": best.spec.model_dump(),
        "search_best_spec": out["best"].spec.model_dump(),
        "robustness_gate": gate,
        "weather": svc.weather.source if svc.weather else "constant 27 C tower water",
        "alternatives": [e.summary() for e in out["ranked"][1:6]],
        "pareto": [e.summary() for e in out["pareto"]],
        "gemini_verification_peak_day": {
            k: v[k] for k in ("date", "screening", "gemini_solver", "deviation", "consistent")
        },
    }
    (OUT / "selected_design.json").write_text(json.dumps(summary, indent=1, default=str))
    (OUT / "gemini_project_peak_day.json").write_text(
        json.dumps(v["project"], indent=1, default=str)
    )
    print(json.dumps(best.summary(), indent=1, default=str))


if __name__ == "__main__":
    main()
