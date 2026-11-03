"""Check a final JSON answer against the tool results the model saw: wording, tags, numbers, consistency with the sweep."""
import json
import re
import sys

import AI01_log as log

WORDS = re.compile(r"\b(optimal|best|lowest|cheapest)\b", re.I)
TAG = re.compile(r"\[(?:[CDLA]|TBC)[^\]]*\]")   # [C], [C, A], [C, 03], [L, research/04], [TBC]
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


def meets_rule(row):
    """No heat unmet, boiler at most 5 % of the heat served, and capacity covers the peak with every doublet on:
    the plan's rule for enough doublets [A]. The boiler allowance is for outage days, not for a plant too small at the peak."""
    return row["unmet_GWh"] < 0.01 and row["boiler_GWh"] <= 0.05 * row.get("served_GWh", 0) and row.get("peak_margin_pct", 0.0) >= 0.0


def close(x, p):
    """x (the model's number, as text) equals p rounded to as many significant digits as x has."""
    n = max(1, len(str(x).replace(".", "").lstrip("0")))
    return float(f"{float(p):.{n}g}") == float(x)


def check(run_json, transcript, tool_results, brief=""):
    """run_json: the parsed answer; transcript: the messages; tool_results: [{"name", "args", "result"}] the model received."""
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
    if not 3 <= n_model <= 12:
        problems.append(f"(f) {n_model} reasoning items, need 3 to 12")
    ph = brief_peak(brief, "heat")
    if ph is not None and not any(float(x) == ph for r in reasoning for x in NUM.findall(TAG.sub("", r))):
        problems.append(f"(f) the brief's peak heat {ph:g} MW appears in no reasoning item")
    pool = [float(x) for r in tool_results for x in NUM.findall(json.dumps(r["result"]))]
    in_brief = [float(x) for x in NUM.findall(brief)]
    for r in reasoning:
        for x in NUM.findall(TAG.sub("", r)):
            if (float(x) < 13 and "." not in x) or any(close(x, b) for b in in_brief):
                continue
            if not any(close(x, p) for p in pool):
                problems.append(f"(c) {x} not in any tool result of this run: {r}")
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
    for m, sm in sweeps.items():
        best = sm["by_return_C"][str(sm["best_return_c"])]
        if n is not None and m < n and meets_rule(best):
            problems.append(f"(d) {m} doublets already meet the heat with boiler at most 5 % of it at {sm['best_return_c']} C; "
                            f"{n} is more than needed")
    for r in tool_results:
        if r["name"] == "checks" and r["args"].get("n_doublets") == n and r["args"].get("t_return_c") == t:
            if run_json.get("checks_passed") != f"{r['result']['n_pass']}/{r['result'].get('n_rows', 13)}":
                problems.append(f"(d) checks_passed={run_json.get('checks_passed')} but checks gives {r['result']['n_pass']}/{r['result'].get('n_rows', 13)}")
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
    parsed = zip((brief_peak(brief, "heat"), brief_peak(brief, "cool"), *brief_site(brief)), ("MW", "MW", "m", "C", "C"))
    for x, unit in parsed:
        if x is not None and x not in args:
            problems.append(f"(e) brief value {x:g} {unit} never reached a tool")
    if any(r["name"] == "site_inputs" and not r["result"].get("supported", False) for r in tool_results):   # an error counts as unsupported
        if not re.search(r"not supported|cannot be trusted", " ".join(reasoning), re.I):
            problems.append("(g) site_inputs says the setpoints are not supported, but the reasoning does not say "
                            "'not supported' or 'cannot be trusted'")
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
