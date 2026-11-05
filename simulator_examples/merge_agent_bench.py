"""Merge benchmark v2 runs split over several folders, and rescore design cases
against the best design ANY run found (the "pooled best").

Long runs get split into parallel processes (``--cases`` per process) and restarted
after quota or credit stops, so one backend's rows end up in several folders with
infrastructure rows and duplicates. This script keeps exactly one row per
(backend, case, repeat): the first non-infrastructure row in the order the folders
are given. Backends named in ``--drop`` are left out::

    $env:PYTHONPATH="src"
    python simulator_examples/merge_agent_bench.py `
        simulator_examples/agent_bench_results/2026-11-04-max `
        --out simulator_examples/agent_bench_results/2026-11-04-max/merged `
        --drop qwen3-235b-thinking

Every ``results.json`` under the folder is read (sorted by path, so ``A`` < ``B`` and
``_part2`` < ``_part3``); pass several folders to set the order yourself.

Pooled best: the oracle searches a 300-design grid, but agents can also vary return
temperatures, ESP size, boiler units, ORC and so on, and sometimes find cheaper
designs that still meet every hard rule. Regret against the grid is then clamped at 0
and every such run scores like the grid optimum. For every design case and oracle
world, the pooled best is the cheaper of the grid optimum and the cheapest feasible
design any run recommended; ``pooled_*`` fields rescore correctness against it
(``total`` and ``passed`` are kept as the grid-scored values). Writes results.json,
results.csv, summary.md (grid-scored), summary_pooled.md, pooled_best.md and missing.md
(runs lost to quota or credit stops are left out of the scores and listed there).
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_agent_bench import summarise, write

from gemini_agent.bench import runner
from gemini_agent.bench.cases import CASES, REGRET_ZERO

_PICK = re.compile(
    r"^(?P<label>[\w ]+): (?P<design>\S+) (?P<lcoe>[\d.]+) EUR/MWh vs oracle "
    r"(?P<best_design>\S+) (?P<best>[\d.]+) \(regret"
)


def load(folders):
    """All rows from every results.json under ``folders``, in folder then path order."""
    rows = []
    for folder in folders:
        for path in sorted(Path(folder).rglob("results.json")):
            if any(part.startswith("merged") for part in path.parts):
                continue
            for r in json.loads(path.read_text(encoding="utf-8")):
                r["_source"] = str(path.parent)
                rows.append(r)
    return rows


def dedupe(rows, drop=()):
    """One row per (backend, case, repeat): the first that is not an infrastructure fail."""
    keep, order = {}, []
    for r in rows:
        if r["backend"] in drop:
            continue
        key = (r["backend"], r["case"], r["repeat"])
        if key not in keep:
            order.append(key)
            keep[key] = r
        elif (
            keep[key]["failure"] == "infrastructure"
            and r["failure"] != "infrastructure"
        ):
            keep[key] = r
    case_order = {k: i for i, k in enumerate(CASES)}
    backends = list(dict.fromkeys(k[0] for k in order))
    return sorted(
        keep.values(),
        key=lambda r: (
            backends.index(r["backend"]),
            case_order.get(r["case"], 99),
            r["repeat"],
        ),
    )


def pick(row):
    """(design, lcoe, grid best design, grid best lcoe) from a design-scored row, or None."""
    for n in row.get("notes", []):
        m = _PICK.match(n)
        if m:
            return m["design"], float(m["lcoe"]), m["best_design"], float(m["best"])
    return None


def _world(row):
    case = CASES[row["case"]]
    return row["case"], json.dumps(
        case.oracle(row["variant"]) if case.oracle else {}, sort_keys=True
    )


def pooled(rows):
    """Add pooled_* fields; return {world: (design, lcoe, found_by)} of pooled bests."""
    best = {}
    for r in rows:
        p = pick(r)
        if not p:
            continue
        w = _world(r)
        design, lcoe, gdesign, glcoe = p
        cur = best.get(w, (gdesign, glcoe, "oracle grid"))
        if lcoe < cur[1]:
            cur = (design, lcoe, f"{r['backend']} r{r['repeat']}")
        best[w] = cur
    for r in rows:
        p = pick(r)
        r["pooled_total"], r["pooled_passed"] = r["total"], r["passed"]
        if not p:
            continue
        ref = best[_world(r)][1]
        regret = max(0.0, (p[1] - ref) / ref)
        dims = {
            k: r.get(k) for k in ("correctness", "judgement", "honesty", "efficiency")
        }
        dims["correctness"] = max(0.0, 1.0 - regret / REGRET_ZERO)
        total = runner.total_score(dims, CASES[r["case"]].weights)
        r["pooled_regret_pct"] = round(100 * regret, 2)
        r["pooled_note"] = (
            f"pooled best {ref} EUR/MWh: regret {100 * regret:.1f} % "
            "(grid regret in the note above)"
        )
        r["pooled_correctness"] = round(dims["correctness"], 3)
        r["pooled_total"] = total
        r["pooled_passed"] = total >= runner.PASS_MARK and not r["critical"]
    return best


def main(argv=None):
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--drop", nargs="*", default=[], help="backend labels to leave out")
    args = ap.parse_args(argv)
    rows = dedupe(load(args.folders), set(args.drop))
    missing = {}
    for (
        r
    ) in rows:  # runs lost to quota or credit stops: not scored, listed in missing.md
        if r["failure"] == "infrastructure":
            missing.setdefault(r["backend"], []).append(f"{r['case']} r{r['repeat']}")
    rows = [r for r in rows if r["failure"] != "infrastructure"]
    best = pooled(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "missing.md").write_text(
        "# Runs lost to infrastructure stops (left out of the scores)\n\n"
        + "".join(f"- {b}: {', '.join(m)}\n" for b, m in missing.items())
        + ("" if missing else "None.\n"),
        encoding="utf-8",
    )
    for r in rows:
        r.pop("_source", None)
    write(rows, out)
    pooled_rows = [
        {
            **r,
            "total": r["pooled_total"],
            "passed": r["pooled_passed"],
            "correctness": r.get("pooled_correctness", r["correctness"]),
            "notes": r["notes"] + ([r["pooled_note"]] if "pooled_note" in r else []),
        }
        for r in rows
    ]
    (out / "summary_pooled.md").write_text(
        summarise(pooled_rows).replace(
            "# Agent benchmark v2",
            "# Agent benchmark v2, design cases scored against the pooled best",
            1,
        ),
        encoding="utf-8",
    )
    lines = [
        "# Pooled best design per design case and oracle world",
        "",
        "| case | oracle world | grid best | pooled best | EUR/MWh | found by |",
        "|---|---|---|---|---|---|",
    ]
    for (case, world), (design, lcoe, who) in sorted(best.items()):
        grid = next(pick(r) for r in rows if _world(r) == (case, world) and pick(r))
        lines.append(
            f"| {case} | `{world}` | {grid[2]} {grid[3]} | {design} | {lcoe} | {who} |"
        )
    (out / "pooled_best.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for b, m in missing.items():
        print(f"{b}: left out (infrastructure): {', '.join(m)}")
    print(summarise(pooled_rows).split("## Failures")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
