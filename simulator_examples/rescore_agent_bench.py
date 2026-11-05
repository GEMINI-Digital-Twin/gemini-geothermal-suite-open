"""Rescore benchmark v2 rows from their Markdown transcripts with the current checkers.

Use this when a checker changes after a live run and the raw workspaces (ledgers,
JSONL transcripts) are not at hand. The transcript holds every tool call with its
arguments and a result preview, every LLM reply and the replies to the user; this
script rebuilds a minimal run ledger from it and reruns ``case.score`` for the cases
named on the command line. Other rows are copied unchanged::

    $env:PYTHONPATH="src"
    python simulator_examples/rescore_agent_bench.py `
        simulator_examples/agent_bench_results/2026-11-01 --cases B8 B10

Writes ``results_rescored.json`` / ``summary_rescored.md`` next to ``results.json``.
Limits: run validity and KPIs come from the result preview (``physics_gate``,
``meets_all_hard_rules``, ``lcoe_eur_per_mwh``); design arguments of screen rows are
read back from the design name. B6 cannot be rescored this way: whether a run passed
the physics gate is the last field of the result and is usually cut from the preview.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

from gemini_agent.bench import runner
from gemini_agent.bench.cases import CASES
from gemini_design.challenge import load_demand

sys.path.insert(0, str(Path(__file__).parent))
from run_agent_bench import summarise  # noqa: E402

_MARK = re.compile(
    r"^(\*\*User:\*\*|> _model thinking_:|> _agent reasoning_|> _LLM call_|- tool `|"
    r"- \*\*physics gate rejected|- physics gate 6|\*\*Agent:\*\*|\*\*Agent asks:\*\*|"
    r"\*\*Agent \(gave up\):\*\*|## Token use)",
    re.M,
)
_NAME = re.compile(
    r"^(\d)D-(\d+)m-(boiler|heat_pump)-(absorption|electric)(-chp)?(-screw|-tower|-aircooled)?"
)
_SHORT = {
    "-screw": "screw_dry_cooler",
    "-tower": "centrifugal_tower",
    "-aircooled": "air_cooled_screw",
}


class _Ledger:
    """Just enough of RunLedger for the claim checker."""

    def __init__(self):
        self.entries = {}
        self.last_id = 0

    def get(self, run_id):
        return self.entries[run_id]

    def put(self, run_id, request, headline, valid):
        old = self.entries.get(run_id)
        if old and not request:
            return
        self.entries[run_id] = {
            "kind": "design",
            "request": request or (old or {}).get("request", {}),
            "headline": headline,
            "valid": valid,
        }


def _next_id(ledger):
    nums = [int(r[1:]) for r in ledger.entries] + [ledger.last_id]
    return f"R{max(nums) + 1:04d}"


def _screen_members(args, result, ledger, oracles):
    """Rebuild the screen's member runs in the order tools.screen creates them.

    The result preview is cut at 400 characters, so most member ids are not in it.
    Members get consecutive ids in grid order (an earlier run_design of the same short
    arguments may have other sizes, so it is not assumed to be reused), then the screen
    takes the next id; their KPIs come from the oracle grid of the same prices.
    """
    combos = [
        (n, d, u, c, h, t)
        for n in args.get("n_doublets", [])
        for d in args.get("depths_m", [])
        for u in args.get("upgrades", [])
        for c in args.get("coolings", [])
        for h in dict.fromkeys(args.get("chp", [False]))
        for t in (
            dict.fromkeys(args.get("chiller_types") or ["legacy"])
            if c == "electric"
            else ["legacy"]
        )
    ]
    if not combos or '"designs_run"' not in result:
        return
    oracle = oracles.get(args.get("assumptions") or {}) if oracles else None
    for n, d, u, c, h, t in combos:
        a = {
            "n_doublets": n,
            "depth_m": float(d),
            "upgrade": u,
            "cooling": c,
            "chp": bool(h),
            "chiller_type": t,
        }
        row = oracle.find(**{**a, "depth_m": int(d)}) if oracle else None
        head = {
            "design": row["design"] if row else None,
            "meets_all_hard_rules": bool(
                row and row["meets_all_hard_rules"] and row["gate_passed"]
            ),
            "lcoe_eur_per_mwh": row["lcoe_eur_per_mwh"] if row else None,
        }
        ledger.put(_next_id(ledger), a, head, True)
    ledger.last_id = int(_next_id(ledger)[1:])  # the screen entry itself


def _args_from_name(name):
    m = _NAME.match(name or "")
    if not m:
        return {}
    return {
        "n_doublets": int(m.group(1)),
        "depth_m": float(m.group(2)),
        "upgrade": m.group(3),
        "cooling": m.group(4),
        "chp": bool(m.group(5)),
        "chiller_type": _SHORT.get(m.group(6), "legacy"),
    }


def _field(text, key):
    m = re.search(rf'"{key}":\s*("?)([^",}}]+)\1', text)
    return m.group(2) if m else None


def parse(md, oracles=None):
    """(events, replies, ledger) from one Markdown transcript."""
    starts = [m.start() for m in _MARK.finditer(md)] + [len(md)]
    blocks = [md[a:b].strip() for a, b in zip(starts, starts[1:])]
    events, replies, ledger = [], [], _Ledger()
    for b in blocks:
        if b.startswith("> _agent reasoning_"):
            events.append({"kind": "llm", "content": b.split("):", 1)[-1].strip()})
        elif b.startswith("- tool `"):
            name = b[len("- tool `") :].split("`", 1)[0]
            head, _, result = b.partition("\n")
            try:
                args = json.loads(head.split("` ", 1)[1])
            except (IndexError, json.JSONDecodeError):
                args = {}
            events.append(
                {"kind": "tool", "name": name, "arguments": args, "result_preview": result}
            )
            if name == "run_design":
                rid = _field(result, "run_id")
                if rid:
                    gate = _field(result, "physics_gate")
                    valid = gate == "pass" if gate else "gate_errors" not in result
                    req = {k: v for k, v in args.items() if k != "assumptions"}
                    req["assumptions"] = args.get("assumptions") or {}
                    if _field(result, "reused_earlier_run"):
                        req = None
                    ledger.put(rid, req, _headline(result, valid), valid)
            elif name == "screen":
                _screen_members(args, result, ledger, oracles)
                for m in re.finditer(r'\{"run_id":"(R\d{4})","design":"([^"]+)"([^}]*)\}', result):
                    lcoe = re.search(r'"lcoe_eur_per_mwh":([\d.]+)', m.group(3))
                    head = {
                        "design": m.group(2),
                        "meets_all_hard_rules": True,  # screen lists feasible rows only
                        "lcoe_eur_per_mwh": float(lcoe.group(1)) if lcoe else None,
                    }
                    ledger.put(m.group(1), _args_from_name(m.group(2)), head, True)
        elif b.startswith("- **physics gate rejected"):
            events.append({"kind": "gate_reject", "answer": ""})
        elif b.startswith("**Agent"):
            kind = (
                "question"
                if b.startswith("**Agent asks")
                else "failed" if b.startswith("**Agent (gave up)") else "answer"
            )
            text = b.split(":**", 1)[1].strip()
            replies.append(SimpleNamespace(kind=kind, text=text, llm_calls=0))
    return events, replies, ledger


def _headline(result, valid):
    lcoe = _field(result, "lcoe_eur_per_mwh")
    return {
        "design": _field(result, "design"),
        "meets_all_hard_rules": _field(result, "meets_all_hard_rules") == "true",
        "lcoe_eur_per_mwh": float(lcoe) if lcoe else None,
        "failed_rules": re.findall(r'"(\w+_met)"', result),
    }


def rescore(row, md, oracles=None):
    """Return a copy of ``row`` with correctness/judgement/honesty/total/passed recomputed."""
    case = CASES[row["case"]]
    events, replies, ledger = parse(md, oracles)
    ctx = SimpleNamespace(
        case=case,
        variant=row["variant"],
        replies=replies,
        events=events,
        ledger=ledger,
        agent=None,
        oracle=oracles.get(case.oracle(row["variant"])) if (case.oracle and oracles) else None,
        new_models={},
        metrics={},
    )
    s = case.score(ctx)
    dims = {k: s.get(k) for k in ("correctness", "judgement", "honesty")}
    dims["efficiency"] = row["efficiency"]
    total = runner.total_score(dims, case.weights)
    critical = bool(s.get("critical"))
    passed = total >= runner.PASS_MARK and not critical
    return {
        **row,
        **{k: (round(v, 3) if v is not None else None) for k, v in dims.items()},
        "total": total,
        "critical": critical,
        "passed": passed,
        "failure": "" if passed else (row["failure"] or "wrong_conclusion"),
        "notes": s.get("notes", []) + ["rescored from transcript"],
    }


def _mark(r):
    return f"{r['total']:.2f}{'P' if r['passed'] else 'f'}{'!' if r['critical'] else ''}"


def main(argv=None):
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder")
    ap.add_argument("--cases", nargs="+", required=True)
    args = ap.parse_args(argv)
    out = Path(args.folder)
    rows = json.loads((out / "results.json").read_text(encoding="utf-8"))
    oracles = runner.OracleCache(load_demand(Path(__file__).parent / "hackathon_inputs"), workers=1)
    new = []
    for row in rows:
        if row["case"] not in args.cases:
            new.append(row)
            continue
        hits = list(
            out.glob(f"{row['backend']}/**/{row['case']}/r{row['repeat']}/transcripts/*.md")
        )
        if not hits:
            print(f"no transcript for {row['backend']} {row['case']} r{row['repeat']}")
            new.append(row)
            continue
        r2 = rescore(row, hits[0].read_text(encoding="utf-8"), oracles)
        if (r2["total"], r2["passed"], r2["critical"]) != (
            row["total"],
            row["passed"],
            row["critical"],
        ):
            print(
                f"{row['backend']:22} {row['case']:4} r{row['repeat']} "
                f"{_mark(row)} -> {_mark(r2)}"
                f"  {r2['notes'][:3]}"
            )
        new.append(r2)
    (out / "results_rescored.json").write_text(json.dumps(new, indent=1), encoding="utf-8")
    (out / "summary_rescored.md").write_text(summarise(new), encoding="utf-8")
    print(summarise(new).split("## Failures")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
