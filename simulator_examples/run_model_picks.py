"""What each LLM picked, against our pick, on one basis and through the same stress tests.

Added 5 Nov 2026 for the video deck. The benchmark's "cheapest design" questions (B1, and
B5b in the same oracle world) asked each model for the cheapest plant on the official
profiles. This script rebuilds the exact design each model answered with from its
transcript (the screen / run_design arguments that produced the picked name, with the
backup sizes the agent set), adds the DeepSeek and Sol answers to the full design brief
(scenario 10, 4 Nov, max reasoning), and runs every plant and our pick:

* on the official profiles, as the benchmark scored it (checks the rebuild),
* on KNMI Schiphol 2025 with CO2 at EUR 80/t (our headline basis),
* through the 13 stress tests of run_stress_margin.py (sized on the 2025 basis).

    PYTHONPATH=src:simulator_examples python simulator_examples/run_model_picks.py ^
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt

Terra's B5b transcript is on the pr39 branch; pass --terra <path> if it is not in the tree.
Writes simulator_examples/outputs/model_picks/: picks.csv, stress.csv, picks.md
(committed copy: simulator_examples/study_results/2026-11-05/model_picks/).
"""

import argparse
import csv
import itertools
import json
import re
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from run_final_pick import INPUTS, PICK
from run_stress_margin import climate_for, tests

from gemini_agent.tools import make_design
from gemini_design.annual import run_year
from gemini_design.ates import MissingWeatherError
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, load_demand
from gemini_design.operations import OperatingRules

HERE = Path(__file__).parent
OUT = HERE / "outputs" / "model_picks"
BENCH = HERE / "agent_bench_results" / "2026-11-04-max"
OBJ = HERE / "agent_compare_results" / "2026-11-04-objective-newdefaults"
TERRA = BENCH / "gpt-6.1-terra" / "fill_1105_0847_B5b" / "gpt-6.1-terra" / "B5b" / "r1"

# (label, model, question, transcript, picked design name); the best-scored run per model
BENCH_PICKS = [
    (
        "GPT-6.1 Sol",
        "B1 r1",
        BENCH / "gpt-6.1-sol/gpt-6.1-sol/B1/r1",
        "2D-3010m-boiler-electric-chp-screw-orc0.35-ret45/29",
    ),
    (
        "GPT-6.1 Terra",
        "B5b r1",
        TERRA,
        "2D-3100m-boiler-electric-chp-screw-orc0.4-esp250v-ret45/28",
    ),
    (
        "GLM 5.3",
        "B1 r1",
        BENCH / "glm-5.3/glm-5.3/B1/r1",
        "2D-3050m-boiler-electric-chp-screw-esp250v-retref/30",
    ),
    (
        "DeepSeek V4.1 Flash",
        "B1 r2",
        BENCH / "deepseek-v4.1-flash/deepseek-v4.1-flash/B1/r2",
        "1D-3040m-boiler-electric-chp-screw-2xB-ret45/28",
    ),
    (
        "Qwen 3.8 27B",
        "B1 r2",
        BENCH / "qwen3.8-27b/A/qwen3.8-27b/B1/r2",
        "1D-3500m-boiler-electric-chp-screw-2xB",
    ),
    (
        "GPT-6 Luna",
        "B1 r1",
        BENCH / "gpt-6-luna/gpt-6-luna/B1/r1",
        "1D-3000m-boiler-electric-chp-screw-2xB",
    ),
]
# answers to the full brief (lowest cost, CO2 at 180 EUR/t, survive a trip on the coldest days)
OBJ_PICKS = [
    ("DeepSeek V4.1 Flash", "brief r1", OBJ / "r1", "R0418"),
    ("GPT-6.1 Sol", "brief r1 (candidate)", OBJ / "sol_r1", "R0514"),
]
TOOL = re.compile(r"^- tool `(screen|run_design)` (\{.*\})\s*$")


def _expand(name, args):
    """Arguments of every design a screen / run_design call asked for."""
    if name == "run_design":
        return [{k: v for k, v in args.items() if k != "assumptions"}]
    vary = args.get("vary") or {}
    extra = [dict(zip(vary, c)) for c in itertools.product(*vary.values())] or [{}]
    chillers = args.get("chiller_types") or ["legacy"]
    out = []
    for n, d, u, c, h, o, x in itertools.product(
        args["n_doublets"],
        args["depths_m"],
        args["upgrades"],
        args["coolings"],
        dict.fromkeys(args.get("chp") or [False]),
        args.get("orc_capacity_mw_el") or [0.0],
        extra,
    ):
        for t in chillers if c == "electric" else ["legacy"]:
            out.append(
                {
                    "n_doublets": n,
                    "depth_m": d,
                    "upgrade": u,
                    "cooling": c,
                    "chp": h,
                    "chiller_type": t,
                    "orc_capacity_mw_el": o,
                    **x,
                }
            )
    return out


def rebuild(run_dir, picked, peak_h, peak_c):
    """Every distinct request in the transcript whose design carries the picked name."""
    md = next(Path(run_dir).glob("transcripts/*.md"))
    found = {}
    for line in md.read_text(encoding="utf-8").splitlines():
        m = TOOL.match(line)
        if not m:
            continue
        for a in _expand(m.group(1), json.loads(m.group(2))):
            ops = bool(a.pop("operating_rules", False))
            try:
                d = make_design(a, peak_h, peak_c)
            except Exception:  # noqa: BLE001 - invalid combos the tool skipped too
                continue
            if d.name == picked:
                found[(repr(sorted(d.as_dict().items())), ops)] = (a, ops)
    m = re.search(
        re.escape(f'"design":"{picked}","lcoe_eur_per_mwh":') + r"([0-9.]+)",
        md.read_text(encoding="utf-8"),
    )
    return list(found.values()), (float(m.group(1)) if m else None)


def _year(job):
    """One 365-day dispatch: (key, request, ops, demand spec, challenge, assumptions)."""
    key, req, ops, spec, ch, a = job
    base = climate_for(spec["knmi"]) if spec["knmi"] else load_demand(INPUTS)
    if spec.get("official"):
        demand = load_demand(INPUTS)
        base = demand
    else:
        demand = climate_for(
            spec["knmi"],
            spec.get("year", 2025),
            spec.get("air", 0.0),
            spec.get("cool", 1.0),
            spec.get("heat", 1.0),
        )
    d = make_design(req, float(base["heating_mw"].max()), float(base["cooling_mw"].max()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            _, s = run_year(
                d,
                demand,
                {**CHALLENGE, **ch},
                {**ASSUMPTIONS, **a},
                operations=OperatingRules() if ops else None,
            )
        except MissingWeatherError:  # ATES needs air temperatures: no official-profile run
            return key, None
    e = s["energy_mwh"]
    return key, {
        "design": d.name,
        "boiler_mw": d.boiler_capacity_mw,
        "chiller_mw": d.chiller_capacity_mw,
        "meets_all_hard_rules": bool(s["all_hard_constraints_met"]),
        "unmet_mwh": round(e["unmet_heating"] + e["unmet_cooling"], 1),
        "lcoe_eur_per_mwh": round(s["economics"]["lcoe_eur_per_mwh"], 2),
        "co2_t_per_year": round(s["kpi"]["co2_t_per_year"]),
        "capex_meur": (
            round(s["economics"]["capex_eur"]["total"] / 1e6, 2)
            if isinstance(s["economics"]["capex_eur"], dict)
            and "total" in s["economics"]["capex_eur"]
            else None
        ),
    }


def main():
    """Rebuild the picks, run them and write the tables."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--knmi", required=True)
    p.add_argument("--terra", help="Terra B5b r1 run folder (with transcripts/)")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    official = load_demand(INPUTS)
    ph, pc = float(official["heating_mw"].max()), float(official["cooling_mw"].max())
    picks = [("Our pick", "headline", dict(PICK), False, None)]
    for label, q, run_dir, name in BENCH_PICKS:
        if label == "GPT-6.1 Terra" and args.terra:
            run_dir = Path(args.terra)
        cands, reported = rebuild(run_dir, name, ph, pc)
        if not cands:
            raise SystemExit(f"{label}: no request in the transcript builds {name}")
        picks += [(label, q, a, ops, reported) for a, ops in cands]
    for label, q, run_dir, rid in OBJ_PICKS:
        for line in open(Path(run_dir) / "run_ledger.jsonl", encoding="utf-8"):
            e = json.loads(line)
            if e.get("run_id") == rid:
                req = {k: v for k, v in e["request"].items() if k not in ("assumptions", "name")}
                ops = bool(req.pop("operating_rules", False))
                picks.append((label, q, req, ops, None))
    peak_day = float(official["heating_mw"].idxmax())
    pool = ProcessPoolExecutor(args.workers)
    # 1) official basis for every candidate; where a name fits several requests (e.g. the
    #    backup boiler size, which the name does not carry), keep the one that reproduces
    #    the LCOE the agent reported
    off = dict(
        pool.map(
            _year,
            [
                ((i, "official"), req, ops, {"knmi": None, "official": True}, {}, {})
                for i, (_, _, req, ops, _) in enumerate(picks)
            ],
        )
    )
    keep = {}
    for i, (label, q, req, ops, reported) in enumerate(picks):
        err = (
            abs(off[(i, "official")]["lcoe_eur_per_mwh"] - reported)
            if (reported and off[(i, "official")])
            else 0.0
        )
        if (label, q) not in keep or err < keep[(label, q)][1]:
            keep[(label, q)] = (i, err)
    picks = [picks[i] for i, _ in keep.values()]
    off = {(j, "official"): off[(i, "official")] for j, (i, _) in enumerate(keep.values())}
    # 2) KNMI 2025 and the 13 stress tests
    jobs = []
    for i, (_, _, req, ops, _) in enumerate(picks):
        for tl, t in tests(peak_day):
            spec = {
                "knmi": args.knmi,
                **{k: t[k] for k in ("year", "air", "cool", "heat") if k in t},
            }
            jobs.append(((i, tl), req, ops, spec, t.get("ch", {}), t.get("a", {})))
    res = {**off, **dict(pool.map(_year, jobs))}
    pool.shutdown()
    OUT.mkdir(parents=True, exist_ok=True)
    names = [tl for tl, _ in tests(peak_day)]
    rows = []
    for i, (label, q, req, ops, reported) in enumerate(picks):
        base, off = res[(i, names[0])], res[(i, "official")] or {"lcoe_eur_per_mwh": float("nan")}
        passed = sum(res[(i, n)]["meets_all_hard_rules"] for n in names)
        rows.append(
            {
                "model": label,
                "question": q,
                "design": base["design"],
                "operating_rules": ops,
                "boiler_mw": base["boiler_mw"],
                "chiller_mw": base["chiller_mw"],
                "official_lcoe": off["lcoe_eur_per_mwh"],
                "reported_lcoe": reported,
                "knmi2025_lcoe": base["lcoe_eur_per_mwh"],
                "knmi2025_co2_t": base["co2_t_per_year"],
                "knmi2025_met": base["meets_all_hard_rules"],
                "stress_passed": passed,
                "stress_total": len(names),
                "stress_failed": "; ".join(
                    f"{n} ({res[(i, n)]['unmet_mwh']} MWh)"
                    for n in names
                    if not res[(i, n)]["meets_all_hard_rules"]
                ),
                "request": json.dumps(req, sort_keys=True),
            }
        )
    with open(OUT / "picks.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(OUT / "stress.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["pick", "model", "test", "meets_all_hard_rules", "unmet_mwh", "lcoe", "co2_t"])
        for i, (label, *_rest) in enumerate(picks):
            for n in names:
                r = res[(i, n)]
                w.writerow(
                    [
                        i,
                        label,
                        n,
                        r["meets_all_hard_rules"],
                        r["unmet_mwh"],
                        r["lcoe_eur_per_mwh"],
                        r["co2_t_per_year"],
                    ]
                )
    lines = [
        "# What each model picked, on our basis and through our 13 stress tests",
        "",
        "Official = the benchmark's basis (official profiles); KNMI 2025 = our headline basis "
        "(CO2 at EUR 80/t inside the LCOE).",
        "",
        "| model | question | design | boiler MW | official EUR/MWh (reported) | KNMI 2025 EUR/MWh "
        "| CO2 t/yr | stress tests met | failed |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        rep = f" ({r['reported_lcoe']})" if r["reported_lcoe"] else ""
        lines.append(
            f"| {r['model']} | {r['question']} | {r['design']} | {r['boiler_mw']:g} "
            f"| {r['official_lcoe']:.2f}{rep} | {r['knmi2025_lcoe']:.2f} | {r['knmi2025_co2_t']} "
            f"| {r['stress_passed']}/{r['stress_total']} | {r['stress_failed']} |"
        )
    (OUT / "picks.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
