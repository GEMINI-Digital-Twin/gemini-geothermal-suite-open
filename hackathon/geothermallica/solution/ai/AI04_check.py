"""Check a final JSON answer against the tool results the model saw; each problem is prefixed by its rule (a) to (j).
(a) 'best' needs a sweep (b) tags (c) numbers from tools (d) consistency (e) brief values used (f) shape (g) site (h) alternatives
(i) trace (j) the chosen design is on the Pareto front and the trade-off quotes its numbers
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import AI01_log as log
from geo.rule import rule_failures, meets_rule  # noqa: E402, F401  (one source of truth for the doublet rule)

WORDS = re.compile(r"\b(optimal|best|lowest|cheapest)\b", re.I)
TAG = re.compile(r"\[(?:[CDLA]|TBC)[^\]]*\]")   # [C], [C, A], [L, DEA], [TBC]
NUM = re.compile(r"\d+(?:\.\d+)?")
NUM_UNIT = re.compile(r"\d+(?:\.\d+)?\s*(?:MW|GWh|C|%|m3/h|bar|days|d)(?![A-Za-z0-9])")
FIELDS = {("heating_capacity_MW",): ("heating_year", "capacity_MW"),
          ("peak_heat_MW_by_source", "exchanger"): ("heating_year", "peak_exchanger_MW"),
          ("peak_heat_MW_by_source", "heat_pump"): ("heating_year", "peak_heat_pump_MW"),
          ("peak_heat_MW_by_source", "boiler"): ("heating_year", "peak_boiler_MW"),
          ("peak_cold_MW_by_source", "free"): ("cooling_year", "peak_free_MW"),
          ("peak_cold_MW_by_source", "absorption"): ("cooling_year", "peak_absorption_MW"),
          ("peak_cold_MW_by_source", "electric"): ("cooling_year", "peak_electric_MW"),
          ("electricity_GWh", "esp"): ("heating_year", "esp_electricity_GWh"),
          ("electricity_GWh", "heat_pump"): ("heating_year", "heat_pump_electricity_GWh"),
          ("electricity_GWh", "injection_pump"): ("heating_year", "injection_pump_electricity_GWh"),
          ("electricity_GWh", "chillers"): ("cooling_year", "chiller_electricity_GWh")}
OPTIONAL = {("lcoh_EUR_MWh",): ("economics", "lcoh_EUR_MWh")}   # checked only when the answer has the field


def norm(brief):
    """'2 500 m' -> '2500 m', '100 °C' -> '100 C'."""
    return re.sub(r"(?<=\d) (?=\d{3}\b)", "", brief.replace("°", ""))


def brief_peak(brief, kind):
    """'<x> MW peak heat(ing)' or 'peak heat(ing) of <x> MW' (kind 'heat' or 'cool'); None if the brief has neither."""
    brief = norm(brief)
    word = r"heat(?:ing)?" if kind == "heat" else r"(?:cool(?:ing)?|cold)"
    m = (re.search(rf"(\d+(?:\.\d+)?)\s*MW\s+(?:of\s+)?peak\s+{word}", brief, re.I)
         or re.search(rf"peak\s+{word}(?:\s+demand)?\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*MW", brief, re.I))
    return float(m.group(1)) if m else None


def brief_site(brief):
    """Depth, heating supply and cooling supply from the brief; None for each one not found."""
    brief = norm(brief)
    d = (re.search(r"(?:reservoir|depth)\D{0,20}?(\d+(?:\.\d+)?)\s*(km|m)\b", brief, re.I)
         or re.search(r"(\d+(?:\.\d+)?)\s*(km|m)\s+(?:deep|depth)", brief, re.I))
    depth = None if d is None else float(d.group(1)) * (1000 if d.group(2).lower() == "km" else 1)
    supply = r"supply\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*C\b"
    h = re.search(r"heat(?:ing)?\s+" + supply, brief, re.I)
    if h is None:   # a plain "supply N C", never one after cool/cooling/cold
        h = next((m for m in re.finditer(r"(?:(\w+)\s+)?" + supply, brief, re.I)
                  if not re.fullmatch(r"cool(?:ing)?|cold", m.group(1) or "", re.I)), None)
    c = (re.search(r"(?:cool(?:ing)?|cold)\s+" + supply, brief, re.I)
         or re.search(r"supply\s+\d+(?:\.\d+)?\s*C\s+and\s+(\d+(?:\.\d+)?)\s*C\b", brief, re.I))
    return depth, (float(h.groups()[-1]) if h else None), (float(c.group(1)) if c else None)


def brief_priority(brief):
    """'co2' when the brief asks for the lowest CO2, emissions or a green design; else 'lcoh' (cheapest heat, the default)."""
    return "co2" if re.search(r"(lowest|reduce|minimi[sz]e|least)\s+(the\s+)?(CO2|carbon)|emissions|green|climate", brief, re.I) else "lcoh"


def brief_stated_priority(brief):
    """True when the brief says what comes first (cheapest, lowest cost, lowest CO2, emissions, green)."""
    return bool(re.search(r"cheapest|lowest\s+cost|(lowest|reduce|minimi[sz]e|least)\s+(the\s+)?(CO2|carbon)|emissions|green|climate", brief, re.I))


def brief_esp(brief):
    """ESP setting depth in m when the brief gives one ('ESP at 800 m', 'pump at 800 m'; never 'heat pump'); else None."""
    m = re.search(r"(?<!heat )(?:ESP|pump)\D{0,15}?(\d{3,4})\s*m\b", norm(brief), re.I)
    return float(m.group(1)) if m else None


def close(x, p):
    """x (the model's number, as text) equals p rounded to as many significant digits as x has."""
    n = max(1, len(str(x).replace(".", "").lstrip("0")))
    return float(f"{float(p):.{n}g}") == float(x)


def check(run_json, transcript, tool_results, brief=""):
    """Problems of run_json (the parsed answer) against tool_results [{"name", "args", "result"}] and the brief."""
    problems, brief = [], norm(brief)
    reasoning = [str(r) for r in run_json.get("reasoning", [])]
    called = {r["name"] for r in tool_results}
    for r in reasoning:
        if WORDS.search(r) and "return_sweep" not in called:
            problems.append(f"(a) '{WORDS.search(r).group(0)}' without a return_sweep comparison: {r}")
        if not TAG.search(r):
            problems.append(f"(b) no [tag]: {r}")
        words = len(r.split())
        if not 4 <= words <= 30:
            problems.append(f"(f) {words} words, need 4 to 30: {r}")
        if not NUM.search(TAG.sub("", r)):
            problems.append(f"(f) no number in: {r}")
    n_model = len([x for x in reasoning if not x.rstrip().endswith("; code]")])   # items appended by code are not counted
    if not 3 <= n_model <= 15:
        problems.append(f"(f) {n_model} reasoning items, need 3 to 15")
    ph = brief_peak(brief, "heat")
    if ph is not None and not any(float(x) == ph for r in reasoning for x in NUM.findall(TAG.sub("", r))):
        problems.append(f"(f) the brief's peak heat {ph:g} MW appears in no reasoning item")
    pool = [float(x) for r in tool_results for x in NUM.findall(json.dumps(r["result"]))]
    in_brief = [float(x) for x in NUM.findall(brief)]
    alts = run_json.get("rejected_alternatives")
    alts_s = [str(x) for x in alts] if isinstance(alts, list) else []
    for r in reasoning + alts_s:
        for x in NUM.findall(TAG.sub("", r)):
            if (float(x) < 13 and "." not in x) or any(close(x, b) for b in in_brief):
                continue
            if not any(close(x, p) for p in pool):
                problems.append(f"(c) {x} not in any tool result of this run: {r}")
    problems += check_alternatives(alts, called)
    sweeps = {r["result"]["n_doublets"]: r["result"] for r in tool_results if r["name"] == "return_sweep"}
    n, t, boiler = run_json.get("n_doublets"), run_json.get("t_return_c"), run_json.get("boiler_needed_for_energy")
    met = any(meets_rule(sm["by_return_C"][str(sm["best_return_c"])]) for sm in sweeps.values())
    if sweeps and run_json.get("demand_met") is not met:
        problems.append(f"(d) demand_met={run_json.get('demand_met')} but the sweeps say {met}"
                        + ("" if met else ": no swept number of doublets meets the heat with boiler at most 5 %"))
    s = sweeps.get(n)
    if s is None:
        problems.append(f"(d) no return_sweep for n_doublets={n}, so the return temperature is not compared")
    else:
        row = s["by_return_C"].get(str(int(t)) if t is not None and float(t).is_integer() else str(t))
        if row is None:
            problems.append(f"(d) t_return_c={t} is not one of the swept returns {list(s['by_return_C'])}")
        else:
            if bool(boiler) != (row["boiler_GWh"] > 0.01):
                problems.append(f"(d) boiler_needed_for_energy={boiler} but the sweep shows {row['boiler_GWh']} GWh boiler at {t} C")
            be = run_json.get("boiler_energy_GWh")
            if not isinstance(be, (int, float)) or isinstance(be, bool) or not close(be, row["boiler_GWh"]):
                problems.append(f"(d) boiler_energy_GWh={be} but the sweep shows {row['boiler_GWh']} GWh boiler at {t} C")
            if row["unmet_GWh"] >= 0.01 and met:   # when nothing meets the demand, the plan already says so
                problems.append(f"(d) {row['unmet_GWh']} GWh unmet at {n} doublets, {t} C")
            if "backup_boiler_MW" in s and run_json.get("backup_boiler_MW") != s["backup_boiler_MW"]:
                problems.append(f"(d) backup_boiler_MW={run_json.get('backup_boiler_MW')} but the sweep gives {s['backup_boiler_MW']} MW")
            if t != s["best_return_c"] and not (boiler and t < s["best_return_c"]):
                problems.append(f"(d) t_return_c={t} but the sweep's best_return_c is {s['best_return_c']} for {n} doublets")
    iters = next((r["result"] for r in tool_results if r["name"] == "design_iterations"), {})
    n_moved = any(st.get("key") == "n_doublets" for st in iters.get("steps", []))   # a repair added a doublet on purpose
    opt = next((r["result"] for r in tool_results if r["name"] == "optimise_point" and "error" not in r["result"]), None)
    n_moved = n_moved or bool(opt and any(p["n"] == n for p in opt["front"]))       # or the front holds a row with this n
    for m, sm in sweeps.items():
        best = sm["by_return_C"][str(sm["best_return_c"])]
        if n is not None and m < n and meets_rule(best) and not n_moved:
            problems.append(f"(d) {m} doublets already meet the heat with boiler at most 5 % of it at {sm['best_return_c']} C; "
                            f"{n} is more than needed")
    last = [r for r in tool_results if r["name"] == "checks" and r["args"].get("n_doublets") == n and r["args"].get("t_return_c") == t
            and "error" not in r["result"]]
    if last:   # the last checks call is the design after any repair move
        r = last[-1]
        if run_json.get("checks_passed") != f"{r['result']['n_pass']}/{r['result'].get('n_rows', 13)}":
            problems.append(f"(d) checks_passed={run_json.get('checks_passed')} but checks gives "
                            f"{r['result']['n_pass']}/{r['result'].get('n_rows', 13)}")
    same = lambda r: r["args"].get("n_doublets", 2) == n and r["args"].get("t_return_c") == t
    found = {r["name"]: r["result"] for r in tool_results if r["name"] in ("heating_year", "cooling_year") and same(r)}
    for path, (tool, key) in FIELDS.items():
        v = run_json
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
        name, w = ".".join(path), found.get(tool, {}).get(key)
        if w is None:
            problems.append(f"(d) {name}: no {tool} {key} for {n} doublets at {t} C to check it against")
        elif not isinstance(v, (int, float)) or isinstance(v, bool):
            problems.append(f"(d) {name} missing, {tool} gives {w}")
        elif not close(v, w):
            problems.append(f"(d) {name}={v} but {tool} gives {w}")
    econ = {r["name"]: r["result"] for r in tool_results if r["name"] == "economics" and same(r)}
    for path, (tool, key) in OPTIONAL.items():
        v, w = run_json.get(path[0]), econ.get(tool, {}).get(key)
        if v is None:
            continue
        if w is None:
            problems.append(f"(d) {path[0]}={v} but no {tool} result for {n} doublets at {t} C to check it against")
        elif not isinstance(v, (int, float)) or isinstance(v, bool) or not close(v, w):
            problems.append(f"(d) {path[0]}={v} but {tool} gives {w}")
    args = [float(v) for r in tool_results for v in r["args"].values() if isinstance(v, (int, float))]
    parsed = zip((brief_peak(brief, "heat"), brief_peak(brief, "cool"), *brief_site(brief), brief_esp(brief)), ("MW", "MW", "m", "C", "C", "m"))
    for x, unit in parsed:
        if x is not None and x not in args:
            problems.append(f"(e) brief value {x:g} {unit} never reached a tool")
    if any(r["name"] == "site_inputs" and not r["result"].get("supported", False) for r in tool_results):   # an error counts as unsupported
        if not re.search(r"not supported|cannot be trusted", " ".join(reasoning), re.I):
            problems.append("(g) site_inputs says the setpoints are not supported, but the reasoning does not say "
                            "'not supported' or 'cannot be trusted'")
    if iters:
        problems += check_iterations(iters, run_json, reasoning, tool_results)
    if opt:
        problems += check_choice(run_json, opt, brief_stated_priority(brief))
    return problems


PASS_REASONS = ("meets the rule", "needs boiler energy", "a lower return meets the rule")   # rows that meet the rule but were not chosen


def check_iterations(it, run_json, reasoning, tool_results):
    """(i) design_iterations: counts, chosen design, said in reasoning, verdicts recomputed, moves reached later tools."""
    p = []
    sweeps = {}
    for r in tool_results:   # the plan's own sweeps: the first one per n
        if r["name"] == "return_sweep" and "error" not in r["result"]:
            sweeps.setdefault(r["result"]["n_doublets"], r["result"])
    pairs = {(m, t) for m, s in sweeps.items() for t in s["by_return_C"]}
    if it.get("tried") != len(pairs):
        p.append(f"(i) design_iterations tried={it.get('tried')} but the sweeps hold {len(pairs)} (n, return) pairs")
    ans = (run_json.get("n_doublets"), run_json.get("t_return_c"))
    on_front = any((st["n_doublets"], st["t_return_c"]) == ans for st in it.get("steps", []) if st.get("front"))
    if (it.get("n_doublets"), it.get("t_return_c")) != ans and not on_front:
        p.append(f"(i) design_iterations chose {it.get('chosen')} but the answer says "
                 f"{run_json.get('n_doublets')} doublets at {run_json.get('t_return_c')} C")
    tried = str(it.get("tried"))
    if not any(re.search(rf"(?<![\d.]){tried}(?![\d.])", r) and re.search(r"tried|candidates", r, re.I) for r in reasoning):
        p.append(f"(i) no reasoning item states the {tried} candidates the plan tried (copy the 'Design iterations' line)")
    any_ok = any(meets_rule(s["by_return_C"][t]) for s in sweeps.values() for t in s["by_return_C"])
    for st in it.get("steps", []):
        if st.get("move") or st.get("front") or st.get("verdict") not in ("chosen", "rejected"):
            continue
        row = sweeps.get(st.get("n_doublets"), {}).get("by_return_C", {}).get(str(st.get("t_return_c")))
        if row is None:
            p.append(f"(i) step {st.get('candidate')}: no sweep row to recompute it from")
            continue
        fails = [f[0] for f in rule_failures(row)]
        if st["reason"] in PASS_REASONS and fails:
            p.append(f"(i) step {st['candidate']}: '{st['reason']}' but the sweep row fails {', '.join(fails)}")
        elif st["reason"] not in PASS_REASONS and st["reason"] not in fails:
            p.append(f"(i) step {st['candidate']}: rejected for '{st['reason']}' but the sweep row fails {fails or 'nothing'}")
        if st["verdict"] == "chosen" and fails and any_ok:
            p.append(f"(i) step {st['candidate']}: chosen but it fails {', '.join(fails)} while another candidate meets the rule")
    moves = [st for st in it.get("steps", []) if st.get("move")]
    checks = [r for r in tool_results if r["name"] == "checks" and "error" not in r["result"]]
    used = lambda k, v: [r for r in tool_results if r["name"] != "design_iterations" and r["args"].get(k) == v]
    for st in moves:
        k, v = st["key"], st["to"]
        if k in ("esp_depth_m", "n_doublets") and (not checks or checks[-1]["args"].get(k) != v):
            p.append(f"(i) move {st['move']}: the final checks call does not use {k}={v:g}")
        if not used(k, v):
            p.append(f"(i) move {st['move']}: no tool result has {k}={v:g} in its args")
    if moves and checks and checks[-1]["result"]["n_fail"] > 0 and not any(st["verdict"] == "still failing" for st in moves):
        p.append(f"(i) the final checks still fail {checks[-1]['result']['n_fail']} rows but no step says 'still failing'")
    return p


def check_choice(run_json, opt, stated):
    """(j) chosen_design is a front row, the answer follows it, trade_off quotes its LCoH and CO2, and the row stays within 5 % of the
    front's best on the brief's priority when the brief states one."""
    c, tr, front = run_json.get("chosen_design"), run_json.get("trade_off"), opt["front"]
    if not front:
        return []
    if not isinstance(c, dict):
        return ["(j) chosen_design missing: copy one row of the Pareto front as {n, t_return_c, esp_depth_m}"]
    near = lambda a, b, tol: isinstance(a, (int, float)) and abs(float(a) - float(b)) <= tol
    row = next((p for p in front if c.get("n") == p["n"] and near(c.get("t_return_c"), p["t_return_c"], 0.01)
                and near(c.get("esp_depth_m"), p["esp_depth_m"], 1.0)), None)
    if row is None:
        return [f"(j) chosen_design {c} is not a row of the Pareto front {[(p['n'], p['t_return_c'], p['esp_depth_m']) for p in front]}"]
    p = []
    if (run_json.get("n_doublets"), run_json.get("t_return_c")) != (row["n"], row["t_return_c"]):
        p.append(f"(j) chosen_design is {row['n']} doublets at {row['t_return_c']} C but the answer says "
                 f"{run_json.get('n_doublets')} doublets at {run_json.get('t_return_c')} C")
    text = TAG.sub("", str(tr or ""))
    for k, unit in (("lcoh_EUR_MWh", "EUR/MWh"), ("co2_total_kt", "kt")):
        if not any(close(x, row[k]) for x in NUM.findall(text)):
            p.append(f"(j) trade_off does not quote the chosen row's {row[k]} {unit}: {tr}")
    if not isinstance(tr, str) or not TAG.search(tr):
        p.append(f"(j) trade_off needs a [tag]: {tr}")
    if row.get("versus") and (row["versus"] not in str(tr)):
        p.append(f"(j) trade_off does not carry the chosen row's versus phrase '{row['versus']}': {tr}")
    k = "lcoh_EUR_MWh" if opt["priority"] == "lcoh" else "co2_total_kt"
    best = opt["best_on_priority"][k]
    if row[k] > 1.05 * best:
        p.append(f"(j) the brief {'asks for' if stated else 'defaults to'} {opt['priority']} first but the chosen row's {k} {row[k]} "
                 f"is more than 5 % above the front's best {best}")
    return p


def check_alternatives(alts, called):
    """(h) 3 to 6 rejected alternatives of 4 to 40 words, each with a number and a tag, naming layout and tank when priced."""
    if not isinstance(alts, list) or not all(isinstance(x, str) for x in alts):
        return [f"(h) rejected_alternatives must be a list of strings, got {type(alts).__name__}"]
    problems = [] if 3 <= len(alts) <= 6 else [f"(h) {len(alts)} rejected_alternatives, need 3 to 6"]
    for a in alts:
        if not 4 <= len(a.split()) <= 40:
            problems.append(f"(h) {len(a.split())} words, need 4 to 40: {a}")
        if not TAG.search(a):
            problems.append(f"(h) no [tag]: {a}")
        if not NUM.search(TAG.sub("", a)):
            problems.append(f"(h) no number in: {a}")
    text = " ".join(alts).lower()
    if "layout_compare" in called and not re.search(r"layout|boiler[- ]lift", text):
        problems.append("(h) layout_compare ran but no rejected alternative names the boiler-lift layout")
    if "storage_point" in called and not re.search(r"tank|storage", text):
        problems.append("(h) storage_point ran but no rejected alternative names the storage tank")
    return problems


def newest_run():
    path = max([*log.RUNS.glob("2*_plan_*.md"), *log.RUNS.glob("2*_free_*.md")])
    data = json.loads(path.read_text().split("```json\n")[-1].split("\n```")[0])
    return path, data


if __name__ == "__main__":
    path, d = newest_run() if len(sys.argv) < 2 else (sys.argv[1], None)
    if d is None:
        d = json.loads(open(path).read().split("```json\n")[-1].split("\n```")[0])
    for label, ans in (("first answer", d["answer"]), ("after re-prompt", d.get("answer_2"))):
        if ans:
            p = check(ans, d["transcript"], d["tool_results"], d["brief"])
            print(f"{path}\n{label}: {len(p)} problems" + "".join(f"\n  {x}" for x in p))
