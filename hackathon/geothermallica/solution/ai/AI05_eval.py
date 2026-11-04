"""Six briefs x two modes through AI03, scored against the expected design; writes runs/eval_table.md."""
import json
import re
import sys
import time

import AI01_log as log
import AI03_agent as agent

BRIEFS = [
    ("A 30/10", agent.BRIEF, (2, 60, False)),
    ("B 12/3", "Small district: 12 MW peak heating, 3 MW peak cooling, supply 100 C, cooling supply 20 C, reservoir 2500 m. "
               "How many doublets, what return, boiler needed?", (1, 60, True)),
    ("C 20/6", "Town: 20 MW peak heating, 6 MW peak cooling, supply 100 C and 20 C, reservoir 2500 m. Doublets, return, boiler?",
     (2, 60, False)),
    ("D 45/10", "Large district: 45 MW peak heating, 10 MW peak cooling, supply 100 C and 20 C, reservoir at 2500 m. "
                "How many doublets, which return, is a boiler needed?", (3, 60, False)),
    ("E 30/10 at 3000 m", "District 30 MW peak heating, 10 MW peak cooling, supply 100 C and 20 C, reservoir 3000 m. "
                          "Doublets, return, boiler?", (3, 60, False)),   # at 3000 m two doublets are 3 % short at the peak
    ("F 30/10 ESP 800 m", "District with 30 MW peak heating and 10 MW peak cooling, supply 100 C and 20 C, reservoir at 2500 m, ESP at 800 m. "
                          "How many doublets, what return, boiler needed?", (2, 60, False)),
    # F exercises the repair: the ESP at 800 m fails the free-gas check and the plan moves it to 1100 m
]
# expected (n, return, boiler) per brief, from return_sweep


def tokens_since(n0):
    recs = [json.loads(l) for l in log.LOG.read_text().splitlines()[n0:]]
    return len(recs), sum(r["prompt_eval_count"] or 0 for r in recs), sum(r["eval_count"] or 0 for r in recs)


def passed(name, j, p2, expected, text, results=()):
    if expected is None:   # the tool must flag the site and the final text must say so
        flagged = any(r["name"] == "site_inputs" and not r["result"].get("supported", True) for r in results if isinstance(r["result"], dict))
        return flagged and bool(re.search(r"not supported|cannot be trusted", text, re.I))
    n, t, b = expected
    return (j.get("n_doublets") == n and float(j.get("t_return_c") or -1) == t and bool(j.get("boiler_needed_for_energy")) is b)


MODES = (False,) if "--plan" in sys.argv else (False, True)   # --plan: code-plan mode only (model ablation)
rows = []
for name, brief, expected in BRIEFS:
    for free in MODES:
        n0, t0 = len(log.LOG.read_text().splitlines()) if log.LOG.exists() else 0, time.time()
        j, p1, p2, results = agent.run(brief, free=free)
        secs = time.time() - t0
        calls, ptok, ctok = tokens_since(n0)
        probs = p2 if p2 is not None else p1
        text = json.dumps(j) + agent.prose(j, results, free)   # no open problems here: (g)'s text says 'not supported'
        ok = passed(name, j, p2, expected, text, results)
        rows.append((name, "free" if free else "plan", j.get("n_doublets"), j.get("t_return_c"), j.get("boiler_needed_for_energy"),
                     j.get("boiler_energy_GWh"), j.get("demand_met"), j.get("checks_passed"), len(probs), calls, ptok, ctok,
                     round(secs, 1), ok, ok and not probs))

head = ("| brief | mode | n | return C | boiler | boiler GWh | met | checks | problems | calls | prompt tok | completion tok | s | pass | clean |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
table = head + "\n" + "\n".join("| " + " | ".join(str(x) for x in r) + " |" for r in rows)
tot = "| mode | runs | passes | clean | mean prompt tok | mean s | cost |\n|---|---|---|---|---|---|---|"
for mode in ("plan", "free"):
    rs = [r for r in rows if r[1] == mode]
    if not rs:
        continue
    tot += (f"\n| {mode} | {len(rs)} | {sum(r[13] for r in rs)} | {sum(r[14] for r in rs)} | {sum(r[10] for r in rs) / len(rs):.0f} | "
            f"{sum(r[12] for r in rs) / len(rs):.1f} | 0 EUR |")
out = (f"# Multi-brief evaluation, {agent.MODEL}, {time.strftime('%Y-%m-%d %H:%M')}\n\n"
       "Expected: A 2/60/no boiler, B 1/60/boiler (outage), C 2/60/no, D 3/60/no, E 3/60/no (3000 m: 2 doublets are 3 % short at the peak), "
       f"F 2/60/no with the ESP repaired from 800 to 1100 m. All [C].\n\n{table}\n\n{tot}\n")
slug = re.sub(r"[^a-z0-9]+", "_", agent.MODEL.lower()).strip("_")
(log.RUNS / ("eval_table.md" if len(MODES) == 2 and agent.MODEL == "qwen3:4b-instruct-2507-q4_K_M" else f"eval_table_{slug}.md")).write_text(out)
print(out)
