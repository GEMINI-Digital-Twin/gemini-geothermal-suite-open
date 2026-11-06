"""GeoBalance design agent.

An LLM agent that designs an integrated deep-geothermal heating + cooling
system. It reasons about the demand, runs GEMINI and the surface models as
tools, reads violations and warnings, improves the design, and explains
its final recommendation. Every session is logged to transcripts/ with
token usage; evaluated designs are kept in memory.json between sessions.

LLM providers (OpenAI-compatible API, set the key as an environment variable):
  groq   -> open-weight model openai/gpt-oss-120b   (GROQ_API_KEY)  [default]
  openai -> gpt-4.1-mini                             (OPENAI_API_KEY)
  mock   -> scripted offline run for testing, no API key needed

Usage:
  python agent.py "Design a system for the GEMINI challenge"
  python agent.py --provider openai --session test1 "..."
  python agent.py --interactive
"""
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import annual_sim
import gemini_wrapper as gw
import tools

HERE = Path(__file__).resolve().parent
MEMORY_FILE = HERE / "memory.json"
TRANSCRIPTS = HERE / "transcripts"
MAX_STEPS = 30
ACCEPT_BOILER_PCT = 5.0
MAX_REVIEWS = 3

PROVIDERS = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key": "GROQ_API_KEY",
             "model": "openai/gpt-oss-120b"},
    "openai": {"base_url": None, "key": "OPENAI_API_KEY", "model": "gpt-4.1-mini"},
}

SYSTEM_PROMPT = """You are GeoBalance, an engineering agent that designs integrated deep-geothermal
heating and cooling systems for an urban district, using the GEMINI digital twin.

Rules:
1. Only report numbers that come from tool results. Never invent or estimate a result
   yourself. If a tool returns a warning or violation, mention it and act on it.
2. Start by calling get_challenge_inputs. Check that you have every input you need.
   If the user's request is missing a required input or contradicts the fixed inputs,
   call ask_user once; if there is no answer, state the assumption you use.
3. A valid design: 1-3 doublets, 50-300 m3/h per doublet, brine cooled max 40 C,
   production = injection, 330 days geothermal availability per doublet (35-day outage),
   heating supplied at 100 C and cooling at 20 C on all 365 days, no violations.
4. Workflow: size the doublet with GEMINI at the given depth (2,500 m) AND a deeper option
   (e.g. 3,400 m) -> evaluate full-year designs -> read every violation and warning -> change
   one variable at a time to fix them -> evaluate at least 4 meaningfully different designs,
   covering: shallow vs deep wells, 2 vs 3 doublets, heat pump vs direct heating, and gas
   engine vs flare/reinject -> compare_designs -> recommend one.
   Acceptance: a design is only acceptable with zero violations AND a backup boiler share
   below 5%. If no design meets this, say so and recommend the closest one.
   Leave maintenance_start_day empty (the simulator staggers outages in spring) unless you
   have a reason to change it; never put two doublets offline at the same time.
5. Cross-check at least one GEMINI doublet result with cross_check_hand_calc and report
   the difference and its cause (from the tool's note), without guessing other causes.
6. Final answer: a short table of the compared designs (backup boiler share, grid
   electricity, CO2, reduction vs. gas boiler reference), the recommended design, and
   one line of reasoning for each major engineering decision (depth, number of
   doublets, heat pump or not, cooling technology, gas handling, maintenance timing).
   Every number and claim must match a tool result; warnings that describe a model or
   solver error must be reported as such, not as physical results.
7. If the user asks something unrelated to geothermal system design, say briefly that
   it is outside your scope and offer what you can do instead. Do not call tools for it.
8. Be concise: keep tool calls purposeful; do not re-run identical evaluations
   (check the memory summary first)."""

DESIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "short unique name"},
        "depth_m": {"type": "number", "description": "reservoir depth TVD, e.g. 2500 (given) or deeper"},
        "n_doublets": {"type": "integer", "enum": [1, 2, 3]},
        "target_flow_m3h": {"type": "number", "description": "per doublet, 50-300"},
        "network_return_c": {"type": "number", "description": "district heating return, default 50"},
        "heating_mode": {"type": "string", "enum": ["preheat_hp", "direct", "hp_only"],
                         "description": "preheat_hp: direct heat exchanger + heat pump top-up; "
                                        "direct: heat exchanger only (backup boiler tops up); "
                                        "hp_only: all heat through a heat pump"},
        "absorption_chiller": {"type": "boolean"},
        "gas_use": {"type": "string", "enum": ["engine", "flare", "reinject"]},
        "storage_mwh": {"type": "number", "description": "hot-water storage size, 0 = none"},
        "maintenance_start_day": {"type": "array", "items": {"type": "integer"},
                                  "description": "one 35-day outage start day (0-330) per doublet"},
    },
    "required": ["name"],   # everything else has a default (see annual_sim.DEFAULT_DESIGN)
}

TOOLS = [
    {"type": "function", "function": {
        "name": "get_challenge_inputs",
        "description": "Fixed challenge inputs, constraints and a summary of the 2027 demand profiles.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "size_doublet",
        "description": "GEMINI: choose ESP/tubing for one doublet at a depth and target flow. "
                       "Returns achievable flow, brine temperature at the plant, pump power, warnings.",
        "parameters": {"type": "object", "properties": {
            "depth_m": {"type": "number"}, "target_flow_m3h": {"type": "number"}},
            "required": ["depth_m", "target_flow_m3h"]}}},
    {"type": "function", "function": {
        "name": "evaluate_design",
        "description": "Run the full-year (365 daily steps) simulation of a design using GEMINI wells "
                       "and surface models. Returns energy balance, CO2, equipment sizes, violations, warnings.",
        "parameters": {"type": "object", "properties": {"design": DESIGN_SCHEMA}, "required": ["design"]}}},
    {"type": "function", "function": {
        "name": "cross_check_hand_calc",
        "description": "Compare a GEMINI doublet run with independent hand calculations "
                       "(doublet pressure, pump power, heat).",
        "parameters": {"type": "object", "properties": {
            "depth_m": {"type": "number"}, "target_flow_m3h": {"type": "number"}},
            "required": ["depth_m", "target_flow_m3h"]}}},
    {"type": "function", "function": {
        "name": "compare_designs",
        "description": "Table of all designs evaluated so far (from memory).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "ask_user",
        "description": "Ask the user one clarifying question when a required input is missing or contradictory.",
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}},
                       "required": ["question"]}}},
]


# ---------------- memory ----------------
def load_memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return {"designs": {}}


def save_memory(mem):
    MEMORY_FILE.write_text(json.dumps(mem, indent=1))


def memory_summary(mem):
    if not mem["designs"]:
        return "No designs evaluated yet."
    lines = [f"- {k}: boiler {v['boiler_pct']}%, grid {v['grid_gwh']} GWh, CO2 {v['co2_t']} t, "
             f"violations {v['n_violations']}" for k, v in mem["designs"].items()]
    return "Designs already evaluated (memory):\n" + "\n".join(lines)


# ---------------- tool implementations ----------------
class ToolBox:
    def __init__(self, interactive=False):
        self.interactive = interactive
        self.mem = load_memory()
        self.session_designs = []      # names evaluated in this session (reviewer scope)

    def get_challenge_inputs(self):
        return {
            "reservoir": {"depth_m": 2500, "thickness_m": 100, "gradient_c_per_km": 30,
                          "surface_temp_c": 12, "pressure_bar": 250, "permeability_md": 200,
                          "deeper_wells": "allowed; hydrostatic pressure, temperature from gradient"},
            "brine": {"density_kg_m3": 1030, "viscosity_mpa_s": 0.4, "glr_nm3_m3": 0.8,
                      "gas": "80% CH4 / 20% CO2"},
            "constraints": {"doublets": "1-3", "flow_m3h_per_doublet": [50, 300], "max_brine_cooling_c": 40,
                            "pump_efficiency": 0.7, "availability_days_per_doublet": 330,
                            "supply_heating_c": 100, "supply_cooling_c": 20,
                            "grid_co2_kg_per_kwh": 0.3},
            "demand": annual_sim.demand_summary(),
            "model_notes": ["Network return temperature is a design choice (default 50 C).",
                            "GEMINI has no cooling model; absorption and electric chiller models are ours.",
                            "Backup boiler and electric chiller are sized by the simulation."],
        }

    def size_doublet(self, depth_m, target_flow_m3h):
        return gw.size_doublet(float(depth_m), float(target_flow_m3h))

    def evaluate_design(self, design=None, **flat):
        design = design or flat          # accept flat arguments too (some LLMs send them unwrapped)
        r = annual_sim.evaluate_design(design)
        name = design.get("name", f"design_{len(self.mem['designs']) + 1}")
        self.session_designs.append(name)
        if "heat_gwh" in r:
            self.mem["designs"][name] = {
                "design": r["design"],
                "boiler_pct": round(r["heat_gwh"]["backup_boiler"] / r["heat_gwh"]["demand"] * 100, 1),
                "grid_gwh": r["electricity_gwh"]["from_grid"], "co2_t": r["co2_t"]["total"],
                "co2_reduction_pct": r["co2_t"]["reduction_pct"],
                "renewable_heat_pct": r["renewable_heat_share_pct"],
                "equipment_mw": r["equipment_mw"], "n_violations": len(r["violations"]),
                "violations": r["violations"], "warnings": r["warnings"]}
            save_memory(self.mem)
        r = dict(r)
        r.pop("design", None)        # keep tool output short (token saving)
        if "heat_gwh" in r:
            boiler_pct = r["heat_gwh"]["backup_boiler"] / r["heat_gwh"]["demand"] * 100
            ok = not r["violations"] and boiler_pct < ACCEPT_BOILER_PCT
            r["acceptable"] = ok
            r["acceptance_note"] = ("ACCEPTABLE: no violations and backup boiler below 5%" if ok else
                                    f"NOT ACCEPTABLE: {len(r['violations'])} violation(s), backup boiler "
                                    f"{boiler_pct:.1f}% (limit 5%). Fix the violations/warnings and re-evaluate.")
        return r

    def cross_check_hand_calc(self, depth_m, target_flow_m3h):
        g = gw.size_doublet(float(depth_m), float(target_flow_m3h))
        if "error" in g:
            return g
        q = g["flow_m3h"]
        p_res = gw.reservoir_pressure_bar(float(depth_m))
        hand = tools.doublet_pressure_and_pump(flow_m3h=q, p_res_bar=p_res, depth_m=depth_m)
        dt = g["brine_temp_at_plant_c"] - (g["reservoir_temperature_c"] - 40)
        return {
            "flow_m3h": q,
            "producer_drawdown_bar": {"gemini_pi_model": round(q / g["productivity_index_m3h_bar"], 1),
                                      "hand_doublet_formula": round(hand["total_dp_bar"] / 2, 1),
                                      "note": "GEMINI: flow / productivity index (radial inflow, "
                                              f"{g['productivity_index_m3h_bar']} m3/h/bar). Hand: two-well doublet "
                                              "formula with 1,500 m well spacing, half of the total pressure difference. "
                                              "Different geometry assumptions cause the difference."},
            "pump_power_mw": {"gemini_esp_plus_injector": round(g["esp_power_mw"] + g["injector_pump_mw"], 3),
                              "hand_calc_70pct": hand["pump_power_mw"],
                              "note": "GEMINI: ESP power from its pump curve at the solved operating point plus the "
                                      "injector pump. Hand: pressure x flow / 70% efficiency with assumed 10 bar "
                                      "wellhead and 5 bar friction per well."},
            "heat_per_doublet_mw": {"gemini_flow_and_plant_temp": round(tools._mw(q, dt), 2),
                                    "hand_calc_same_flow_40K": round(tools.doublet_heat_mw(q, 40)["heat_mw"], 2),
                                    "note": f"difference = wellbore/separator/filter losses: brine reaches the "
                                            f"plant at {g['brine_temp_at_plant_c']} C, so only {dt:.0f} K of the "
                                            f"40 K cooling cap is usable"},
            "gas_engine_el_mw": {"gemini_chp": g["gemini_chp_power_el_mw"],
                                 "hand_gas_engine": round(tools.gas_engine(q)["electricity_mw"], 3),
                                 "note": "GEMINI CHP converts 80% of the fuel energy and 1/3 of that to electricity "
                                         "(26.7% electric efficiency). Hand calc: 40% electric efficiency (gas engine)."},
            "warnings": g["warnings"] + hand["warnings"],
        }

    def compare_designs(self):
        return {k: {kk: v[kk] for kk in ("boiler_pct", "grid_gwh", "co2_t", "co2_reduction_pct",
                                         "renewable_heat_pct", "n_violations")}
                for k, v in self.mem["designs"].items()} or {"note": "no designs yet"}

    def ask_user(self, question):
        if self.interactive:
            return {"answer": input(f"\n[agent asks] {question}\n> ")}
        return {"answer": None, "note": "No user available (batch run). State your assumption and continue."}

    def call(self, name, args):
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_"):
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**args)
        except Exception as e:  # report errors to the agent so it can fix its call
            return {"error": f"{type(e).__name__}: {e}"}


# ---------------- LLM client ----------------
def make_client(provider):
    if provider == "mock":
        return MockClient()
    from openai import OpenAI
    cfg = PROVIDERS[provider]
    key = os.environ.get(cfg["key"])
    if not key:
        raise SystemExit(f"Set {cfg['key']} first, e.g.  export {cfg['key']}=...")
    return OpenAI(api_key=key, base_url=cfg["base_url"]) if cfg["base_url"] else OpenAI(api_key=key)


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class MockClient:
    """Offline scripted run to test the plumbing (no LLM)."""
    def __init__(self):
        self.step = 0
        self.script = [
            ("get_challenge_inputs", {}),
            ("size_doublet", {"depth_m": 2500, "target_flow_m3h": 250}),
            ("evaluate_design", {"design": {"name": "mock_shallow_hp", "depth_m": 2500, "n_doublets": 3,
                                            "heating_mode": "preheat_hp", "gas_use": "engine"}}),
            ("evaluate_design", {"design": {"name": "mock_deep_direct", "depth_m": 3400, "n_doublets": 3,
                                            "heating_mode": "direct", "gas_use": "engine"}}),
            ("cross_check_hand_calc", {"depth_m": 2500, "target_flow_m3h": 250}),
            ("compare_designs", {}),
        ]
        self.chat = _Obj(completions=_Obj(create=self.create))

    def create(self, **kw):
        usage = _Obj(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        if self.step < len(self.script):
            name, args = self.script[self.step]
            self.step += 1
            tc = _Obj(id=f"call_{self.step}", type="function",
                      function=_Obj(name=name, arguments=json.dumps(args)))
            msg = _Obj(content=None, tool_calls=[tc], role="assistant")
        else:
            msg = _Obj(content="[mock] Final recommendation would be written here.", tool_calls=None,
                       role="assistant")
        return _Obj(choices=[_Obj(message=msg)], usage=usage)


# ---------------- context compaction (token saving) ----------------
KEEP_KEYS = ("acceptable", "acceptance_note", "violations", "co2_t", "heat_gwh", "flow_m3h",
             "brine_temp_at_plant_c", "esp_power_mw", "sizing_note", "error")
TOKEN_BUDGET = 4500          # messages only; + ~1,100 tool schema tokens + reply must stay under Groq free tier 8,000 TPM


def est_tokens(messages):
    return sum(len(json.dumps(m, default=str)) for m in messages) // 4


def compact(messages, keep_last=3):
    """Shorten all but the last `keep_last` tool results to their key fields.
    Full results stay in memory.json (compare_designs)."""
    tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    for i in tool_idx[:-keep_last] if keep_last else tool_idx:
        c = messages[i]["content"]
        if c.startswith("[trimmed]"):
            continue
        try:
            data = json.loads(c)
            short = {k: data[k] for k in KEEP_KEYS if isinstance(data, dict) and k in data}
            if "co2_t" in short and isinstance(short["co2_t"], dict):
                short["co2_t"] = short["co2_t"].get("total")
            if "heat_gwh" in short and isinstance(short["heat_gwh"], dict):
                short["boiler_gwh"] = short.pop("heat_gwh").get("backup_boiler")
            text = json.dumps(short)
        except (json.JSONDecodeError, TypeError):
            text = c[:200]
        messages[i]["content"] = "[trimmed] " + text[:400]


def fit_budget(messages):
    for keep in (3, 1, 0):
        if est_tokens(messages) <= TOKEN_BUDGET:
            return
        compact(messages, keep)


# ---------------- reviewer (critic) ----------------
def review(mem, final_text, session_designs, full_task):
    """Check the agent's work before accepting its final answer.
    Only designs evaluated in this session count. No design work this session
    (e.g. an off-topic question) -> nothing to review. Coverage rules apply only
    to the open design task, not when the user set their own constraints.
    Returns a list of problems (empty = accept)."""
    if not session_designs:
        return []
    designs = {k: v for k, v in mem["designs"].items() if k in set(session_designs)}
    problems = []
    if full_task:
        ds = [v["design"] for v in designs.values()]
        if len(designs) < 4:
            problems.append(f"Only {len(designs)} designs evaluated; evaluate at least 4.")
        if not any(float(d.get("depth_m", 2500)) > 2500 for d in ds):
            problems.append("No deeper-well design (> 2,500 m) evaluated.")
        if not any(int(d.get("n_doublets", 2)) == 3 for d in ds):
            problems.append("No 3-doublet design evaluated.")
        if not any(d.get("heating_mode") == "direct" for d in ds):
            problems.append("No direct-heating design evaluated.")
    ok = [k for k, v in designs.items() if v["n_violations"] == 0 and v["boiler_pct"] < ACCEPT_BOILER_PCT]
    if not ok:
        problems.append("No design is acceptable yet (zero violations and backup boiler < 5%). "
                        "Read the warnings of your best design and change one variable to fix them, "
                        "or explain clearly why the user's constraints make it impossible.")
    else:
        best = min(ok, key=lambda k: designs[k]["co2_t"])
        if best not in (final_text or ""):
            problems.append(f"Acceptable designs: {', '.join(ok)}. The lowest-CO2 acceptable design is "
                            f"'{best}'. Recommend an acceptable design (use its exact name) or explain "
                            "with tool numbers why another acceptable one is better.")
    return problems


# ---------------- agent loop ----------------
DEFAULT_PROMPT = ("Design the integrated geothermal heating and cooling system for the GEMINI challenge "
                  "and recommend the best option.")


def run(prompt, provider="groq", model=None, session=None, interactive=False):
    client = make_client(provider)
    model = model or PROVIDERS.get(provider, {}).get("model", "mock")
    box = ToolBox(interactive)
    session = session or datetime.now().strftime("session_%Y%m%d_%H%M%S")
    TRANSCRIPTS.mkdir(exist_ok=True)
    log = [f"# GeoBalance agent session `{session}`", "",
           f"- Provider: {provider}  \n- Model: {model}  \n- Started: {datetime.now():%Y-%m-%d %H:%M}", "",
           "## User", "", prompt, ""]
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + memory_summary(box.mem)},
                {"role": "user", "content": prompt}]
    tok = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
    final = None
    t0 = time.time()
    try:
        final = _loop(client, model, box, messages, log, tok, prompt.strip() == DEFAULT_PROMPT)
    except Exception as e:
        log += ["## Run stopped by an error", "", f"`{type(e).__name__}: {e}`", ""]
        final = None
        print(f"\nERROR: {type(e).__name__}: {e}")
    finally:
        _write_log(session, log, final, tok, t0)
    return final, tok


def _loop(client, model, box, messages, log, tok, full_task=True):
    final = None
    reviews = 0
    for step in range(1, MAX_STEPS + 1):
        fit_budget(messages)
        resp = None
        for attempt in range(6):
            try:
                resp = client.chat.completions.create(model=model, messages=messages, tools=TOOLS,
                                                      tool_choice="auto", temperature=0.2)
                break
            except Exception as e:   # rate limit (429) or request too large (413): trim, wait, retry
                code = getattr(e, "status_code", None)
                if code == 400 and "validation" in str(e).lower() and attempt < 5:
                    # The provider rejected a malformed tool call: tell the agent and let it retry.
                    err = str(e)[:400]
                    messages.append({"role": "user", "content": "SYSTEM: your last tool call was rejected "
                                     f"by the API: {err}. Fix the arguments and call the tool again."})
                    print(f"[step {step}] tool call rejected by API, asking agent to fix it")
                    log += [f"_Tool call rejected by API (400), agent asked to fix it: {err}_", ""]
                    continue
                if code not in (413, 429) or attempt == 5:
                    raise
                compact(messages, keep_last=1 if code == 413 else 3)
                wait = 20 if code == 413 else 30
                print(f"[step {step}] rate limit ({code}), waiting {wait}s and retrying...")
                log += [f"_Rate limit {code}: context trimmed, retried after {wait}s_", ""]
                time.sleep(wait)
        u = resp.usage
        tok["prompt"] += u.prompt_tokens or 0
        tok["completion"] += u.completion_tokens or 0
        tok["total"] += u.total_tokens or 0
        tok["calls"] += 1
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [{"id": tc.id, "type": "function",
                                             "function": {"name": tc.function.name,
                                                          "arguments": tc.function.arguments}}
                                            for tc in msg.tool_calls]})
            if msg.content:
                log += [f"### Step {step}: agent reasoning", "", msg.content, ""]
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError as e:
                    args, result = {}, {"error": f"invalid JSON arguments: {e}"}
                else:
                    result = box.call(tc.function.name, args)
                out = json.dumps(result, default=float)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
                log += [f"### Step {step}: tool `{tc.function.name}`", "",
                        "```json", json.dumps(args, indent=1), "```", "", "Result:", "",
                        "```json", out[:3000] + (" ...(truncated in log)" if len(out) > 3000 else ""), "```",
                        f"_tokens so far: {tok['total']}_", ""]
                print(f"[step {step}] {tc.function.name} -> {len(out)} chars")
        else:
            problems = review(box.mem, msg.content, box.session_designs, full_task)
            if problems and reviews < MAX_REVIEWS:
                reviews += 1
                note = "REVIEWER: your answer is not accepted yet:\n- " + "\n- ".join(problems)
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append({"role": "user", "content": note})
                log += [f"### Step {step}: draft answer (rejected by reviewer)", "", msg.content or "", "",
                        f"### Step {step}: reviewer feedback {reviews}", "", note, ""]
                print(f"[step {step}] reviewer rejected draft ({len(problems)} problem(s))")
                continue
            final = msg.content
            if problems:
                final += "\n\n_Reviewer note: still open after 3 reviews: " + "; ".join(problems) + "_"
            break
    return final


def _write_log(session, log, final, tok, t0):
    log += ["## Final answer", "", final or "(no final answer: step limit reached)", "",
            "## Token usage", "",
            f"| LLM calls | prompt | completion | total | time (s) |",
            f"|---|---|---|---|---|",
            f"| {tok['calls']} | {tok['prompt']} | {tok['completion']} | {tok['total']} | {time.time() - t0:.0f} |", ""]
    path = TRANSCRIPTS / f"{session}.md"
    path.write_text("\n".join(log), encoding="utf-8")
    print("\n" + (final or "(no final answer)"))
    print(f"\nTokens: {tok}  |  transcript: {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
    ap.add_argument("--provider", default="groq", choices=["groq", "openai", "mock"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--interactive", action="store_true", help="let the agent ask you questions")
    ap.add_argument("--reset-memory", action="store_true")
    a = ap.parse_args()
    if a.reset_memory and MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
    run(a.prompt, a.provider, a.model, a.session, a.interactive)
