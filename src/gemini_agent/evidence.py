"""Evidence appendix: turn agent sessions into a readable record of prompts, answers and tokens.

  PYTHONPATH=src python -m gemini_agent.evidence [--bakeoff runs/bakeoff] [--results out.json] \
      runs/<session> [runs/<session> ...] > evidence.md

``--results`` also writes a compact JSON (bake-off table, per-scenario cost) that the report
builder reads.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


_TURNS = {"S1": 1, "S2": 2, "S3": 1, "S4": 1, "S5": 3, "S6": 2}  # user turns per scenario


def session_markdown(run_dir: Path, title: str | None = None) -> str:
    """Markdown record of one session."""
    meta = (
        json.loads((run_dir / "meta.json").read_text()) if (run_dir / "meta.json").exists() else {}
    )
    turns = _jsonl(run_dir / "transcript.jsonl")
    trace = _jsonl(run_dir / "trace.jsonl")
    ledger = _ledger(run_dir)
    llm = [e for e in trace if e["type"] == "llm"]
    head = title or " · ".join(
        x for x in (meta.get("scenario"), meta.get("model"), run_dir.name) if x
    )
    host = meta.get("llm_host", "")
    where = "laptop CPU via SSH tunnel" if "11435" in host else "VPS CPU" if host else "n/a"
    mem = meta.get("memory_at_start", "")
    n_lessons = mem.count("verifier rejection") if mem else 0
    out = [
        f"## {head}",
        f"Model `{meta.get('model')}` · profile `{meta.get('profile')}` · mode "
        f"`{meta.get('mode')}` · "
        f"harness `{meta.get('harness')}` · LLM on {where} · inputs {meta.get('inputs', 'default')}"  # noqa: E501
        + (
            f" · site weather: {meta['weather']} (documented default, loaded by the harness)"
            if meta.get("weather")
            else ""
        ),
        f"*Memory at start:* {n_lessons} lesson(s) from earlier sessions"
        + (
            " — "
            + "; ".join(
                ln.split(") ", 1)[-1] for ln in mem.split("\n") if "verifier rejection" in ln
            )
            if n_lessons
            else ""
        ),
        "",
    ]
    gen = sorted(run_dir.glob("agent_generated_*.py"))
    if gen:
        out += [
            "*Model Forge output kept with this session:* " + ", ".join(g.name for g in gen),
            "",
        ]
    for i, t in enumerate(turns, 1):
        p = t["provenance"]
        out += [f"### Turn {i}", "**User:**", "", f"> {t['user']}", ""]
        if t.get("harness_notes"):
            out += [
                "*Harness notes (deterministic, from the request parser):* "
                + " ".join(t["harness_notes"]),
                "",
            ]
        if t.get("llm_retries"):
            out += [
                f"*LLM server error (Ollama rejected a malformed tool call); the harness retried "
                f"{t['llm_retries']}x from the last checkpoint.*",
                "",
            ]
        if t.get("request_screen"):
            out += [
                f"*Request screen (deterministic, before the LLM):* {'; '.join(t['request_screen'])}",  # noqa: E501
                "",
            ]
        if t.get("revised_from"):
            r = t["revised_from"]
            out += [
                "**Agent (first draft, rejected by the verifier):**",
                "",
                r["answer"].strip(),
                "",
                "*Rejected for:* "
                + "; ".join(
                    [c["detail"] for c in r["provenance"].get("claim_issues", [])]
                    + [
                        f"{u['number']} written as '{u['unit_written']}'"
                        for u in r["provenance"]["unit_mismatches"]
                    ]
                    + [f"untraceable {x:g}" for x in r["provenance"]["unsupported"]]
                ),
                "",
            ]
        out += [
            "**Agent (final answer):**",
            "",
            t["answer"].strip() or "_(no answer)_",
            "",
            f"*Verifier:* {p['numbers_checked']} numbers checked; untraceable: "
            f"{p['unsupported'] or 'none'}; unit mismatches: "
            f"{[(u['number'], u['unit_written']) for u in p.get('unit_mismatches', [])] or 'none'}; "  # noqa: E501
            f"contradicted claims: {[c['detail'] for c in p.get('claim_issues', [])] or 'none'}  ",
            *(
                [
                    f"*Verifier feedback loop:* first draft rejected "
                    f"({len(t['revised_from']['provenance'].get('unsupported', []))} unsupported "
                    f"number(s), {len(t['revised_from']['provenance'].get('claim_issues', []))} "
                    f"claim, {len(t['revised_from']['provenance']['unit_mismatches'])} unit "
                    f"issue(s)); one revision requested; final verdict: "
                    f"{'accepted' if p.get('passed') else 'still rejected (shown as unverified)'}  "
                ]
                if t.get("revised_from")
                else []
            ),
            *_recheck(t, ledger),
            *(
                [f"*Memory written:* {'; '.join(t['memory_lessons'])}  "]
                if t.get("memory_lessons")
                else []
            ),
            f"*Cost:* {t['llm_calls']} LLM calls, {t['prompt_tokens']:,} prompt + "
            f"{t['completion_tokens']:,} completion tokens, {t['seconds']} s wall time  ",
            f"*Tool sequence:* {' → '.join(t['tool_calls']) or '(none)'}",
            "",
        ]
    if llm:
        out += [
            "#### Per-call token log",
            "",
            "| # | agent | prompt tok | completion tok | latency s | tool calls |",
            "|---|---|---|---|---|---|",
        ]
        for j, e in enumerate(llm, 1):
            calls = ", ".join(tc["name"] for tc in e.get("tool_calls", [])) or "(answer)"
            out.append(
                f"| {j} | {e['agent']} | {e['prompt_tokens']} | {e['completion_tokens']} | "
                f"{e['latency_s']} | {calls} |"
            )
        out += [
            "",
            f"**Totals:** {len(llm)} calls, {sum(e['prompt_tokens'] for e in llm):,} prompt + "
            f"{sum(e['completion_tokens'] for e in llm):,} completion tokens, "
            f"{round(sum(e['latency_s'] for e in llm), 1)} s LLM time.",
            "",
        ]
    expected = _TURNS.get(meta.get("scenario"), len(turns))
    if len(turns) < expected:  # the session died before the scenario's last turn
        n_llm = sum(1 for e in _jsonl(run_dir / "trace.jsonl") if e.get("type") == "llm")
        out += [
            f"### Turn {len(turns) + 1}",
            "*Session ended with an LLM-server error: Ollama rejected a malformed tool call "
            f"(HTTP 500) twice, once after a retry from the last checkpoint. {n_llm} LLM calls in "
            "total; the trace shows the tool sequence up to the crash.*",
            "",
        ]
    return "\n".join(out)


def _ledger(run_dir: Path):
    """The session's fact ledger, re-loaded for re-verification with the current checks."""
    from gemini_agent.ledger import FactLedger
    from gemini_agent.physics.site import Brief

    led = FactLedger(seed=Brief.load().raw)
    for f in _jsonl(run_dir / "ledger.jsonl"):
        led.record(f["tool"], {k: v for k, v in f["args"].items() if k != "s"}, f["result"])
    return led


def _recheck(turn: dict, ledger) -> list[str]:
    """A line for sessions recorded before a check existed, when today's verifier disagrees."""
    from gemini_agent.ledger import provenance_check

    now = provenance_check(turn["answer"], ledger)
    if now["passed"] == turn["provenance"].get("passed") or now["passed"]:
        return []
    why = [c["detail"] for c in now["claim_issues"]] + [
        f"untraceable {x:g}" for x in now["unsupported"]
    ]
    return [
        f"*Re-check with the current verifier (session recorded before the check existed):* "
        f"REJECTED — {'; '.join(why)}  "
    ]


def _bakeoff_rows(bake_dir: Path) -> list[dict]:
    rows = []
    for f in sorted(bake_dir.glob("*.json")):
        r = json.loads(f.read_text())
        r["failed"] = ", ".join(t["task"].split("_")[0] for t in r["tasks"] if not t["pass"]) or "—"
        rows.append(r)
    return rows


def router_markdown(path: Path) -> str:
    """Router calibration: held-out accuracy, calibration error and the threshold table."""
    r = json.loads(path.read_text())
    raw, cal = r["raw"], r["calibrated_cv"]
    out = [
        "## Optional router: calibration on labelled turns",
        "",
        f"Model `{r['model']}`, {r['n']} labelled turns (`data/router_labels.yaml`), one call each "
        f"(mean {r['router_prompt_tokens_mean']} prompt tokens + 1 completion token, "
        f"{r['router_latency_s_mean']} s). "
        f"Temperature fitted by 2-fold cross-validation ({r['cv_temperatures'][0]:g} / "
        f"{r['cv_temperatures'][1]:g}); "
        "all numbers below are held-out.",
        "",
        "| | accuracy | NLL | ECE |",
        "|---|---|---|---|",
        f"| raw log-probabilities | {raw['accuracy']} | {raw['nll']} | {raw['ece']} |",
        f"| temperature-scaled | {cal['accuracy']} | {cal['nll']} | {cal['ece']} |",
        "",
        "Turns the router would answer itself (off-topic / vague) by confidence threshold — a "
        "*false act* "
        "is a turn answered by the router with the wrong class:",
        "",
        "| threshold | raw: answers / false acts | calibrated: answers / false acts |",
        "|---|---|---|",
    ]
    for a, b in zip(raw["thresholds"], cal["thresholds"]):
        out.append(
            f"| {a['threshold']} | {a['router_answers']} / {a['false_acts']} | "
            f"{b['router_answers']} / {b['false_acts']} |"
        )
    out += [
        "",
        f"Selected threshold: **{r['threshold']}**. Misclassified turns (true → predicted, "
        "calibrated confidence): " + "; ".join(f"{a} → {b} ({c})" for a, b, c in cal["confusion"]),
        "",
    ]
    return "\n".join(out)


def bakeoff_markdown(bake_dir: Path) -> str:
    """Every bake-off prompt with the model's raw reply (tool calls / text), tokens and verdict."""
    from gemini_agent.bakeoff import TASKS

    prompts = {t["id"]: t["messages"][0].content for t in TASKS}
    ctx = {
        t["id"]: [
            m.tool_calls[0]["name"] for m in t["messages"][1:] if getattr(m, "tool_calls", None)
        ]
        for t in TASKS
    }
    out = [
        "## Model bake-off: prompts, replies and scores",
        "",
        "Each task is one LLM call with the real system prompt and tool schemas; scoring is "
        "deterministic "
        "(see `gemini_agent/bakeoff.py`). T3 is an infeasible request, T4 an irrelevant one, T5 an "
        "incomplete one.",
        "",
        "| task | prompt | prior tool results in context |",
        "|" + "-" * 24 + "|" + "-" * 46 + "|" + "-" * 16 + "|",
    ]
    out += [
        f"| {k.replace('_', ' ')} | {v} | {', '.join(ctx.get(k, [])) or '—'} |"
        for k, v in prompts.items()
    ]
    out.append("")
    for r in _bakeoff_rows(bake_dir):
        out += [
            f"### {r['model']} — {r['score']}/{r['n']}"
            + ("" if r.get("complete", True) else " (incomplete run)"),
            "",
            f"Mean latency {r['mean_latency_s']} s; tokens {r['prompt_tokens']:,} prompt + "
            f"{r['completion_tokens']:,} completion.",
            "",
            "| task | reply (tool calls / text) | tok in/out | s | verdict |",
            "|----|" + "-" * 56 + "|----------|------|-------|",
        ]  # dash counts set the PDF column widths
        for t in r["tasks"]:
            reply = "; ".join(f"{c['name']}({json.dumps(c['args'])})" for c in t["tool_calls"])
            text = (t["text"] or "").replace("\n", " ")[:300]
            reply = " ".join(x for x in (reply, text) if x).replace("|", "/") or "(empty reply)"
            out.append(
                f"| {t['task'].split('_')[0]} | {reply} | "
                f"{t['prompt_tokens']}/{t['completion_tokens']} | "
                f"{t['latency_s']} | {'PASS' if t['pass'] else 'fail'} |"
            )
        out.append("")
    return "\n".join(out)


def results_json(paths: list[Path], bake_dir: Path | None) -> dict:
    """Compact data for the report builder."""
    res = {
        "bakeoff": (
            [
                {
                    k: r[k]
                    for k in (
                        "model",
                        "score",
                        "n",
                        "mean_latency_s",
                        "prompt_tokens",
                        "completion_tokens",
                        "failed",
                    )
                }
                for r in _bakeoff_rows(bake_dir)
            ]
            if bake_dir
            else []
        ),
        "scenarios": [],
    }
    for p in paths:
        meta = json.loads((p / "meta.json").read_text()) if (p / "meta.json").exists() else {}
        turns = _jsonl(p / "transcript.jsonl")
        if not turns:
            continue
        res["scenarios"].append(
            {
                "session": p.name,
                "scenario": meta.get("scenario"),
                "model": meta.get("model"),
                "turns": len(turns),
                "llm_calls": sum(t["llm_calls"] for t in turns),
                "prompt_tokens": sum(t["prompt_tokens"] for t in turns),
                "completion_tokens": sum(t["completion_tokens"] for t in turns),
                "seconds": round(sum(t["seconds"] for t in turns)),
                "tools": [c for t in turns for c in t["tool_calls"]],
                "verifier_passed": all(t["provenance"].get("passed", True) for t in turns),
                "untraceable": sorted({x for t in turns for x in t["provenance"]["unsupported"]}),
            }
        )
    return res


def main(argv: list[str]):
    """Print the appendix for the given session directories (and the bake-off)."""
    bake = results = router = None
    paths = []
    it = iter(argv)
    for a in it:
        if a == "--bakeoff":
            bake = Path(next(it))
        elif a == "--router":
            router = Path(next(it))
        elif a == "--results":
            results = Path(next(it))
        else:
            paths.append(Path(a))
    print("# Appendix: agent interaction evidence\n")
    if bake:
        print(bakeoff_markdown(bake))
        print()
    if router:
        print(router_markdown(router))
        print()
    for p in paths:
        print(session_markdown(p))
        print()
    if results:
        results.write_text(json.dumps(results_json(paths, bake), indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
