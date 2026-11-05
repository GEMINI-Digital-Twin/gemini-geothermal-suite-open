"""Collect agent backend comparison runs into one tracked results folder.

Reads the ``results.json`` and run ledgers of each comparison output folder
(``outputs/agent_compare_<name>``), and writes to ``--dest``:

- ``results.csv`` / ``results.json``: all rows (backend x case x repeat)
- ``summary.md``: the runner's tables plus physics-gate and A1 design tables
- ``transcripts/<backend>/r<k>/*.md``: the Markdown transcript of every case

Usage::

    python simulator_examples/collect_agent_compare.py \
        --src simulator_examples/outputs/agent_compare_luna \
        --src simulator_examples/outputs/agent_compare_openrouter \
        --dest simulator_examples/agent_compare_results/2026-10-31
"""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compare_agent_models import CASES, summarise  # noqa: E402

GATE_STEPS = ["1_inputs", "2_hard_rules", "3_energy_balance", "4_second_solver", "5_sanity"]


def ledger_rows(src, backend):
    """All design runs the agent made for one backend (the reference run excluded)."""
    rows = []
    for ledger in sorted((src / backend).glob("r*/run_ledger.jsonl")):
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                entry["repeat"] = ledger.parent.name
                rows.append(entry)
    return rows


def gate_table(ledgers):
    """Physics-gate outcome of every year run, per backend."""
    lines = [
        "## Physics gate on the agents' simulation runs",
        "",
        "Gate passed = integrity verdict (energy balance and sanity). A design that fails a "
        "hard rule (for example cooling demand not met) is still a valid run, but it cannot "
        "be recommended.",
        "",
        "| backend | runs in ledger | gate passed | gate failed | meets all hard rules | "
        "solver re-run agrees | steps not passed |",
        "|---|---|---|---|---|---|---|",
    ]
    for backend, entries in ledgers.items():
        gated = [e for e in entries if isinstance(e.get("gate"), dict)]
        passed = sum(bool(e["gate"].get("passed")) for e in gated)
        rules = sum(bool(e.get("headline", {}).get("meets_all_hard_rules")) for e in gated)
        agrees = sum(
            bool((e["gate"].get("4_second_solver") or {}).get("agrees"))
            for e in gated
            if isinstance(e["gate"].get("4_second_solver"), dict)
        )
        failed_steps = {}
        for e in gated:
            for step in GATE_STEPS:
                value = e["gate"].get(step)
                if isinstance(value, str) and value != "pass":
                    failed_steps[step] = failed_steps.get(step, 0) + 1
                if isinstance(value, dict) and value.get("agrees") is False:
                    failed_steps[step] = failed_steps.get(step, 0) + 1
        steps = ", ".join(f"{k} x{v}" for k, v in failed_steps.items()) or "none"
        lines.append(
            f"| {backend} | {len(entries)} | {passed} | {len(gated) - passed} | {rules} | "
            f"{agrees} | {steps} |"
        )
    return lines


def design_table(rows, reference):
    """Design each backend selected for A1, per repeat."""
    lines = [
        "## A1 design found (reference: "
        f"{reference['design']}, {reference['lcoe_eur_per_mwh']} EUR/MWh)",
        "",
        "| backend | repeat | final reply | asked first | design | LCOE EUR/MWh | "
        "matches reference | tool calls | wall s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["case"] != "A1":
            continue
        lines.append(
            f"| {r['backend']} | {r['repeat']} | {r['final_reply']} | "
            f"{'yes' if r['asked_for_missing_input'] else 'no'} | {r['selected_design'] or '-'} | "
            f"{r['selected_lcoe_eur_per_mwh'] or '-'} | "
            f"{'yes' if r['matches_reference_design'] is True else 'no'} | "
            f"{r['tool_calls']} | {r['wall_seconds']} |"
        )
    return lines


def failure_table(rows):
    """Behaviour checks that failed, per backend and case."""
    lines = [
        "## Failed behaviour checks",
        "",
        "| backend | case | repeat | failure |",
        "|---|---|---|---|",
    ]
    for r in rows:
        if r["behaviour_failures"]:
            lines.append(
                f"| {r['backend']} | {r['case']} | {r['repeat']} | {r['behaviour_failures']} |"
            )
    return lines


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", action="append", required=True, help="comparison output folder")
    parser.add_argument("--dest", required=True)
    parser.add_argument("--notes", help="Markdown file appended to summary.md")
    args = parser.parse_args(argv)

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    rows, ledgers, reference = [], {}, None
    for src in map(Path, args.src):
        src_rows = json.loads((src / "results.json").read_text(encoding="utf-8"))
        rows += src_rows
        ref_path = src / "_reference" / "run_ledger.jsonl"
        if ref_path.exists() and reference is None:
            first = json.loads(ref_path.read_text(encoding="utf-8").splitlines()[0])
            reference = dict(first["headline"], run_id=first["run_id"])
        for backend in sorted({r["backend"] for r in src_rows}):
            ledgers[backend] = ledger_rows(src, backend)
            for md in (src / backend).glob("r*/transcripts/*.md"):
                out = dest / "transcripts" / backend / md.parent.parent.name / md.name
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(md, out)

    (dest / "results.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    with (dest / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    text = summarise(rows).splitlines()
    text += [""] + gate_table(ledgers) + [""] + design_table(rows, reference)
    text += [""] + failure_table(rows)
    text += ["", "Cases: " + ", ".join(f"{k} = {v}" for k, v in CASES.items()) + "."]
    if args.notes:
        text += ["", Path(args.notes).read_text(encoding="utf-8").rstrip()]
    (dest / "summary.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    print(f"Wrote {dest / 'summary.md'} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
