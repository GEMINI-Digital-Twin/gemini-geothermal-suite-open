"""Red-team the checks on agent-written models (no LLM, about a second).

Plants one known bug at a time in the dry cooler and heat store models an
agent writes in the demo scenarios, then records whether the agent's own
tests and the harness acceptance tests (gemini_agent.acceptance) reject it.

    $env:PYTHONPATH="src"; python simulator_examples/run_model_red_team.py

Writes simulator_examples/outputs/model_red_team/results.csv and results.md.
"""

import csv
import json
from pathlib import Path

from gemini_agent.model_red_team import run_model_trials, score_models

OUT = Path(__file__).parent / "outputs" / "model_red_team"


def _yes(flag):
    return "yes" if flag else "no"


def main():
    """Run the study and write the results."""
    OUT.mkdir(parents=True, exist_ok=True)
    rows = run_model_trials()
    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    t = score_models(rows)
    (OUT / "totals.json").write_text(json.dumps(t, indent=2), encoding="utf-8")
    lines = [
        "# Agent-written model red team",
        "",
        f"{t['faults']} planted bugs ({t['designed']} the harness is designed to catch, "
        f"{t['faults'] - t['designed']} calibration error it is not) and {t['clean']} "
        "clean models.",
        "",
        f"- Agent's own tests alone: {t['agent_tests_caught']}/{t['faults']} caught",
        f"- Harness acceptance tests alone: {t['harness_caught']}/{t['faults']} caught "
        f"({t['harness_caught_designed']}/{t['designed']} of the designed faults)",
        f"- Both (what write_model now requires): {t['both_caught']}/{t['faults']} caught",
        f"- False alarms on the clean models: {t['false_alarms']}/{t['clean']}",
        "",
        "| fault | model | bug | expected | agent tests | harness | first harness problem |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['fault']} | {r['model']} | {r['description']} | {r['expected']} | "
        f"{_yes(r['agent_tests_reject'])} | {_yes(r['harness_rejects'])} | "
        f"{r['harness_problem'][:110].replace('|', '/')} |"
        for r in rows
    ]
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:9]))


if __name__ == "__main__":
    main()
