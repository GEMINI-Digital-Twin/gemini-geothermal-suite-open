"""Red-team the agent's physics gate with injected faults (no LLM needed).

Runs a few real designs through the agent's ToolBox (so they pass the
gate), then plants faults of known kinds in final answers (gate 6), in the
daily results (gates 2, 3, 5) and in tool arguments (gate 1), and counts
how many the gate rejects. Clean inputs measure false alarms.

    $env:PYTHONPATH="src"; python simulator_examples/run_gate_red_team.py --trials 200

Writes simulator_examples/outputs/gate_red_team/results.csv and results.md.
"""

import argparse
import csv
import json
import shutil
from pathlib import Path

from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.physics_gate import check_answer
from gemini_agent.red_team import run_answer_trials, run_arg_trials, run_daily_trials, score
from gemini_agent.tools import ToolBox
from gemini_design.challenge import default_inputs_dir, load_demand

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "gate_red_team"
DESIGNS = [
    {
        "n_doublets": 2,
        "depth_m": 3100,
        "upgrade": "boiler",
        "cooling": "electric",
        "chp": True,
        "chiller_capacity_mw": 12.0,
    },
    {"n_doublets": 1, "depth_m": 2800, "upgrade": "boiler", "cooling": "electric"},
    {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "absorption", "chp": True},
    {"n_doublets": 2, "depth_m": 2500, "upgrade": "heat_pump", "cooling": "electric"},
]


def main():
    """Run the study and write the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=200, help="trials per fault class")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    ledger, notes = RunLedger(OUT / "ws"), ProjectNotes(OUT / "ws")
    tb = ToolBox(load_demand(INPUTS), ledger, notes, OUT / "ws", workers=1)
    runs = []
    for d in DESIGNS:
        head = tb.call("run_design", d)
        print(f"{head['run_id']} {head['design']}: gate {head['physics_gate']}")
        if head["physics_gate"] == "pass":
            runs.append((head["run_id"], {k: v for k, v in head.items() if k != "run_id"}))
    # a ledger entry that failed the gate, so citing it is a fault
    failed = ledger.add(
        "design",
        "redteam-failed",
        {"note": "planted"},
        {"design": "planted-invalid"},
        {"passed": False},
    )

    def numbers_only(answer, evidence, brief, ledger_):
        """Numbers only."""
        return check_answer(answer, evidence, brief, ledger_, unit_binding=False)

    tables = {
        "gate 6, numbers only (as built)": run_answer_trials(
            runs, ledger, failed, args.trials, args.seed, checker=numbers_only
        ),
        "gate 6 + 6b unit binding": run_answer_trials(runs, ledger, failed, args.trials, args.seed),
        "gates 2/3/5 (daily results)": run_daily_trials(runs, ledger, args.trials, args.seed),
        "gate 1 schema only": run_arg_trials(),
        "gate 1 via ToolBox.call": run_arg_trials(tb),
    }
    rows = []
    for layer, res in tables.items():
        for name, r in res.items():
            rows.append(
                {
                    "layer": layer,
                    "fault": name,
                    "expected": r["expected"],
                    "n": r["n"],
                    "rejected": r["rejected"],
                    "rejected_pct": round(100.0 * r["rejected"] / r["n"], 1) if r["n"] else "",
                }
            )
    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    totals = {layer: score(res) for layer, res in tables.items()}
    (OUT / "totals.json").write_text(json.dumps(totals, indent=2), encoding="utf-8")
    lines = [
        "# Physics-gate red team",
        "",
        f"Runs: {', '.join(r for r, _ in runs)}; "
        f"{args.trials} trials per class, seed {args.seed}.",
        "",
        "| layer | fault | expected | n | rejected | % |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['layer']} | {r['fault']} | {r['expected']} | {r['n']} | {r['rejected']} | "
        f"{r['rejected_pct']} |"
        for r in rows
    ]
    lines += [
        "",
        "| layer | designed faults caught | blind-class faults caught | false alarms |",
        "|---|---|---|---|",
    ]
    for layer, t in totals.items():
        lines.append(
            f"| {layer} | {t['designed_caught']}/{t['designed_faults']} | "
            f"{t['blind_caught']}/{t['blind_faults']} | {t['false_alarms']}/{t['clean']} |"
        )
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
