"""New design levers (PR #28/#30) on the pick and on the cheapest 2-doublet design, KNMI 2025.

Also checks the cheaper-than-oracle B1 designs the agents found on the official profiles.

    PYTHONPATH=src:simulator_examples python simulator_examples/run_pick_levers.py <workspace dir>
"""

import shutil
import sys
import warnings
from pathlib import Path

sys.path[:0] = ["src", "simulator_examples"]
warnings.simplefilter("ignore")
from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.tools import ToolBox
from gemini_design.challenge import load_demand
from gemini_design.climate import read_knmi_daily, with_climate
from run_final_pick import PICK, INPUTS

climate = with_climate(
    load_demand(INPUTS),
    read_knmi_daily("simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt", 2025),
    "max",
)
ws = Path(sys.argv[1])
shutil.rmtree(ws, ignore_errors=True)
ledger, notes = RunLedger(ws), ProjectNotes(ws)
SCREW = {
    "n_doublets": 2,
    "depth_m": 3100,
    "upgrade": "boiler",
    "cooling": "electric",
    "chp": True,
    "chiller_type": "screw_dry_cooler",
}
cases = [
    ("pick", PICK),
    ("pick, cool ret 30", {**PICK, "cooling_return_c": 30}),
    ("pick, heat ret 45 cool 28", {**PICK, "heating_return_c": 45, "cooling_return_c": 28}),
    ("pick, ESP 250 vsd", {**PICK, "esp_rated_flow_m3h": 250, "esp_drive": "vsd"}),
    ("pick, ESP 250 fixed", {**PICK, "esp_rated_flow_m3h": 250, "esp_drive": "fixed"}),
    ("pick, ESP 300 vsd", {**PICK, "esp_rated_flow_m3h": 300, "esp_drive": "vsd"}),
    ("pick, 2 boiler units", {**PICK, "boiler_units": 2}),
    ("pick, 3 boiler units", {**PICK, "boiler_units": 3}),
    (
        "pick, ESP 250 vsd, 2 units, ret 45/30",
        {
            **PICK,
            "esp_rated_flow_m3h": 250,
            "esp_drive": "vsd",
            "boiler_units": 2,
            "heating_return_c": 45,
            "cooling_return_c": 30,
        },
    ),
    ("2D screw", SCREW),
    (
        "2D screw, ESP 250 vsd, 2 units, ret 45/30",
        {
            **SCREW,
            "esp_rated_flow_m3h": 250,
            "esp_drive": "vsd",
            "boiler_units": 2,
            "heating_return_c": 45,
            "cooling_return_c": 30,
        },
    ),
    (
        "DeepSeek B1: 1D-3040 screw, 2 units, ret 45/28",
        {
            **SCREW,
            "n_doublets": 1,
            "depth_m": 3040,
            "boiler_units": 2,
            "heating_return_c": 45,
            "cooling_return_c": 28,
        },
    ),
    (
        "GLM B1: 2D-3050 screw, ESP 250, cool ret 30",
        {**SCREW, "depth_m": 3050, "esp_rated_flow_m3h": 250, "cooling_return_c": 30},
    ),
]
for label, req in cases:
    tb = ToolBox(climate, ledger, notes, ws, workers=1)
    h = tb.call("run_design", dict(req))
    if "error" in h:
        print(label, "ERROR", h["error"])
        continue
    s = ledger.summary(h["run_id"])
    print(
        f"| {label} | {h['run_id']} | {h['physics_gate']} | {h['meets_all_hard_rules']} "
        f"| {s['economics']['lcoe_eur_per_mwh']:.2f} | {h['co2_t_per_year']:.0f} "
        f"| {h['capex_meur']:.2f} |",
        flush=True,
    )
