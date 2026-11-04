"""Curves of the component models we built, for the dashboard 'Component models' panel.

    python make_component_data.py -> outputs_dashboard/components.json, health.json
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from gemini_design_agent.components import HeatPump, AbsorptionChiller, HeatExchanger, bubble_point_estimate_bar
from gemini_design_agent.spec import SPEC

OUT = ROOT / "outputs_dashboard"
hp, ab, hx = HeatPump(), AbsorptionChiller(), HeatExchanger()
rows = []
for t in range(40, 121, 2):
    rows.append({"curve": "hp_cop", "x": t, "y": round(hp.cop(t - 20, 100.0), 3)})       # source mean = brine in - 20 C
for t in range(60, 126, 1):
    rows.append({"curve": "abs_cop", "x": t, "y": round(ab.cop(t), 3)})
for g in [i / 10 for i in range(0, 31)]:
    rows.append({"curve": "bubble", "x": g, "y": round(bubble_point_estimate_bar(g, 90.0), 2)})
for d in range(2000, 4201, 50):
    rows.append({"curve": "wellhead_t", "x": d, "y": round(SPEC.reservoir.temperature_at_depth(d) - 3.0, 2)})  # ~3 C wellbore loss at 300 m3/h
(OUT / "components.json").write_text(json.dumps(rows), encoding="utf-8")
print("components.json", len(rows))

# equipment health over the 25-year loop
cl = json.loads((ROOT / "outputs_claude" / "closed_loop.json").read_text(encoding="utf-8"))
k = json.loads((ROOT / "outputs_claude" / "final_kpis.json").read_text(encoding="utf-8"))["kpis"]
corr = k["corrosion_rate_unmitigated_mm_yr"]
h = []
for r in cl["records"]:
    h.append({"year": r["year"], "esp_eff": r["esp_efficiency_factor"], "skin_extra": r["skin_injection_extra"],
              "injection_whp_bar": r["injection_whp_bar"], "t_produced_c": r["t_produced_c"],
              "wall_loss_mm_unmitigated": round(corr * r["year"], 1), "wall_loss_mm_mitigated": round(0.1 * r["year"], 2),
              "actions": "; ".join(r["actions"])})
(OUT / "health.json").write_text(json.dumps(h), encoding="utf-8")
print("health.json", len(h), "corrosion", corr)
