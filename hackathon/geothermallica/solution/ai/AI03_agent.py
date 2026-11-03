"""The agent loop: brief -> code plan (sweeps, checks) -> model may call more tools -> JSON answer -> AI04 check -> one re-prompt."""
import json
import pathlib
import re
import sys
import time
from datetime import datetime

import AI01_log as log
import AI02_tools as tools
import AI04_check as checker

PROMPTS = pathlib.Path(__file__).parent / "prompts"


def prompt(name):
    """The prompt text in prompts/<name>.md."""
    return (PROMPTS / f"{name}.md").read_text().rstrip("\n")


SYSTEM = prompt("system_design")
PLAN_NOTE = prompt("plan_note")


brief_peak = checker.brief_peak


brief_site = checker.brief_site
SITE_DEFAULTS = {"depth_m": 2500.0, "supply_heat_c": 100.0, "supply_cold_c": 20.0}   # the challenge's site [D]


def pick(sweeps):
    """Smallest n whose best return leaves no heat unmet and has boiler <= 5 % of the heat served [A]; else least boiler."""
    row = lambda s: s["by_return_C"][str(s["best_return_c"])]
    sweeps = [s for s in sweeps if "error" not in s]
    ok = [s for s in sweeps if checker.meets_rule(row(s))]
    s = ok[0] if ok else min(sweeps, key=lambda s: row(s)["boiler_GWh"])
    return s, row(s), bool(ok)


def brief_max_n(brief):
    m = re.search(r"(?:up to|at most|max(?:imum)?)\s+(\d)\s+doublets", brief, re.I)
    return min(3, int(m.group(1))) if m else 3


def brief_inputs(brief):
    """Peaks (heat, cold), the site with defaults filled in, and what the brief gave (None where it gave nothing)."""
    ph, pc = brief_peak(brief, "heat"), brief_peak(brief, "cool")
    found = brief_site(brief)
    site = {k: (v if v is not None else d) for (k, d), v in zip(SITE_DEFAULTS.items(), found)}
    return ph, pc, site, found


def call(name, args):
    """A tool result, or {"error": ...} when the tool rejects its arguments."""
    try:
        return tools.call(name, {**SITE_DEFAULTS, **args} if name == "site_inputs" else args)
    except ValueError as e:
        return {"error": str(e)}


def plan(brief):
    """The tool calls of the code plan: site, demand, a return sweep per n, then checks and years for the chosen design.
    site_inputs is recorded with the values the brief gave; the challenge defaults fill the rest (prose() warns)."""
    ph, pc, _, found = brief_inputs(brief)
    site = {k: v for k, v in zip(SITE_DEFAULTS, found) if v is not None}
    print(f"brief peaks: heat {ph} MW, cold {pc} MW, depth {found[0]} m")
    dep = {} if found[0] is None else {"depth_m": found[0]}   # the brief's depth reaches every tool (rule (e))
    heat = {**dep, **({} if ph is None else {"peak_heat_MW": ph})}
    peaks = {**heat, **({} if pc is None else {"peak_cold_MW": pc})}
    steps = [("site_inputs", site), ("demand_summary", {k: v for k, v in peaks.items() if k != "depth_m"})] + [("return_sweep", {"n_doublets": n, **heat}) for n in range(1, brief_max_n(brief) + 1)]
    out = [{"name": k, "args": a, "result": call(k, a)} for k, a in steps]
    s, _, _ = pick([r["result"] for r in out if r["name"] == "return_sweep"])
    n, t = s["n_doublets"], s["best_return_c"]
    cost = [("economics", {"n_doublets": m, "t_return_c": t, **peaks}) for m in (n, n + 1) if m <= 3]   # what the next doublet costs
    alts = [("layout_compare", {"n_doublets": n, "t_return_c": t, **peaks}), ("storage_point", {"n_doublets": n, "t_return_c": t, **heat})]
    for k, a in (("checks", {"n_doublets": n, "t_return_c": t, **peaks}), *cost, *alts, ("heating_year", {"n_doublets": n, "t_return_c": t, **heat}),
                 ("cooling_year", {"t_return_c": t, "n_doublets": n, **peaks}), ("injector_point", {"q_m3h": 300, **dep})):
        out.append({"name": k, "args": a, "result": call(k, a)})
    econ = {r["args"]["n_doublets"]: r["result"] for r in out if r["name"] == "economics" and "error" not in r["result"]}
    if n in econ and n + 1 in econ:   # the increment is computed here from two tool results, so the checker can trace it
        out.append({"name": "economics_delta", "args": {"from_n": n, "to_n": n + 1},
                    "result": {"delta_lcoh_EUR_MWh": round(econ[n + 1]["lcoh_EUR_MWh"] - econ[n]["lcoh_EUR_MWh"], 2),
                               "delta_capex_MEUR": round(econ[n + 1]["capex_total_MEUR"] - econ[n]["capex_total_MEUR"], 2), "tag": "[C]"}})
    return out


def plan_message(brief, out):
    """The plan's choice in words, from the tool results of plan()."""
    ph, pc, site, found = brief_inputs(brief)
    s, row, ok = pick([r["result"] for r in out if r["name"] == "return_sweep"])
    n, t = s["n_doublets"], s["best_return_c"]
    scale = " ".join(f"{name.capitalize()} demand scaled to the brief's {v} MW peak." if v is not None else
                     f"No {name} peak found in the brief, so the {name} demand file is used as is ({d} MW)."
                     for name, v, d in (("heating", ph, 30.0), ("cooling", pc, 10.0)))
    miss = [f"{k} (default {site[k]:g})" for k, v in zip(site, found) if v is None]
    site_msg = ("Site from the brief: " + ", ".join(f"{k} {v:g}" for k, v in site.items()) + "."
                + (f" Not found in the brief, defaults used: {', '.join(miss)}." if miss else ""))
    si = out[0]["result"]
    if "error" in si:
        site_msg += f" site_inputs rejected these inputs: {si['error']}. The design cannot be trusted for them [C]."
    elif not si["supported"]:
        site_msg += f" {si['message']}. The design cannot be trusted for these inputs [D, A]."
    rule = ("the smallest number of doublets whose best_return_c leaves no heat unmet with boiler energy at most 5 % of the "
            "heat served [A]; so demand_met is true" if ok else
            f"the demand cannot be met with up to {brief_max_n(brief)} doublets at any return; least-boiler option shown; "
            "so demand_met is false")
    econ = {r["args"]["n_doublets"]: r["result"]["lcoh_EUR_MWh"] for r in out if r["name"] == "economics" and "error" not in r["result"]}
    lcoh = "; ".join(f"with {m} doublets {v} EUR/MWh" for m, v in econ.items())
    if n in econ and n + 1 in econ:
        lcoh += f"; so the {({2: 'second', 3: 'third'}[n + 1])} doublet adds {round(econ[n + 1] - econ[n], 2)} EUR/MWh (say this, not the n+1 LCoH, as 'what the next doublet costs')"
    return (f"{site_msg}\n{scale}\nPlan choice: {n} doublets at a {t} C return, {rule}. Boiler energy there: "
            f"{row['boiler_GWh']} GWh of {row['served_GWh']} GWh served ({row['boiler_share_pct']} %), unmet {row['unmet_GWh']} GWh [C]"
            + ("; so boiler_needed_for_energy is true" if row["boiler_GWh"] > 0.01 else "") + "."
            + (f"\nLCoH {lcoh} [C]." if lcoh else "")
            + "\nRejected alternatives (say each in rejected_alternatives with its number and tag, copying these sentences):\n"
            + "\n".join(f"- {x}" for x in rejected(out, n, t)))


def rejected(out, n, t):
    """One copy-ready sentence per alternative the plan priced and did not choose, every number from a tool result in out."""
    res = lambda name, **a: next((r["result"] for r in out if r["name"] == name and "error" not in r["result"]
                                  and all(r["args"].get(k) == v for k, v in a.items())), None)
    lines = []
    fewer = res("return_sweep", n_doublets=n - 1) if n > 1 else None
    if fewer:
        b = fewer["best_return_c"]; r = fewer["by_return_C"][str(b)]
        lines.append(f"Fewer doublets: {n - 1} doublet{'s' if n > 2 else ''} at {'their' if n > 2 else 'its'} best {b} C return leave{'' if n > 2 else 's'} {r['unmet_GWh']} GWh unmet, "
                     f"boiler share {r['boiler_share_pct']} % and peak margin {r['peak_margin_pct']} % [C].")
    delta = res("economics_delta")
    if n < 3 and delta:
        lines.append(f"A {({2: 'second', 3: 'third'})[n + 1]} doublet adds {delta['delta_lcoh_EUR_MWh']} EUR/MWh to the LCoH and "
                     f"{delta['delta_capex_MEUR']} MEUR of CAPEX when {n} already meet the heat [C].")
    lay = res("layout_compare")
    if lay:
        a, b = lay["A"], lay["B"]
        lines.append(f"The boiler-lift layout without heat pump costs {a['lcoh_EUR_MWh']} against {b['lcoh_EUR_MWh']} EUR/MWh, "
                     f"burns {a['gas_GWh']} GWh gas and emits {a['co2_kt']} kt CO2 [C].")
    st = res("storage_point")
    if st:
        lines.append(f"A storage tank instead of the {st['backup_boiler_MW']:g} MW backup boiler: a {st['outage_days']}-day winter outage of one doublet "
                     f"needs {st['tank_for_outage_MWh']:.0f} MWh, {st['tanks_needed']} tanks, {st['tank_cost_MEUR']} MEUR against {st['backup_boiler_MEUR']} MEUR [C, L, A].")
    sw = res("return_sweep", n_doublets=n)
    low = [x for x in tools.SWEEP_C if x < t] if sw else []
    if low:
        r = sw["by_return_C"][str(low[-1])]
        lines.append(f"A lower {low[-1]} C return needs {r['boiler_GWh']} GWh of boiler energy ({r['boiler_share_pct']} % of the heat) [C].")
    return lines


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
                warn.append(f"Warning: no {what} found in the brief; the challenge default {SITE_DEFAULTS[k]:g} {unit} was used [A].")
    for r in results:
        if r["name"] == "demand_summary":
            for k, what in (("peak_heat_MW", "heat"), ("peak_cold_MW", "cold")):
                if k not in r["args"]:
                    warn.append(f"Warning: no {what} peak found in the brief; the challenge default {r['result'][what + '_peak_MW']} MW was used [A].")
    head = "\n".join([first] + warn) + "\n\n"
    open_ = f"\n\nOpen checker problems: {'; '.join(problems)}" if problems else ""
    if "unparsed" in j:
        return head + "No parsable answer." + open_
    c = j.get("cooling", {})
    return head + (f"Build {j.get('n_doublets')} doublets with a {j.get('t_return_c')} C network return. "
            + ("The heat demand is not met with up to 3 doublets. " if j.get("demand_met") is False else "") +
            f"{'A boiler is needed for energy' if j.get('boiler_needed_for_energy') else 'No boiler is needed for energy'}; "
            f"a {j.get('backup_boiler_MW')} MW backup boiler covers security of supply. Constraints: {j.get('checks_passed')} pass. "
            f"Cooling: {c.get('free_pct')} % free, {c.get('absorption_pct')} % absorption, {c.get('electric_pct')} % electric."
            + open_ + "\n\n"
            + "\n".join(f"- {r}" for r in j.get("reasoning", []))
            + ("\n\nRejected alternatives:\n" + "\n".join(f"- {r}" for r in j.get("rejected_alternatives", []))
               if j.get("rejected_alternatives") else ""))


def declare(j, results):
    """Code, not the model, states when site_inputs says the setpoints are unsupported (safety line; F10: the model forgets it)."""
    bad = [r["result"] for r in results if r["name"] == "site_inputs" and isinstance(r["result"], dict) and not r["result"].get("supported", True)]
    if bad and isinstance(j, dict) and "reasoning" in j and not any("not supported" in x.lower() or "cannot be trusted" in x.lower() for x in j["reasoning"]):
        j["reasoning"].append(f"Not supported: supply {bad[0].get('supply_heat_c', 0):g} C heat / {bad[0].get('supply_cold_c', 0):g} C cold is outside the design tables built for 100 C / 20 C, so the design above cannot be trusted [D, site_inputs; code]")
        j["code_added"] = ["reasoning[-1]"]
    return j


def run(brief, free=False):
    t0, records = time.time(), []
    results = [] if free else plan(brief)
    choice = "" if free else plan_message(brief, results)
    content = brief if free else brief + "\n\n" + "\n".join(
        f"{r['name']}({json.dumps(r['args'])}) = {json.dumps(r['result'], separators=(',', ':'))}" for r in results) + \
        f"\n\n{choice}\n{PLAN_NOTE}"
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
    a1 = declare(answer(msgs, records, results, 6, offer_tools=free), results)   # planned: first answer from the plan results, no tools
    p1 = checker.check(a1, msgs, results, brief)
    a2 = p2 = None
    if p1:
        msgs.append({"role": "user", "content": prompt("recheck").replace("{problems}", "\n".join(p1))})
        a2 = declare(answer(msgs, records, results, 3), results)
        p2 = checker.check(a2, msgs, results, brief)
    save(brief, free, msgs, records, results, a1, p1, a2, p2, time.time() - t0)
    return a2 or a1, p1, p2, results


def save(brief, free, msgs, records, results, a1, p1, a2, p2, secs):
    s = log.summary(records, show=False)
    slug = re.sub(r"[^a-z0-9]+", "_", brief.lower())[:40].strip("_") or "brief"
    path = log.RUNS / f"{datetime.now():%Y%m%d_%H%M%S}_{'free' if free else 'plan'}_{slug}.md"
    lines = [f"# Agent run, {MODEL}, {'free (no code plan)' if free else 'code plan'}", "", f"**Brief.** {brief}", "",
             "## Recommendation", "", prose(a2 or a1, results, free, p2 or ()), "", "## First answer", "", "```", json.dumps(a1, indent=1), "```", "",
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


BRIEF = ("District with 30 MW peak heating and 10 MW peak cooling, supply 100 C and 20 C, reservoir at 2500 m. "
         "Recommend the number of doublets and the network return temperature, and tell me whether the design needs "
         "a boiler. Check the constraints.")
MODEL = log.DEFAULT_MODEL

def gemini_version():
    """Path and git commit of the GEMINI package the tools import."""
    import subprocess
    import gemini_model
    root = str(pathlib.Path(gemini_model.__file__).parents[2])
    sha = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    return f"{root} @ {sha or 'no git'}"


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
        print(f"Agent on {MODEL}{' (free mode)' if free else ''}, tools on GEMINI {gemini_version()}.\n"
              "Brief with MW -> design agent, any other question -> notes (RAG). Enter = challenge brief, q = quit.")
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
