"""Run the ESP smart-monitoring demo on the selected design.  python run_monitoring.py"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from gemini_design_agent.esp_monitoring import demo
from gemini_design_agent.system import SystemDesign

OUT = ROOT / "outputs_monitoring"
ds = SystemDesign.from_dict(json.loads((ROOT / "outputs_claude" / "final_design.json").read_text(encoding="utf-8")))
daily = pd.read_csv(ROOT / "outputs_claude" / "daily_dispatch.csv")
t0 = time.time()
res = demo(ds, daily, OUT, days=90, start_day=0)   # Jan-Mar: high-load season
print(f"{time.time()-t0:.0f} s")
print(json.dumps(res.summary, indent=1))
print("health now", round(res.health_now, 1), "RUL days", res.rul_days, "eff factor", res.esp_efficiency_factor)
for a in res.alerts:
    print(f"- h{a.hour:5d} {a.kind:17s} score {a.score:6.1f}  {a.message}")
