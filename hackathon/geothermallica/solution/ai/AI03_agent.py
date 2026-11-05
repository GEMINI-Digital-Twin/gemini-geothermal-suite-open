"""The design agent: brief -> code plan -> model answer in JSON -> AI04 check -> one re-prompt; run file written.

Run: python ai/AI03_agent.py ["<brief>"] [--free]   (no brief: interactive)
"""
import json
import pathlib
import re
import sys
import time
from datetime import datetime

import AI01_log as log
import AI02_tools as tools
import AI03_plan as planner
import AI04_check as checker

PROMPTS = pathlib.Path(__file__).parent / "prompts"


def prompt(name):
    """The prompt text in prompts/<name>.md."""
    return (PROMPTS / f"{name}.md").read_text().rstrip("\n")


SYSTEM = prompt("system_design")
PLAN_NOTE = prompt("plan_note")


def loop(msgs, records, results, max_steps, offer_tools=True):
    for step in range(max_steps):
        msg, rec = log.chat(msgs, tools=tools.TOOLS if offer_tools and step < max_steps - 1 else None, model=MODEL)
        records.append(rec)
        msgs.append({"role": "assistant", "content": msg["content"], "tool_calls": [{"function": c} for c in msg["tool_calls"]]})
        if not msg["tool_calls"]:
            return msg["content"]
        for c in msg["tool_calls"]:
            try:
                res = tools.call(c["name"], c["arguments"])
                results.append({"name": c["name"], "args": c["arguments"], "result": res})
                out = json.dumps(res)
            except Exception as e:
                out = f"error: {e}"
            print(f"  tool: {c['name']}({c['arguments']})")
            msgs.append({"role": "tool", "tool_name": c["name"], "content": out})
    return msgs[-1]["content"]


def answer(msgs, records, results, max_steps, offer_tools=True):
    text = loop(msgs, records, results, max_steps, offer_tools)
    for attempt in range(2):
        try:
            return json.loads(text[text.index("{"):text.rindex("}") + 1])
        except ValueError as e:
            if attempt:
                return {"unparsed": text}
            msgs.append({"role": "user", "content": f"Your final message is not valid JSON ({e}). Reply with the JSON object only."})
            text = loop(msgs, records, results, 1)


PROSE_HEAD = ("Doublet count and return temperature were chosen by the code plan from return_sweep; "
              "the model wrote the explanation below and may have called further tools.")


SITE_WORDS = {"depth_m": ("reservoir depth", "m"), "supply_heat_c": ("heat supply temperature", "C"),
              "supply_cold_c": ("cold supply temperature", "C")}


def _checks_summary(results, j):
    """The checks tool's own summary (x/y pass, computed + declared rows) for the design answered, else the answer's x/y."""
    for r in reversed(list(results)):
        if r["name"] == "checks" and r["result"].get("summary") and r["args"].get("n_doublets") == j.get("n_doublets"):
            return r["result"]["summary"]
    return f"{j.get('checks_passed')} pass"


def prose(j, results=(), free=False, problems=()):
    first = "Free mode: the model chose the doublet count and return temperature and wrote the explanation below." if free else PROSE_HEAD
    warn = []
    for r in results:
        if r["name"] != "site_inputs":
            continue
        if "error" in r["result"]:
            warn.append(f"Warning: site_inputs rejected the brief's site: {r['result']['error']}.")
        elif not r["result"].get("supported", True):
            warn.append(f"Warning: {r['result']['message']}.")
        for k, (what, unit) in SITE_WORDS.items():
            if k not in r["args"]:
                warn.append(f"Warning: no {what} found in the brief; "
                            f"the challenge default {planner.SITE_DEFAULTS[k]:g} {unit} was used [A].")
    for r in results:
        if r["name"] == "demand_summary":
            for k, what in (("peak_heat_MW", "heat"), ("peak_cold_MW", "cold")):
                if k not in r["args"]:
                    warn.append(f"Warning: no {what} peak found in the brief; "
                                f"the challenge default {r['result'][what + '_peak_MW']} MW was used [A].")
    it = next((r["result"] for r in results if r["name"] == "design_iterations"), None)
    if it:
        warn.append(f"Design iterations: {it['tried']} tried, {it['rejected']} rejected"
                    + (f", {it['moves']} repair move{'s' if it['moves'] > 1 else ''} ({it.get('model_moves', 0)} chosen by the model, "
                       f"{it.get('code_moves', 0)} by the code fallback)" if it["moves"] else "") + "; see the run file.")
        for st in it["steps"]:
            if st.get("by"):
                warn.append(f"Repair step by the {st['by']}: {st.get('move') or st['verdict']}, {st['verdict']}"
                            + (f" (checks {st['checks_after']})" if st.get("checks_after") else "") + f"; why: {st['why']}")
    if isinstance(j, dict) and (j.get("code_moved") or j.get("code_added")):
        warn.append("Code repairs: " + "; ".join([j["code_moved"]] * bool(j.get("code_moved")) + [f"added {a}" for a in j.get("code_added", [])]) + ".")
    if isinstance(j, dict) and j.get("code_split"):
        warn.append(f"The model joined its reasoning items into {j['code_split']} string(s); code split them on '; '.")
    head = "\n".join([first] + warn) + "\n\n"
    open_ = f"\n\nOpen checker problems: {'; '.join(problems)}" if problems else ""
    if "unparsed" in j:
        return head + "No parsable answer." + open_
    c = j.get("cooling", {})
    return head + (f"Build {j.get('n_doublets')} doublets with a {j.get('t_return_c')} C network return. "
            + ("The heat demand is not met with up to 3 doublets. " if j.get("demand_met") is False else "") +
            f"{'A boiler is needed for energy' if j.get('boiler_needed_for_energy') else 'No boiler is needed for energy'}; "
            f"a {j.get('backup_boiler_MW')} MW backup boiler covers security of supply. Constraints: {_checks_summary(results, j)}. "
            f"Cooling: {c.get('free_pct')} % free, {c.get('absorption_pct')} % absorption, {c.get('electric_pct')} % electric."
            + (f" GEMINI's own solver: {j['gemini_verification']}" if j.get("gemini_verification") else "")
            + open_ + "\n\n"
            + "\n".join(f"- {r}" for r in j.get("reasoning", []))
            + (f"\n\nChosen from the Pareto front: {j['chosen_design']}. {j.get('trade_off', '')}" if j.get("chosen_design") else "")
            + ("\n\nRejected alternatives:\n" + "\n".join(f"- {r}" for r in j.get("rejected_alternatives", []))
               if j.get("rejected_alternatives") else ""))


def split_joined(j):
    """Small models sometimes join the reasoning items into one string with '; '. Code splits it back; the run file says so."""
    if not isinstance(j, dict) or not isinstance(j.get("reasoning"), list):
        return j
    out = []
    for r in j["reasoning"]:
        if isinstance(r, str) and len(r.split()) > 30 and r.count("; ") >= 2 and r.count("[") >= 3:   # several tagged items in one
            out += [x.strip() for x in r.split("; ") if x.strip()]
            j["code_split"] = j.get("code_split", 0) + 1
        else:
            out.append(r)
    j["reasoning"] = out
    return j


def tidy(j, results):
    """Two repairs the run file records: a replay verdict the model wrote into reasoning moves to its field; the gas option
    the plan priced and did not choose is appended when the model left it out. Both use the tools' own words."""
    if not isinstance(j, dict):
        return j
    moved = [r for r in j.get("reasoning", []) if isinstance(r, str) and r.startswith("GEMINI's solver re-ran")]
    if moved and len(str(j.get("gemini_verification", "")).split()) < 4:
        j["gemini_verification"] = moved[0].replace("[C]", "").strip()
        j["reasoning"] = [r for r in j["reasoning"] if r not in moved]
        j["code_moved"] = "gemini_verification taken from reasoning"
    it = next((r["result"] for r in results if r["name"] == "design_iterations" and isinstance(r["result"], dict)), None)
    for st in (x for x in (it or {}).get("steps", []) if x.get("move") and x.get("by")):
        if isinstance(j.get("reasoning"), list) and not any(f"{st['by']}'s move" in str(r).lower() for r in j["reasoning"]):
            import AI03_plan
            j["reasoning"].append(AI03_plan.violation_sentence(st).replace("[C].", "[C; code]"))
            j["code_added"] = j.get("code_added", []) + ["reasoning[-1]"]
    ec = {r["result"].get("gas_handling"): r["result"] for r in results if r["name"] == "economics"
          and "error" not in r["result"] and r["args"].get("n_doublets") == j.get("n_doublets")
          and r["args"].get("t_return_c") == j.get("t_return_c")}
    gas = next((r["result"].get("gas_handling") for r in results if r["name"] == "gas_choice"), None)
    other = {"engine": "reinject", "reinject": "engine"}.get(gas)
    alts = j.get("rejected_alternatives")
    if gas in ec and other in ec and isinstance(alts, list) and not any(other in str(a).lower() for a in alts):
        import AI03_plan
        alts.append(AI03_plan.gas_sentence(ec[gas], ec[other]).replace("[C, A].", "[C, A; code]."))
        j["code_added"] = j.get("code_added", []) + ["rejected_alternatives[-1]"]
    return j


def declare(j, results):
    """Code, not the model, adds the 'not supported' line when site_inputs rejects the setpoints (small models forget it)."""
    j = tidy(split_joined(j), results)
    bad = [r["result"] for r in results if r["name"] == "site_inputs" and isinstance(r["result"], dict) and not r["result"].get("supported", True)]
    said = lambda x: "not supported" in x.lower() or "cannot be trusted" in x.lower()
    if bad and isinstance(j, dict) and "reasoning" in j and not any(said(x) for x in j["reasoning"]):
        j["reasoning"].append(f"Not supported: supply {bad[0].get('supply_heat_c', 0):g} C heat / {bad[0].get('supply_cold_c', 0):g} C cold "
                              "is outside the design tables built for 100 C / 20 C, so the design above cannot be trusted [D, site_inputs; code]")
        j["code_added"] = j.get("code_added", []) + ["reasoning[-1]"]
    return j


def brief_result(r):
    """A tool result as the model sees it: design_iterations without its swept steps, checks as counts plus the FAIL rows."""
    if r["name"] == "design_iterations":
        return {**r["result"], "steps": [st for st in r["result"]["steps"] if st.get("by")]}   # the repair loop's steps only
    if r["name"] == "optimise_point" and "error" not in r["result"]:
        return {k: v for k, v in r["result"].items() if k not in ("basis", "best_lcoh", "best_co2")}
    if r["name"] == "gemini_replay" and "error" not in r["result"]:
        # the verdict and the per-day residuals; the full rows stay in the run file and go to the checker
        res = r["result"]
        day_keys = ("date", "demand_MW", "freq_hz_ours", "freq_hz_gemini_same_flow", "esp_head_residual_bar",
                    "p_injection_wellhead_residual_bar", "T_supply_C_gemini")
        return {**{k: res[k] for k in ("verdict", "n_days", "gemini_version", "project_path") if k in res},
                "days": [{k: d[k] for k in day_keys if k in d} for d in res["days"]]}
    if r["name"] == "checks" and "error" not in r["result"]:
        res = r["result"]
        keep = {k: v for k, v in res.items() if not k[:2].isdigit() or "FAIL" in str(v)}
        return {**keep, "note": "rows that pass are omitted here; copy n_pass/n_rows into checks_passed (see summary)"}
    return r["result"]


def run(brief, free=False):
    t0, records, exchanges = time.time(), [], []   # exchanges: the repair loop's messages, shown in the run file
    results = [] if free else planner.plan(brief, lambda m, **o: log.chat(m, model=MODEL, **o), records, exchanges)
    choice = "" if free else planner.plan_message(brief, results)
    content = brief if free else brief + "\n\n" + "\n".join(
        f"{r['name']}({json.dumps(r['args'])}) = {json.dumps(brief_result(r), separators=(',', ':'))}" for r in results) + \
        f"\n\n{choice}\n{PLAN_NOTE}"
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
    a1 = declare(answer(msgs, records, results, 6, offer_tools=free), results)   # plan mode: no tools offered for the first answer
    p1 = checker.check(a1, msgs, results, brief)
    a2 = p2 = None
    if p1:
        msgs.append({"role": "user", "content": prompt("recheck").replace("{problems}", "\n".join(p1))})
        a2 = declare(answer(msgs, records, results, 3), results)
        p2 = checker.check(a2, msgs, results, brief)
    if a2 is not None and len(p2) > len(p1):   # the re-prompt made the answer worse: keep the first one
        print(f"re-prompt answer has {len(p2)} problems against {len(p1)}: first answer kept")
        a2, p2 = None, p1
    save(brief, free, [msgs[0], *exchanges, *msgs[1:]], records, results, a1, p1, a2, p2, time.time() - t0)   # the repair exchange first
    return a2 or a1, p1, p2, results


def save(brief, free, msgs, records, results, a1, p1, a2, p2, secs):
    s = log.summary(records, show=False)
    slug = re.sub(r"[^a-z0-9]+", "_", brief.lower())[:40].strip("_") or "brief"
    path = log.RUNS / f"{datetime.now():%Y%m%d_%H%M%S}_{'free' if free else 'plan'}_{slug}.md"
    lines = [f"# Agent run, {MODEL}, {'free (no code plan)' if free else 'code plan'}", "", f"**Brief.** {brief}", "",
             "## Recommendation", "", prose(a2 or a1, results, free, p2 or ()), "", *iteration_table(results),
             "## First answer", "", "```", json.dumps(a1, indent=1), "```", "",
             "Checker problems: " + ("none" if not p1 else "".join(f"\n- {x}" for x in p1)), ""]
    if a2:
        lines += ["## Answer after re-prompt", "", "```", json.dumps(a2, indent=1), "```", "",
                  "Checker problems: " + ("none" if not p2 else "".join(f"\n- {x}" for x in p2)), ""]
    lines += ["## Transcript", ""]
    for m in msgs[1:]:
        calls = "".join(f"\n\n-> `{c['function']['name']}({json.dumps(c['function']['arguments'])})`" for c in m.get("tool_calls", []))
        lines += [f"**{m['role']}**{' ' + m['tool_name'] if m['role'] == 'tool' else ''}", "", (m["content"] or "") + calls, ""]
    lines += ["## Tokens", "", f"{s['calls']} model calls, {s['prompt_tokens']} prompt tokens, {s['completion_tokens']} "
              f"completion tokens, {s['wall_s']:.1f} s in the model, {secs:.1f} s wall", "", "## Data", "", "```json",
              json.dumps({"brief": brief, "free": free, "answer": a1, "problems": p1, "answer_2": a2, "problems_2": p2,
                          "tool_results": results, "transcript": msgs}, default=str), "```", ""]
    path.write_text("\n".join(lines))
    print(f"tokens: {s['calls']} calls, {s['prompt_tokens']} prompt, {s['completion_tokens']} completion, "
          f"{s['wall_s']:.1f} s in the model, {secs:.1f} s wall\nwrote {path}")


def iteration_table(results):
    """The design_iterations steps as a markdown table for the run file (empty in free mode)."""
    it = next((r["result"] for r in results if r["name"] == "design_iterations"), None)
    if not it:
        return []
    rows = [f"| {st['candidate']} | {st['verdict']} | {st['reason']} | {st.get('move') or st.get('number') or ''} | "
            f"{st['by'] + ': ' + str(st['why']) if st.get('by') else ''} |" for st in it["steps"]]
    return ["## Design iterations", "", f"{it['tried']} tried, {it['rejected']} rejected, {it['not_needed']} not needed, {it['moves']} repair moves "
            f"({it.get('model_moves', 0)} by the model, {it.get('code_moves', 0)} by the code); chosen {it['chosen']} [C].", "",
            "| candidate | verdict | reason | number or move | who moved and why |", "|---|---|---|---|---|", *rows, ""]


BRIEF = ("District with 30 MW peak heating and 10 MW peak cooling, supply 100 C and 20 C, reservoir at 2500 m. "
         "Recommend the number of doublets and the network return temperature, and tell me whether the design needs "
         "a boiler. Check the constraints.")
MODEL = log.DEFAULT_MODEL


def ask(brief, free=False):
    """One brief in, recommendation printed, run file written."""
    final, p1, p2, results = run(brief, free=free)
    print("\n" + prose(final, results, free, p2 or ()))
    print(f"\nchecker problems: {len(p1)} first, {'n/a' if p2 is None else len(p2)} after re-prompt\n")
    return final


if __name__ == "__main__":
    free = "--free" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--free"]
    if args:                                   # one brief on the command line
        ask(args[0], free)
    else:                                      # interactive: type a brief, Enter for the challenge brief, q to quit
        print(f"Agent on {MODEL}{' (free mode)' if free else ''}, tools on GEMINI {tools.gemini_version()}.\n"
              "Brief with MW -> design agent, any other question -> GEMINI's docstrings (RAG). Enter = challenge brief, q = quit.")
        while True:
            try:
                line = input("brief or question> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if line.lower() in ("q", "quit", "exit"):
                break
            if not line or re.search(r"\d+(?:\.\d+)?\s*MW\b", line, re.I):
                ask(line or BRIEF, free)
            else:
                import AI06_rag
                AI06_rag.answer(line, show=True)
