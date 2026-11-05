"""Report agent benchmark scores several ways, so no single choice flatters the models.

Read-only: it never changes a results file. For one run folder it writes
``honest_scores.md`` and ``honest_scores.json`` next to the merged results, with:

1. **Scores three ways** per model:
   - *as graded*: the scores the checkers gave during the run. The checkers were frozen
     before the run started, and no row is rescored by hand. Runs lost to credit or
     quota stops are left out.
   - *lost runs as fails*: every run that never completed because the LLM endpoint
     refused or dropped the request counts as a failed run with total 0.
   - *pooled*: design cases rescored against the cheapest feasible design ANY run found,
     not the 300-design grid. This can only lower scores.
2. **Why runs were lost**: each infrastructure row with the endpoint's error. These are
   402 credit refusals, ChatGPT-plan stops and one dropped connection, not bad JSON or
   context overflows.
3. **Worlds per repeat**: which variant each repeat of each case used. Up to the 4 Nov run,
   ``pick_variant`` could give two repeats the same world (fixed afterwards).
4. **Chance floor**: what an agent with no skill scores.
   - A *silent agent*: it answers every turn with one sentence and runs nothing. It goes
     through the real harness and scorers.
   - A *random rule-meeting design*: for the design cases, the mean score of
     recommending a design drawn at random from the oracle grid's feasible designs.
     Judgement and honesty are set as for the silent agent.
5. **1 Nov run, raw against rescored**: the 1 Nov checker fixes were made after reading
   the transcripts, and every rescored row moved up. Both are listed.

Run it from the repo root::

    $env:PYTHONPATH="src"
    python simulator_examples/benchmark_honest_scores.py `
        simulator_examples/agent_bench_results/2026-11-04-max `
        --merged simulator_examples/agent_bench_results/2026-11-04-max/merged_pre_terra
"""

import argparse
import json
import statistics
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gemini_agent.bench import runner  # noqa: E402
from gemini_agent.bench.cases import CASES, REGRET_ZERO  # noqa: E402
from gemini_agent.llm import ScriptedLLM  # noqa: E402
from gemini_design.challenge import load_demand  # noqa: E402

INPUTS = ROOT / "simulator_examples" / "hackathon_inputs"
OLD_RUN = ROOT / "simulator_examples" / "agent_bench_results" / "2026-11-01"
SILENT = "I can't help with that."
LCOE_DESIGN_CASES = ("B1", "B4", "B5a", "B5b")  # scored on LCOE regret against the oracle
NAMES = {
    "gpt-6.1-sol": "GPT-6.1 Sol",
    "gpt-6.1-terra": "GPT-6.1 Terra",
    "gpt-6-luna": "GPT-6 Luna",
    "deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
    "glm-5.3": "GLM 5.3",
    "qwen3.8-27b": "Qwen 3.8 27B",
    "qwen3-235b": "Qwen3 235B",
}


def _name(b):
    return NAMES.get(b, b)


def raw_rows(folder):
    """Every row of every results.json under ``folder`` except merged ones."""
    rows = []
    for path in sorted(Path(folder).rglob("results.json")):
        if any(p.startswith("merged") for p in path.relative_to(folder).parts):
            continue
        for r in json.loads(path.read_text(encoding="utf-8")):
            r["_source"] = path.parent.relative_to(folder).as_posix()
            rows.append(r)
    return rows


def lost_runs(raw, merged):
    """(backend, case, repeat) keys with no completed row, and each one's last error."""
    done = {(r["backend"], r["case"], r["repeat"]) for r in merged}
    lost = {}
    for r in raw:
        key = (r["backend"], r["case"], r["repeat"])
        if key not in done and r["failure"] == "infrastructure":
            lost[key] = r
    return lost


def _error(r):
    text = (r.get("final_reply") or "").replace("The language model could not be reached: ", "")
    if "402" in text:
        return "OpenRouter 402: credit reserved for the uncapped output ran out"
    if "codex exec failed" in text:
        return "Codex CLI exit 1 (ChatGPT plan usage limit window)"
    if "ended prematurely" in text:
        return "connection dropped mid-response"
    return text[:80]


def _stats(totals, passes):
    n = len(totals)
    if not n:
        return {"runs": 0, "mean": None, "pass": None}
    return {
        "runs": n,
        "mean": round(statistics.fmean(totals), 3),
        "pass": round(100 * sum(passes) / n),
    }


def three_ways(merged, lost):
    """Per backend: as graded, lost runs counted as fails, pooled."""
    by = defaultdict(list)
    for r in merged:
        by[r["backend"]].append(r)
    out = {}
    for b, rows in by.items():
        n_lost = sum(1 for k in lost if k[0] == b)
        graded = _stats([r["total"] for r in rows], [r["passed"] for r in rows])
        as_fail = _stats(
            [r["total"] for r in rows] + [0.0] * n_lost,
            [r["passed"] for r in rows] + [False] * n_lost,
        )
        pooled = _stats(
            [r.get("pooled_total", r["total"]) for r in rows],
            [r.get("pooled_passed", r["passed"]) for r in rows],
        )
        out[b] = {"lost": n_lost, "graded": graded, "lost_as_fail": as_fail, "pooled": pooled}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["graded"]["mean"]))


def worlds(merged):
    """{case: {repeat: variant}} as run (the same for every backend), plus available n."""
    out = {}
    for r in merged:
        out.setdefault(r["case"], {})[r["repeat"]] = json.dumps(r["variant"], sort_keys=True)
    return out


def silent_floor(oracles):
    """Each case run through the harness with an agent that only says ``SILENT``."""
    rows = {}
    for case in runner.all_cases():
        variant = runner.pick_variant(case, 0)
        n_turns = len(case.turns(variant))
        steps = [{"content": SILENT}] * (n_turns + runner.MAX_QUESTIONS_PER_TURN * n_turns)
        ws = Path(tempfile.gettempdir()) / "bench_floor" / case.key
        row = runner.run_case(case, variant, oracles, ws, llm=ScriptedLLM(steps), label="silent")
        rows[case.key] = row
    return rows


def random_design_floor(oracles, silent):
    """Design cases: mean total for a random feasible grid design, other dims as silent."""
    out = {}
    for case in runner.all_cases():
        if case.key not in LCOE_DESIGN_CASES:
            continue
        corr = []
        for v in case.variants:
            o = oracles.get(case.oracle(v))
            best = o.best["lcoe_eur_per_mwh"]
            corr += [
                max(0.0, 1.0 - max(0.0, (r["lcoe_eur_per_mwh"] - best) / best) / REGRET_ZERO)
                for r in o.feasible
            ]
        s = silent[case.key]
        dims = {
            "correctness": statistics.fmean(corr),
            "judgement": s["judgement"],
            "honesty": 1.0,
            "efficiency": 1.0,
        }
        total = runner.total_score(dims, case.weights)
        share = sum(c > 0 for c in corr) / len(corr)
        p_pass = sum(
            runner.total_score({**dims, "correctness": c}, case.weights) >= runner.PASS_MARK
            for c in corr
        ) / len(corr)
        out[case.key] = {
            "correctness": round(dims["correctness"], 3),
            "total": total,
            "share_within_10pct": round(share, 3),
            "pass_rate": round(p_pass, 3),
            "n_feasible": len(corr),
        }
    return out


def old_run_diff():
    """1 Nov: rows whose total changed between results.json and results_rescored.json."""
    raw = json.loads((OLD_RUN / "results.json").read_text(encoding="utf-8"))
    res = json.loads((OLD_RUN / "results_rescored.json").read_text(encoding="utf-8"))
    changed, by = [], defaultdict(lambda: {"raw": [], "res": [], "rp": [], "sp": []})
    for a, b in zip(raw, res):
        assert (a["backend"], a["case"], a["repeat"]) == (b["backend"], b["case"], b["repeat"])
        d = by[a["backend"]]
        d["raw"].append(a["total"])
        d["res"].append(b["total"])
        d["rp"].append(a["passed"])
        d["sp"].append(b["passed"])
        if abs(a["total"] - b["total"]) > 1e-9:
            changed.append((a["backend"], a["case"], a["repeat"], a["total"], b["total"]))
    table = {
        b: {
            "raw": _stats(d["raw"], d["rp"]),
            "rescored": _stats(d["res"], d["sp"]),
        }
        for b, d in by.items()
    }
    return table, changed


def _f(x, nd=2):
    return "–" if x is None else f"{x:.{nd}f}"


def write_md(path, ways, lost, wmap, silent, rnd, old, changed, merged_name):
    """Write honest_scores.md."""
    L = [
        "Author: Sa'eed Telvari",
        "",
        "# Agent benchmark scores, reported several ways",
        "",
        "Made by `simulator_examples/benchmark_honest_scores.py`. It reads the results and "
        f"changes nothing. Merged rows are from `{merged_name}/`.",
        "",
        "## 1. Scores three ways (4 Nov max-thinking run)",
        "",
        "- **As graded:** the scores the checkers gave during the run. Every checker fix "
        "was made before the run started (last benchmark code change 786f1a3, 3 Nov; run "
        "on e0007ae), and no row was rescored afterwards. Runs lost to credit or quota "
        "stops are left out.",
        "- **Lost runs as fails:** every lost run counts as a failure with total 0.",
        "- **Pooled:** design cases are rescored against the cheapest feasible design that "
        "any run found, not the grid optimum. This can only lower a score.",
        "",
        "| model | runs scored | lost | as graded: mean / pass | lost as fails: mean / pass "
        "| pooled: mean / pass |",
        "|---|---|---|---|---|---|",
    ]
    for b, w in ways.items():
        g, a, p = w["graded"], w["lost_as_fail"], w["pooled"]
        L.append(
            f"| {_name(b)} | {g['runs']} | {w['lost']} | {_f(g['mean'])} / {g['pass']} % | "
            f"{_f(a['mean'])} / {a['pass']} % | {_f(p['mean'])} / {p['pass']} % |"
        )
    floor_mean = statistics.fmean(r["total"] for r in silent.values())
    floor_pass = sum(r["passed"] for r in silent.values())
    L += [
        f"| *silent agent (chance floor)* | {len(silent)} | – | {_f(floor_mean)} / "
        f"{round(100 * floor_pass / len(silent))} % | – | – |",
        "",
        "## 2. Why runs were lost",
        "",
        "A run is lost when the LLM endpoint refused or dropped the request. In the merged "
        "results every such run was rerun where credit or quota allowed. The ones below "
        "never completed. No lost run comes from a model error such as bad JSON or an "
        "overflowing context.",
        "",
        "| model | case | repeat | error |",
        "|---|---|---|---|",
    ]
    for (b, c, k), r in sorted(lost.items()):
        L.append(f"| {_name(b)} | {c} | r{k} | {_error(r)} |")
    if not lost:
        L.append("| – | – | – | none |")
    L += [
        "",
        "## 3. Which world each repeat saw",
        "",
        "Every model saw the same worlds, so the models compare fairly. But the old "
        "`pick_variant` drew a fresh random offset for every repeat, so some repeats "
        "shared a world. The fix (`variants[(repeat + seed) % n]`) applies to new runs. "
        "`--legacy-variants` keeps the old mapping for filling in rows of this run.",
        "",
        "| case | worlds available | repeats r1 / r2 / r3 | distinct worlds tested |",
        "|---|---|---|---|",
    ]
    for c, reps in wmap.items():
        n = len(CASES[c].variants)
        if n < 2:
            continue
        seq = [reps.get(k, "?") for k in (1, 2, 3)]
        keys = [json.dumps(x, sort_keys=True) for x in CASES[c].variants]
        names = {v: i for i, v in enumerate(keys)}
        L.append(
            f"| {c} | {n} | {' / '.join('v' + str(names.get(s, '?')) for s in seq)} | "
            f"{len(set(seq))} of {n} |"
        )
    L += [
        "",
        "v0, v1, ... are the case's variants in the order they are listed in "
        "`bench/cases.py`. B3: cap 6 / 8 / 12 %. B4: (gas, CO2, power) 90/180/70, "
        "30/50/200, 120/250/120. B10: notes, tool. B13: four planted faults.",
        "",
        "## 4. Chance floor",
        "",
        "Honesty and efficiency come almost free to an agent that does nothing: it makes "
        "no false claim and uses one LLM call. So a raw total says little without the "
        "floor next to it.",
        "",
        "| case | silent agent total | random rule-meeting design: total | its correctness | "
        "chance it passes |",
        "|---|---|---|---|---|",
    ]
    for c, s in silent.items():
        r = rnd.get(c)
        L.append(
            f"| {c} | {_f(s['total'])} | {_f(r['total']) if r else '–'} | "
            f"{_f(r['correctness']) if r else '–'} | "
            f"{(str(round(100 * r['pass_rate'])) + ' %') if r else '–'} |"
        )
    L += [
        f"| **mean** | **{_f(floor_mean)}** | | | |",
        "",
        "The silent agent ran through the real harness and scorers, with one reply per "
        f'turn ("{SILENT}"). The random design is drawn from the oracle grid\'s designs '
        "that meet every hard rule, for the cases scored on LCOE regret (B1, B4, B5a, B5b). "
        "Its correctness is the mean regret score over them, assuming it used any stated "
        "prices; its other dimensions are the silent agent's.",
        "",
        "## 5. 1 Nov run: raw against rescored",
        "",
        "After the 1 Nov run, four checker bugs were found by reading the transcripts and "
        "fixed (`2026-11-01/notes.md`). B8 and B10 were rescored from the transcripts. "
        f"{len(changed)} rows changed, all of them upward. B6 could not be rescored, "
        "though the bug there hurt GLM and Qwen. That is why the 4 Nov run was made with "
        "the fixed checkers frozen.",
        "",
        "| model | raw: mean / pass | rescored: mean / pass |",
        "|---|---|---|",
    ]
    for b, d in old.items():
        L.append(
            f"| {_name(b)} | {_f(d['raw']['mean'])} / {d['raw']['pass']} % | "
            f"{_f(d['rescored']['mean'])} / {d['rescored']['pass']} % |"
        )
    L += ["", "Rows that changed:", ""]
    for b, c, k, a, z in changed:
        L.append(f"- {_name(b)} {c} r{k}: {a:.2f} → {z:.2f}")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None):
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", help="run folder with the per-backend results")
    ap.add_argument("--merged", required=True, help="folder with the merged results.json")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args(argv)
    folder, merged_dir = Path(args.folder), Path(args.merged)
    merged = json.loads((merged_dir / "results.json").read_text(encoding="utf-8"))
    lost = lost_runs(raw_rows(folder), merged)
    ways = three_ways(merged, lost)
    oracles = runner.OracleCache(load_demand(INPUTS), workers=args.workers)
    silent = silent_floor(oracles)
    rnd = random_design_floor(oracles, silent)
    old, changed = old_run_diff()
    out = folder / "honest_scores.md"
    write_md(out, ways, lost, worlds(merged), silent, rnd, old, changed, merged_dir.name)
    data = {
        "three_ways": ways,
        "lost": [
            {"backend": b, "case": c, "repeat": k, "error": _error(r)}
            for (b, c, k), r in sorted(lost.items())
        ],
        "silent_floor": {
            c: {k: r[k] for k in ("total", "passed", "correctness", "judgement", "honesty")}
            for c, r in silent.items()
        },
        "random_design_floor": rnd,
        "old_run": old,
        "old_run_changed": changed,
    }
    (folder / "honest_scores.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
