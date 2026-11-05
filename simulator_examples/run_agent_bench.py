"""Benchmark v2: run the B cases for one or more LLM backends and score them.

Backends are ``label=provider:model`` as in ``compare_agent_models.py``, or ``good`` /
``bad`` for the scripted policies (``bad`` runs every bad policy of every case)::

    $env:PYTHONPATH="src"
    python simulator_examples/run_agent_bench.py `
        --backend deepseek-v4.1-flash=openrouter:deepseek/deepseek-v4.1-flash-1017 `
        --backend gpt-6.1-sol=codex:gpt-6.1-sol `
        --price deepseek-v4.1-flash=0.0141,0.158 --repeats 3

The oracle grid (300 year runs per price set) is built first and cached in
``simulator_examples/outputs/oracle/`` by a hash of the model code. Writes
``results.json`` / ``results.csv`` (one row per backend x case x repeat) and
``summary.md`` to ``--out`` (default ``simulator_examples/outputs/agent_bench``).
"""

import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path

from gemini_agent import tools
from gemini_agent.bench import runner
from gemini_agent.bench.oracle import SMALL_GRID
from gemini_design.challenge import add_inputs_argument, default_inputs_dir, load_demand

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "agent_bench"


def parse_backend(spec):
    """``label=provider:model`` -> (label, provider, model); ``good``/``bad`` -> scripted."""
    if spec in ("good", "bad"):
        return spec, "scripted", None
    label, _, rest = spec.partition("=")
    provider, _, model = rest.partition(":")
    if not label or not provider:
        raise ValueError(f"backend must look like label=provider:model, got '{spec}'")
    return label, provider, model or None


def cost_usd(row, price):
    """USD for a row at ``price`` = (input, output[, cached input]) per M tokens.

    Cached prompt tokens are billed at the cached rate; prompt_tokens includes them.
    """
    if not price:
        return 0.0
    pin, pout = price[0], price[1]
    pcached = price[2] if len(price) > 2 else pin
    cached = min(row.get("cached_tokens", 0) or 0, row["prompt_tokens"])
    usd = (row["prompt_tokens"] - cached) * pin + cached * pcached + row["completion_tokens"] * pout
    return round(usd / 1e6, 4)


def bootstrap_ci(values, n=2000, seed=0):
    """95 % bootstrap interval of the mean."""
    if not values:
        return (None, None)
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(n))
    return round(means[int(0.025 * n)], 3), round(means[int(0.975 * n) - 1], 3)


def summarise(rows):
    """Markdown summary: per backend, per case, pass^k, CIs and failure classes."""
    by = {}
    for r in rows:
        by.setdefault(r["backend"], []).append(r)
    cases = list(dict.fromkeys(r["case"] for r in rows))
    lines = [
        "# Agent benchmark v2",
        "",
        "Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + "
        "0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing "
        "critical. pass^k = share of cases where every repeat passed.",
        "",
        "| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement "
        "| honesty | efficiency | critical | USD at --price | USD billed |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def mean(rs, k):
        v = [r[k] for r in rs if r.get(k) is not None]
        return f"{sum(v) / len(v):.2f}" if v else "-"

    for label, rs in by.items():
        lo, hi = bootstrap_ci([r["total"] for r in rs])
        per_case = {}
        for r in rs:
            per_case.setdefault(r["case"], []).append(r["passed"])
        passk = sum(all(v) for v in per_case.values()) / len(per_case)
        lines.append(
            f"| {label} | {len(rs)} | {mean(rs, 'total')} ({lo}-{hi}) | "
            f"{sum(r['passed'] for r in rs) / len(rs):.0%} | {passk:.0%} | "
            f"{mean(rs, 'correctness')} | "
            f"{mean(rs, 'judgement')} | {mean(rs, 'honesty')} | {mean(rs, 'efficiency')} | "
            f"{sum(r['critical'] for r in rs)} | {sum(r.get('cost_usd', 0) for r in rs):.3f} | "
            f"{sum(r.get('billed_usd', 0) or 0 for r in rs):.3f} |"
        )
    lines += ["", "## Mean total per case", "", "| backend | " + " | ".join(cases) + " |"]
    lines.append("|---|" + "---|" * len(cases))
    for label, rs in by.items():
        cells = []
        for c in cases:
            cr = [r for r in rs if r["case"] == c]
            cells.append(
                f"{sum(r['total'] for r in cr) / len(cr):.2f} "
                f"({sum(r['passed'] for r in cr)}/{len(cr)})"
                if cr
                else "-"
            )
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "## Failures", "", "| backend | case | variant | total | class | notes |"]
    lines.append("|---|---|---|---|---|---|")
    for r in rows:
        if not r["passed"]:
            notes = "; ".join(r["notes"])[:220]
            lines.append(
                f"| {r['backend']} | {r['case']} | {json.dumps(r['variant'])} | {r['total']} | "
                f"{r['failure'] or ('critical' if r['critical'] else '')} | {notes} |"
            )
    return "\n".join(lines) + "\n"


def write(rows, out):
    """Write results.json, results.csv and summary.md."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    keys = [k for k in rows[0] if k not in ("notes", "questions", "final_reply")]
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys + ["notes"], extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**{k: r[k] for k in keys}, "notes": "; ".join(r["notes"])})
    (out / "summary.md").write_text(summarise(rows), encoding="utf-8")


def main(argv=None):
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backend", action="append", required=True)
    ap.add_argument("--cases", nargs="*", default=None, help="case keys (default all)")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument(
        "--first-repeat",
        type=int,
        default=1,
        help="run repeats K..--repeats only (same variants and labels as a full run)",
    )
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--legacy-variants",
        action="store_true",
        help="old repeat-to-world mapping (up to the 4 Nov 2026 run), for filling in its rows",
    )
    ap.add_argument(
        "--price",
        action="append",
        default=[],
        help="label=usd_in,usd_out[,usd_cached_in] per M tokens (cached defaults to usd_in)",
    )
    ap.add_argument("--small-grid", action="store_true", help="test grid (16 designs) as oracle")
    ap.add_argument(
        "--workers", type=int, default=int(os.environ.get("GEMINI_AGENT_SCREEN_WORKERS", 4))
    )
    ap.add_argument("--no-shared-cache", action="store_true", help="re-simulate repeated designs")
    ap.add_argument("--keep", action="store_true", help="append to earlier results.json")
    ap.add_argument("--out", default=str(OUT))
    add_inputs_argument(ap)
    args = ap.parse_args(argv)
    out = Path(args.out)
    prices = {}
    for p in args.price:
        label, _, nums = p.partition("=")
        prices[label] = tuple(float(x) for x in nums.split(","))
    if not args.no_shared_cache:
        tools.SHARED_YEAR_CACHE = {}
    demand = load_demand(args.inputs)
    oracles = runner.OracleCache(
        demand, grid=SMALL_GRID if args.small_grid else None, workers=args.workers
    )
    cases = runner.all_cases(args.cases)
    for case in cases:  # build every oracle first, so model runs are not slowed by it
        if case.oracle:
            for v in case.variants:
                o = oracles.get(case.oracle(v))
                print(
                    f"oracle {case.key} {v}: best {o.best['design']} {o.best['lcoe_eur_per_mwh']}"
                )
    rows = []
    if args.keep and (out / "results.json").exists():
        rows = json.loads((out / "results.json").read_text(encoding="utf-8"))
    for spec in args.backend:
        label, provider, model = parse_backend(spec)
        for case in cases:
            for k in range(args.first_repeat - 1, args.repeats):
                variant = runner.pick_variant(case, k, args.seed, legacy=args.legacy_variants)
                ws = out / label / case.key / f"r{k + 1}"
                if provider == "scripted":
                    policies = ["good"] if label == "good" else list(case.bad)
                    results = [
                        runner.run_scripted(case, variant, oracles, ws / p, policy=p)
                        for p in policies
                    ]
                else:
                    cfg = {"provider": provider, "model": model, "screen_workers": args.workers}
                    results = [
                        runner.run_case(
                            case, variant, oracles, ws, config_overrides=cfg, label=label
                        )
                    ]
                for row in results:
                    row["repeat"] = k + 1
                    row["cost_usd"] = cost_usd(row, prices.get(label))
                    rows.append(row)
                    print(
                        f"{row['backend']:22} {case.key:4} r{k + 1} total {row['total']:.2f} "
                        f"{'PASS' if row['passed'] else 'fail'} {row['failure']} "
                        f"{row['notes'][:2]}",
                        flush=True,
                    )
                write(rows, out)
    print(summarise(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
