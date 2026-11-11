"""The repair loop of the design agent: when a check fails, the model picks one move from a menu (or stops); the code applies it.

The menu holds one move per failing check row (MOVES): the input it changes, the code's suggested value and the allowed range.
The model replies with one JSON object {"move", "value", "why"}. The code checks the row and the value, applies the move,
re-runs checks and records who moved (model or code) and why, word for word. Up to MAX_MOVES moves per brief; after two
replies that are not a valid move the code takes the suggested move itself, so a weak model never leaves a repair undone.
"""
import json
import math
import pathlib
import re

import AI01_log as log
import AI02_tools as tools
from geo import lifetime
from geo.common import Q_MAX_M3H
from geo.well import ESP_DEPTH_M

MAX_MOVES = 3
MISSES = 2   # replies that are not a valid move before the code moves by itself
PROMPT = pathlib.Path(__file__).parent / "prompts" / "move.md"
# repair move per failing check row: (input it changes, unit, how the code suggests the value)
MOVES = {"free gas at ESP intake": ("esp_depth_m", "m", "+300 m, cap 1250 m"),
         "SodM injection pressure": ("n_doublets", "doublets", "+1, cap the brief's maximum"),
         "capacity covers the peak": ("n_doublets", "doublets", "+1, cap the brief's maximum"),
         "one doublet out on the coldest day": ("n_doublets", "doublets", "+1, cap the brief's maximum"),
         "thermal breakthrough": ("spacing_m", "m", "spacing for 30 yr at 300 m3/h, rounded up to 50 m"),
         "doublet interference": ("doublet_spacing_m", "m", "x 1.5, cap 5000 m")}
START = {"esp_depth_m": ESP_DEPTH_M, "spacing_m": lifetime.SPACING_M}   # tool defaults when the brief gives no value
STEP = {"esp_depth_m": 50.0, "n_doublets": 1, "spacing_m": 50.0, "doublet_spacing_m": 50.0}   # values are rounded to these
LIFE_KEYS = ("spacing_m", "doublet_spacing_m")   # inputs of lifetime_point, not of checks
FIRST_NUM = re.compile(r"-?\d+(?:\.\d+)?\s*(?:bar|yr|GWh|MW|m3/h|K|m)\b")


def cap(key, max_n):
    return {"esp_depth_m": 1250.0, "n_doublets": max_n, "spacing_m": 3000.0, "doublet_spacing_m": 5000.0}[key]


def suggested(key, now, max_n):
    """The code's own value for key after one move from now (the old repair rule)."""
    if key == "esp_depth_m":
        return min(now + 300.0, cap(key, max_n))
    if key == "n_doublets":
        return min(now + 1, max_n)
    if key == "spacing_m":
        return min(max(now, 50.0 * math.ceil(lifetime.spacing_for_yr(30, Q_MAX_M3H) / 50.0)), cap(key, max_n))
    return min(now * 1.5, cap(key, max_n))


def failing(checks_result):
    """[(row name without number and tag, value text, limit text)] for the FAIL rows of a checks result."""
    rows = []
    for k, v in checks_result.items():
        if isinstance(v, str) and "-> FAIL" in v:
            value, rest = v.split(" (limit ", 1)
            rows.append((re.sub(r"^\d+ |\s*\[[^\]]*\]$", "", k), value, rest.rsplit(") -> ", 1)[0]))
    return rows


def short(value, limit):
    """'45.2 bar against limit 62.5 bar' from a check row's value and limit text (the full row stays in the checks result)."""
    v, lim = FIRST_NUM.search(value), FIRST_NUM.search(limit)
    return f"{v.group(0)} against limit {lim.group(0)}" if v and lim else f"{value} (limit {limit})"


def menu(design, life, checks_result, max_n):
    """One option per failing row that has a move and is not at its cap: row, key, unit, how, now, new, cap, reason."""
    options = []
    for row, value, limit in failing(checks_result):
        if row not in MOVES:
            continue
        key, unit, how = MOVES[row]
        where = life if key in LIFE_KEYS else design
        now = where.get(key, START.get(key, lifetime.SPACING_M))
        new = suggested(key, now, max_n)
        if new != now:
            options.append({"row": row, "key": key, "unit": unit, "how": how, "now": now, "new": new, "cap": cap(key, max_n),
                            "reason": f"{row}: {short(value, limit)}"})
    return options


def message(brief, design, checks_result, options):
    """The user message of one move exchange: the design, the failing rows and the menu."""
    esp = design.get("esp_depth_m", ESP_DEPTH_M)
    lines = [f"Brief: {brief}", f"Design now: {design['n_doublets']} doublets at {design['t_return_c']:g} C return, ESP at {esp:g} m, "
             f"reservoir {design.get('depth_m', 2500):g} m. Checks: {checks_result.get('summary', '')}.", "Failing:"]
    lines += [f"- {row}: {value} (limit {limit}) [C]" for row, value, limit in failing(checks_result)]
    lines.append("Moves you may make, one per reply, with the code's suggested value and the allowed range:")
    for o in options:
        lo = o["now"] + STEP[o["key"]]
        lines.append(f'- "{o["row"]}": {o["key"]} {o["now"]:g} -> {o["new"]:g} {o["unit"]} ({o["how"]}); '
                     f'allowed {lo:g} to {o["cap"]:g} {o["unit"]}')
    lines.append('- "stop": keep the design as it is and let the answer say which check still fails (only when no move above can help).')
    return "\n".join(lines)


def parse(text, options):
    """(option, value, why) from the model's reply; option is 'stop' for a stop and None when the reply is not a valid move."""
    try:
        j = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError as e:
        return None, f"not a JSON object ({e})", text[:200]
    why = str(j.get("why", ""))
    move = str(j.get("move", "")).strip().strip('"')
    if move == "stop":
        return "stop", None, why
    o = next((o for o in options if o["row"] == move or o["key"] == move), None)
    if o is None:
        return None, f"'{move}' is not a move in the list", why
    value = j.get("value")
    if value is None:
        return o, o["new"], why
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None, f"value {value!r} is not a number", why
    step = STEP[o["key"]]
    v = round(v / step) * step
    if not o["now"] < v <= o["cap"]:
        return None, f"value {v:g} is outside the allowed {o['now'] + step:g} to {o['cap']:g} {o['unit']}", why
    return o, int(v) if o["key"] == "n_doublets" else v, why


def apply(o, new, design, life, out, by, why):
    """Apply one move in place, re-run checks, record the checks call in out and return the trace step."""
    where = life if o["key"] in LIFE_KEYS else design
    where[o["key"]] = new
    res = tools.call("checks", dict(design))
    out.append({"name": "checks", "args": dict(design), "result": res})
    esp = design.get("esp_depth_m", ESP_DEPTH_M)
    return {"candidate": f"{design['n_doublets']} doublets at {design['t_return_c']:g} C, ESP {esp:g} m"
            + "".join(f", {k} {v:g} m" for k, v in life.items()),
            "n_doublets": design["n_doublets"], "t_return_c": design["t_return_c"],
            "verdict": "repaired" if res.get("n_fail", 1) == 0 else "still failing", "reason": o["reason"],
            "move": f"{o['key']} {o['now']:g} -> {new:g} {o['unit']} [A, MOVES]", "key": o["key"], "from": o["now"], "to": new,
            "by": by, "why": why, "checks_after": f"{res.get('n_pass')}/{res.get('n_rows')}", "tag": "[C]"}


def note(design, chk, verdict, reason, why):
    """A trace step for a reply that moved nothing (a stop or an invalid reply); checks_after is the checks result it left."""
    return {"candidate": verdict, "n_doublets": design["n_doublets"], "t_return_c": design["t_return_c"], "verdict": verdict,
            "reason": reason, "by": "model", "why": why, "checks_after": f"{chk.get('n_pass')}/{chk.get('n_rows')}", "tag": "[C]"}


def loop(brief, design, life, out, max_n, chat=log.chat, records=None, exchanges=None):
    """Up to MAX_MOVES moves chosen by the model (or by the code after MISSES bad replies); design and life change in place.

    chat(messages) -> (message, record) is AI01_log.chat unless a test injects its own; records and exchanges collect the
    model calls and the user/assistant messages so the run file shows them.
    """
    steps, misses, system = [], 0, PROMPT.read_text().rstrip("\n")
    records, exchanges = [] if records is None else records, [] if exchanges is None else exchanges
    while len([s for s in steps if s.get("move")]) < MAX_MOVES:
        chk = next(r["result"] for r in reversed(out) if r["name"] == "checks")
        options = menu(design, life, chk, max_n)
        if not options:
            break
        if misses >= MISSES:   # the code takes the suggested move for the first failing row
            o = options[0]
            steps.append(apply(o, o["new"], design, life, out, "code", f"{MISSES} replies were not a valid move; the code moved {o['key']}"))
            continue
        user = message(brief, design, chk, options)
        msg, rec = chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        records.append(rec)
        exchanges += [{"role": "user", "content": user}, {"role": "assistant", "content": msg["content"]}]
        pick, value, why = parse(msg["content"], options)
        if pick == "stop":
            steps.append(note(design, chk, "stopped", options[0]["reason"], why))
            break
        if pick is None:
            misses += 1
            steps.append(note(design, chk, "invalid reply", value, why or msg["content"][:200]))
            continue
        steps.append(apply(pick, value, design, life, out, "model", why))
    return steps
