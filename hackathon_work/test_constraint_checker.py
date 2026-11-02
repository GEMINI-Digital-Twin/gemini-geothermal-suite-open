"""GEMINI hackathon task 2: negative tests for the constraint checker.

Run in GEMINI repository root:
    py -3.11 -m poetry run python hackathon_work/test_constraint_checker.py

Synthetic cases (not simulator results): one compliant reference case and
variants that each break one constraint. Every variant must be rejected for
the expected reason. Output is saved as report evidence in
outputs/evidence/constraint_checker_tests.{txt,json}. Exits non-zero if any
expectation fails.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from constraints import FAIL, MISSING, check_constraints, format_report, load_limits

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "outputs" / "evidence"
ETA = 0.70
ESP_DP_PA = 27.7e5
INJECTOR_DP_PA = 1.0e5


def doublet(name, q_m3h, t_prod=85.0, t_inj=50.0, q_inj_m3h=None, eta=ETA):
    q_inj_m3h = q_m3h if q_inj_m3h is None else q_inj_m3h
    q = q_m3h / 3600
    return {
        "name": name,
        "active": True,
        "production_m3h": q_m3h,
        "injection_m3h": q_inj_m3h,
        "T_production_C": t_prod,
        "T_injection_C": t_inj,
        "pumps": [
            {"name": "ESP", "flow_m3s": q, "dp_pa": ESP_DP_PA, "power_w": q * ESP_DP_PA / eta},
            {"name": "injector_pump", "flow_m3s": q, "dp_pa": INJECTOR_DP_PA, "power_w": q * INJECTOR_DP_PA / ETA},
        ],
    }


def reference_case():
    return {"n_doublets": 1, "doublets": [doublet("doublet_1", 200.0)], "heating_supply_C": 100.0, "cooling_supply_C": 20.0}


def variant(**changes):
    case = reference_case()
    case.update(copy.deepcopy(changes))
    return case


# (id, description, case, expected status per check; None = must be feasible)
TESTS = [
    ("T0_reference", "compliant reference: 200 m3/h, dT 35 K, eta 0.70, 100 C / 20 C", reference_case(), None),
    ("T1_flow_350", "proposed 350 m3/h per doublet",
     variant(doublets=[doublet("doublet_1", 350.0)]), {"flow_range": FAIL}),
    ("T2_flow_30", "proposed 30 m3/h per active doublet",
     variant(doublets=[doublet("doublet_1", 30.0)]), {"flow_range": FAIL}),
    ("T3_dT_45", "brine cooled 85 -> 40 C (45 K)",
     variant(doublets=[doublet("doublet_1", 200.0, t_inj=40.0)]), {"brine_dT": FAIL}),
    ("T4_four_doublets", "4 doublets",
     variant(n_doublets=4, doublets=[doublet(f"doublet_{i}", 200.0) for i in range(1, 5)]), {"doublet_count": FAIL}),
    ("T5_supply_77.75", "task-1 heating supply 77.75 C",
     variant(heating_supply_C=77.75), {"heating_supply_T": FAIL}),
    ("T6_esp_curve_power", "extra: ESP power taken from the curve at eta 0.65",
     variant(doublets=[doublet("doublet_1", 200.0, eta=0.65)]), {"pump_efficiency": FAIL}),
    ("T7_volume_imbalance", "extra: 200 m3/h produced, 190 m3/h injected",
     variant(doublets=[doublet("doublet_1", 200.0, q_inj_m3h=190.0)]), {"volume_balance": FAIL}),
    ("T8_no_cooling_model", "extra: cooling supply not modeled",
     variant(cooling_supply_C=None), {"cooling_supply_T": MISSING}),
]


def main():
    limits = load_limits()
    text, records, failures = [], [], []
    for test_id, description, case, expected in TESTS:
        report = check_constraints(case, limits)
        statuses = {}
        for r in report["results"]:
            if r["status"] != "PASS":
                statuses.setdefault(r["check"], r["status"])
        if expected is None:
            ok = report["feasible"]
            expectation = "feasible"
        else:
            ok = not report["feasible"] and all(statuses.get(c) == s for c, s in expected.items())
            expectation = "rejected by " + ", ".join(f"{c}={s}" for c, s in expected.items())
        if not ok:
            failures.append(test_id)
        text += [f"=== {test_id}: {description}", f"expected: {expectation} -> {'OK' if ok else 'UNEXPECTED'}", format_report(report), ""]
        records.append({"id": test_id, "description": description, "expected": expectation, "ok": ok, "case": case, "report": report})

    summary = f"{len(TESTS) - len(failures)}/{len(TESTS)} expectations met" + (f"; UNEXPECTED: {', '.join(failures)}" if failures else "")
    text.append(summary)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "constraint_checker_tests.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    (EVIDENCE / "constraint_checker_tests.json").write_text(
        json.dumps({"limits": limits, "summary": summary, "tests": records}, indent=2), encoding="utf-8"
    )
    print("\n".join(text))
    print("EVIDENCE: hackathon_work/outputs/evidence/constraint_checker_tests.{txt,json}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
