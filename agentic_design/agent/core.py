"""The agent loop: LLM decides, tools compute, guards check, memory remembers.

    user -> LLM -> (tool call -> argument + provenance check -> tool -> result)* -> answer
         -> claim check (numbers must come from tools/user) -> user

Every step is recorded so a session can be exported as a transcript (the
evidence appendix the organisers asked for) with token counts.
"""

import json
import re
import time

from agentic_design.agent import guard
from agentic_design.agent.tools import SCHEMA_BY_NAME, SCHEMAS, ToolBox

SYSTEM_PROMPT = """You are a geothermal engineering design agent (SPE GeoEnergyHackathon 2026). Goal: select, size and \
validate a deep-geothermal plant that meets a district's daily heating (100 C) and cooling (20 C) demand in 2027, \
within the challenge constraints, and explain every decision.

Rules:
1. Every number you state must come from a tool result or from the user. Never estimate or invent numbers.
2. If the answer depends on information neither the tools nor the user provided, ask one short clarifying question \
and say what you would assume otherwise. Do not guess. Never attribute a value to the organisers unless \
get_challenge_inputs shows it.
3. If a request is unrelated to geothermal heating/cooling design, say so in one sentence and call no tools.
4. To design: look at inputs and demand, evaluate candidates (sweep_designs is cheapest; it can vary doublets, depth, \
heat_pump_mw, absorption_chiller_mw and electric_chiller_mw), read the violations, change the design and \
re-evaluate until meets_all_constraints is true. Cooling needs absorption and/or electric chillers (peak cooling \
is 10 MW); each doublet is off 35 days a year (staggered), so the remaining equipment must cover those days. \
Associated gas can be burned (surplus flared) or partly reinjected (gas_reinjection). Choose with sweep_designs' \
recommendation_rule (lowest cost with CO2 valued at the EIB carbon value of 450 EUR/t, not the ETS price) and \
quote CO2, cost_EUR_per_MWh and cost_with_EIB_co2_value_EUR_per_MWh. Base the answer on answer_summary when given. Costs are assumptions (ThermoGIS, Eurostat, EIB): say so. Never recommend a design with a P8_OVERSIZED warning. A heat pump COP comes from heat_pump_mean_COP or get_day_operation; \
heat_pump_eta_lorenz is an efficiency factor, not a COP. Explain a change only with causes the tool results \
show; do not invent physical reasons. \
Store final choices with record_decision.
5. Before comparing or explaining designs, call compare_designs with exactly those designs (it refreshes results for \
the current assumptions). Quote each number only for the design it belongs to. Change only what the user asks; keep \
other design parameters at their defaults unless you state why. Never say a design meets all constraints unless its \
meets_all_constraints is true. Do not announce future actions: do them now with a tool, or ask the user.
6. Justify decisions with the specific KPIs, the computed heating_limit_on_peak_day and the constraint results. \
Name the assumptions used. Describe only components listed in a design's 'design' field; anything else is missing \
or proposed and must be called that. Compare a KPI only for the same design: quote a figure only from that design's own row. To explain a \
change, use only the flows listed in its 'cause'.
7. Be concise: short paragraphs or bullets, no repetition.

Memory from earlier sessions:
{memory}"""


class Agent:
    def __init__(self, llm, toolbox: ToolBox, max_steps=12, max_history=40, keep_turns=1):
        self.llm, self.tools = llm, toolbox
        self.max_steps, self.max_history = max_steps, max_history
        # token saving: only the last `keep_turns` finished questions stay in the conversation; everything older
        # reaches the model through the memory summary in the system prompt (designs, assumptions, best design)
        self.keep_turns = keep_turns
        self.best_design = None
        self.cheapest = None
        self._designs_this_turn = set()
        self.messages = [{"role": "system", "content": self._system_prompt()}]
        self.user_texts, self.evidence, self.design_texts = [], guard.new_evidence(), []
        self.user_evidence, self.design_evidence, self.feasible = guard.new_evidence(), {}, set()
        self.design_co2 = {}
        challenge = toolbox.get_challenge_inputs()
        self.not_given = challenge["not_given_by_challenge"]
        # fixed challenge facts (100 C supply, 300 m3/h cap, demand peaks ...) are evidence from the start:
        # quoting them is not hallucination even if the model did not call the tool this session
        self.facts = guard.new_evidence()
        for given in (challenge, toolbox.get_demand_summary()):
            for ev in (self.evidence, self.user_evidence, self.facts):
                guard.add_evidence(ev, given)
        self.esp_warning_seen = False
        dem = toolbox.get_demand_summary()
        self.peak_dates = {"heating": dem["heating"]["peak_date"], "cooling": dem["cooling"]["peak_date"]}
        self.design_fields, self.turn_fields, self.oversized = {}, {}, {}
        self.changes = []  # (before, after) pairs reported by the tools
        self.events = []  # transcript
        self._failed_calls = set()
        self.stats = {"llm_calls": 0, "prompt_tokens": 0, "output_tokens": 0, "tool_calls": 0,
                      "rejected_tool_calls": 0, "claim_corrections": 0, "unverified_answers": 0, "turns": 0}

    # ----------------------------------------------------------------- internals
    def _system_prompt(self):
        mem = self.tools.memory.summary()
        if getattr(self, "best_design", None):
            mem += f"\nCurrent recommended design (last sweep_designs): {self.best_design}"
        return SYSTEM_PROMPT.format(memory=mem)

    def _llm(self):
        out = self.llm.chat(self.messages, SCHEMAS)
        self.stats["llm_calls"] += 1
        self.stats["prompt_tokens"] += out["prompt_tokens"]
        self.stats["output_tokens"] += out["output_tokens"]
        return out

    def _run_tool(self, name, args):
        key = (name, json.dumps(args, sort_keys=True, default=str))
        if key in self._failed_calls:  # demo 8: the same rejected sweep was sent 12 times
            return {"error": "you already made exactly this call in this question and it failed; do not repeat it. "
                             "Change the arguments (see suggested_call if given) or answer with what you have."}, False
        res, ok = self._run_tool_once(name, args)
        if not ok:
            self._failed_calls.add(key)
        return res, ok

    def _run_tool_once(self, name, args):
        if name not in SCHEMA_BY_NAME:
            return {"error": f"unknown tool '{name}'. Available: {sorted(SCHEMA_BY_NAME)}"}, False
        clean, errs = guard.check_arguments(SCHEMA_BY_NAME[name], args)
        errs += guard.check_provenance(name, clean, self.user_texts)
        errs += guard.check_geometry(name, clean, self.user_texts, self.esp_warning_seen)
        if errs:
            return {"error": "rejected before running", "problems": errs}, False
        try:
            res = getattr(self.tools, name)(**clean)
            return res, not (isinstance(res, dict) and "error" in res)
        except Exception as exc:  # tool failure goes back to the model, not to the user as a crash
            return {"error": f"{type(exc).__name__}: {exc}"}, False

    def _collect_design_texts(self, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "design" and isinstance(v, str):
                    self.design_texts.append(v)
                else:
                    self._collect_design_texts(v)
        elif isinstance(obj, list):
            for v in obj:
                self._collect_design_texts(v)

    def _lowest_co2(self, feasible_only=False):
        pool = {n: c for n, c in self.design_co2.items() if not feasible_only or n in self.feasible}
        return min(pool, key=pool.get) if pool else None

    def _collect_design_evidence(self, obj):
        """Numbers per design name, so a figure can be checked against the design it is quoted for."""
        if isinstance(obj, dict):
            if isinstance(obj.get("name"), str) and ("kpi" in obj or "co2_kt_per_year" in obj):
                ev = self.design_evidence.setdefault(obj["name"], guard.new_evidence())
                guard.add_evidence(ev, obj)
                guard.flat_fields(obj, self.design_fields.setdefault(obj["name"], {}))
                guard.flat_fields(obj, self.turn_fields)
                p8 = [w for w in obj.get("warnings", []) if str(w).startswith("P8")]
                if p8:
                    self.oversized[obj["name"]] = "; ".join(p8)
                elif "warnings" in obj:
                    self.oversized.pop(obj["name"], None)
                # component sizes live in the name (HP25 = 25 MW heat pump): they are evidence for that design
                for comp, mw in guard.name_components(obj["name"]).items():
                    guard.add_evidence(ev, mw, "MW")
                    guard.add_evidence(self.evidence, mw, "MW")
                if "design" not in obj:
                    self.design_texts.append(guard.name_text(obj["name"]))
                co2 = obj.get("co2_kt_per_year", (obj.get("kpi") or {}).get("co2_kt_per_year"))
                if co2 is not None:
                    self.design_co2[obj["name"]] = co2
                if obj.get("meets_all_constraints") is True or obj.get("violations") == []:
                    self.feasible.add(obj["name"])
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    self._collect_design_evidence(v)
        elif isinstance(obj, list):
            for v in obj:
                self._collect_design_evidence(v)

    @staticmethod
    def _for_llm(tool, result):
        """What the model reads. A 48-design sweep is ~5k tokens and in demo 11 the model summarised the table
        instead of answering, so it gets the plain-language summary first and only the best rows."""
        if tool != "sweep_designs" or not isinstance(result, dict) or "ranked_by_co2" not in result:
            return result
        rows = result["ranked_by_co2"]
        ok = sorted((r for r in rows if not r["violations"]),
                    key=lambda r: r.get("cost_with_EIB_co2_value_EUR_per_MWh", r["co2_kt_per_year"]))
        named = {result.get("recommended_design")} | {result[k]["name"] for k in (
            "lowest_co2_design_meeting_all_constraints", "lowest_cost_design_meeting_all_constraints")
            if isinstance(result.get(k), dict)}
        # always include the designs the summary names, so their figures are there to quote (demo 12)
        ok = ok[:8] + [r for r in ok[8:] if r["name"] in named]
        bad = [r for r in rows if r["violations"]]
        head = {k: result[k] for k in ("answer_summary", "recommended_design", "recommendation_rule") if k in result}
        rest = {k: v for k, v in result.items() if k not in head and k != "ranked_by_co2"}
        return {**head, **rest,
                "best_designs_meeting_all_constraints": ok,
                "designs_with_violations": [f"{r['name']}: {', '.join(r['violations'])}" for r in bad][:12],
                "evaluated": len(rows)}

    @staticmethod
    def _compact(content):
        """Short form of a tool result for later turns (token saving): the raw result was already used in its
        own turn, and compare_designs re-fetches current numbers whenever they are needed again."""
        try:
            r = json.loads(content)
        except (ValueError, TypeError):
            return content[:300]
        if not isinstance(r, dict):
            return content[:300]
        if "ranked_by_co2" in r:
            keep = {k: r[k] for k in ("lowest_co2_design", "lowest_co2_design_meeting_all_constraints",
                                      "recommended_design", "right_sized_design") if k in r}
            keep["evaluated"] = [{"name": x["name"], "co2_kt_per_year": x["co2_kt_per_year"],
                                  "violations": x["violations"]} for x in r["ranked_by_co2"]]
        elif "kpi" in r:
            keep = {"name": r["name"], "meets_all_constraints": r["meets_all_constraints"],
                    "co2_kt_per_year": r["kpi"]["co2_kt_per_year"], "violations": [v.split(":")[0] for v in r["violations"]],
                    "warnings": [w.split(":")[0] for w in r["warnings"]]}
        elif "designs" in r:
            keep = {"designs": [{"name": d["name"], "co2_kt_per_year": d.get("co2_kt_per_year"),
                                 "meets_all_constraints": d.get("meets_all_constraints")} for d in r["designs"]]}
        else:
            return content if len(content) <= 400 else content[:400] + " ...(truncated; call the tool again for details)"
        keep["_compacted"] = "earlier result, shortened; call a tool for full numbers"
        return json.dumps(keep, separators=(",", ":"))

    def _compress_turn(self, start):
        for m in self.messages[start:]:
            if m["role"] == "tool":
                m["content"] = self._compact(m["content"])

    def _trim(self):
        """Keep the (refreshed) system prompt and the most recent complete turns."""
        self.messages[0] = {"role": "system", "content": self._system_prompt()}
        starts = [i for i, m in enumerate(self.messages)
                  if m["role"] == "user" and i > 0 and not str(m["content"]).startswith("[verifier]")]
        if self.keep_turns is not None and len(starts) > self.keep_turns:
            self.messages = [self.messages[0]] + self.messages[starts[-self.keep_turns]:]
            return
        if len(self.messages) <= self.max_history:
            return
        starts = [i for i, m in enumerate(self.messages) if m["role"] == "user" and i > 0]
        for s in starts:
            if len(self.messages) - s + 1 <= self.max_history:
                self.messages = [self.messages[0]] + self.messages[s:]
                return

    # ----------------------------------------------------------------- public
    def ask(self, text):
        t0 = time.time()
        self.stats["turns"] += 1
        tok0 = self.stats["prompt_tokens"] + self.stats["output_tokens"]
        self.user_texts.append(text)
        guard.add_evidence(self.evidence, text)
        guard.add_evidence(self.user_evidence, text)
        self.messages.append({"role": "user", "content": text})
        self.events.append(("user", text))
        corrections_left, answer, verified = 2, "", True
        tools_this_turn, turn_start = 0, len(self.messages)
        self._failed_calls = set()
        self._designs_this_turn = set()
        self.turn_fields = {}
        for _ in range(self.max_steps):
            out = self._llm()
            if out["tool_calls"]:
                self.messages.append({"role": "assistant", "content": out["content"],
                                      "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}}
                                                     for c in out["tool_calls"]]})
                for c in out["tool_calls"]:
                    tools_this_turn += 1
                    result, ok = self._run_tool(c["name"], c["arguments"])
                    self.stats["tool_calls"] += 1
                    if not ok:
                        self.stats["rejected_tool_calls"] += 1
                    else:
                        guard.add_evidence(self.evidence, result)
                        if isinstance(result, dict) and isinstance(result.get("recommended_design"), str):
                            self.best_design = result["recommended_design"]
                        if isinstance(result, dict) and isinstance(result.get("lowest_cost_design_meeting_all_constraints"), dict):
                            self.cheapest = result["lowest_cost_design_meeting_all_constraints"]["name"]
                        names_now = ([result["name"]] if isinstance(result, dict) and isinstance(result.get("name"), str)
                                     else [d.get("name") for d in result.get("designs", [])] if isinstance(result, dict) else [])
                        self._designs_this_turn.update(n for n in names_now if n)
                        if isinstance(result, dict):
                            for v in (result.get("changes_vs_previous_evaluation_of_this_design") or {}).values():
                                if isinstance(v, dict) and isinstance(v.get("before"), (int, float)) \
                                        and isinstance(v.get("after"), (int, float)):
                                    self.changes.append((float(v["before"]), float(v["after"])))
                        if "P3_ESP_INTAKE" in json.dumps(result, default=str):
                            self.esp_warning_seen = True
                        self._collect_design_texts(result)
                        self._collect_design_evidence(result)
                    payload = json.dumps(self._for_llm(c["name"], result), separators=(",", ":"), default=str)
                    self.messages.append({"role": "tool", "content": payload, "tool_name": c["name"]})
                    self.events.append(("tool", c["name"], c["arguments"], payload, ok))
                continue
            answer = out["content"]
            bad = guard.check_claims(answer, self.evidence) + guard.check_design_numbers(
                answer, self.design_evidence, self.user_evidence)
            # only the CURRENT question can make a component "asked about" (demo 12: Q3 asked about a heat pump, so
            # Q5's invented heat pump passed)
            comps = guard.check_components(answer, self.design_texts, self.user_texts[-1:], list(self.design_evidence))
            stmts = []
            lows = [self._lowest_co2(), self._lowest_co2(feasible_only=True)]
            for s_ in guard.check_superlatives(answer, lows):
                stmts.append(f"you write '{s_}', but the lowest-CO2 design in the tool results is {lows[0]}"
                             + (f" ({lows[1]} among designs meeting all constraints)" if lows[1] and lows[1] != lows[0] else ""))
            # design figures not among the fixed challenge facts and not given by the user in this question
            result_numbers = [x for x in guard.numbers_with_units(answer) if x[3] in guard.DESIGN_UNITS
                              and not guard._matches(x[0], x[1], self.facts.get(x[3], set()), x[3])]
            if tools_this_turn == 0 and guard.EXPLAIN_RE.search(self.user_texts[-1]) \
                    and guard.DESIGN_TOPIC_RE.search(answer):
                stmts.append("you explain designs without calling any tool for this question, so the explanation is not "
                             "grounded in results. Call compare_designs for the designs involved (e.g. ['2x2500m','3x2500m']) "
                             "and explain from their KPIs and heating_limit_on_peak_day")
            elif tools_this_turn == 0 and result_numbers \
                    and not any(u in guard.DESIGN_UNITS for _, _, _, u in guard.numbers_with_units(self.user_texts[-1])):
                stmts.append("you quote design results without calling any tool for this question; numbers from earlier "
                             "turns may belong to other designs or assumptions. Call compare_designs for exactly the "
                             "designs you discuss (e.g. ['2x2500m','3x2500m']) and answer from that result")
            for s_ in guard.check_compliance_claims(answer, bool(self.feasible)):
                stmts.append(f"you state '{s_}', but no evaluated design has meets_all_constraints=true")
            for t_ in guard.check_attribution(answer, self.not_given):
                stmts.append(f"you attribute the {t_} to the organisers, but get_challenge_inputs lists it under "
                             "not_given_by_challenge; say it is not given and ask the user")
            for f_ in guard.check_field_citations(answer, self.design_fields, self.turn_fields):
                stmts.append(f"you write {f_}")
            for p_ in guard.check_peak_dates(answer, self.peak_dates):
                stmts.append(f"you write that {p_}")
            for o_ in guard.check_oversized_recommendation(answer, self.oversized):
                stmts.append(f"you recommend {o_}; oversized units only add cost, so recommend the right-sized design "
                             "(sweep_designs: recommended_design) or evaluate one with the component resized/removed")
            for c_ in guard.check_change_direction(answer, self.changes):
                stmts.append(f"you write {c_}; use 'before' and 'after' from changes_vs_previous_evaluation_of_this_design")
            for d_ in guard.check_demand_claims(answer):
                stmts.append(f"you write '{d_}', but heating and cooling demand are fixed challenge data; design "
                             "and assumption changes alter how the demand is met, not the demand itself")
            for c_ in guard.check_comparisons(answer):
                stmts.append(f"your comparison '{c_}' has the wrong direction for the numbers it quotes")
            for c_ in guard.check_cost_claims(answer, self.cheapest):
                stmts.append(f"you write '{c_}', but the cheapest design meeting all constraints is {self.cheapest}")
            for r_ in guard.check_return_temperature(answer):
                stmts.append(f"you write '{r_}', but 100 C is the given supply temperature, not a return temperature")
            if self.best_design and re.search(r"\b(best|recommended)\s+design\b", self.user_texts[-1], re.I) \
                    and self._designs_this_turn and self.best_design not in self._designs_this_turn:
                stmts.append(f"the user asks about the best design, which is the current recommendation "
                             f"{self.best_design}, but you evaluated {', '.join(sorted(self._designs_this_turn))}; "
                             f"re-evaluate {self.best_design} (compare_designs) and answer for it")
            for a_ in guard.check_unfinished_actions(answer):
                stmts.append(f"you announce '{a_}' instead of doing it; call the tool now, or ask the user what you need")
            if (bad or comps or stmts) and corrections_left:
                corrections_left -= 1
                self.stats["claim_corrections"] += 1
                parts = []
                if bad:
                    parts.append(f"these numbers (with their units) are not supported by any tool result or by the user: "
                                 f"{', '.join(bad)}. Obtain them with a tool, ask the user, or remove them")
                if comps:
                    parts.append(f"you describe {', '.join(comps)} as part of the plant, but no evaluated design contains it "
                                 "(see the 'design' field). Say explicitly that it is missing/proposed, or remove it")
                parts += stmts
                note = ("[verifier] In your answer " + "; and ".join(parts) + ". Fix only these points and answer again, "
                        "keeping every correct result and recommendation from your previous answer.")
                self.messages += [{"role": "assistant", "content": answer}, {"role": "user", "content": note}]
                self.events.append(("verifier", note))
                continue
            if bad or comps or stmts:
                verified = False
                self.stats["unverified_answers"] += 1
                answer += ("\n\n[verifier warning: " + "; ".join(
                    ([f"numbers not traceable to tool results: {', '.join(bad)}"] if bad else [])
                    + ([f"components not in any evaluated design: {', '.join(comps)}"] if comps else [])
                    + stmts) + "]")
            break
        else:
            answer = answer or "I could not finish within the step limit; please narrow the request."
        self._compress_turn(turn_start)
        self.messages.append({"role": "assistant", "content": answer})
        tokens = self.stats["prompt_tokens"] + self.stats["output_tokens"] - tok0
        self.events.append(("assistant", answer, verified, tokens, round(time.time() - t0, 1)))
        self._trim()
        return answer

    def transcript_markdown(self, title="Agent session"):
        lines = [f"# {title}", "", f"Model: `{getattr(self.llm, 'model', '?')}`", ""]
        for e in self.events:
            if e[0] == "user":
                lines += [f"**User:** {e[1]}", ""]
            elif e[0] == "tool":
                status = "" if e[4] else " **(rejected/failed)**"
                res = e[3] if len(e[3]) < 700 else e[3][:700] + " ..."
                lines += [f"> tool `{e[1]}`({json.dumps(e[2])}){status}", f"> -> `{res}`", ""]
            elif e[0] == "verifier":
                lines += [f"> *{e[1]}*", ""]
            elif e[0] == "assistant":
                lines += [f"**Agent:** {e[1]}", "",
                          f"*claims verified: {'yes' if e[2] else 'NO'} | tokens this turn: {e[3]} | time: {e[4]} s*", "", "---", ""]
        s = self.stats
        lines += ["## Session statistics", "", *(f"- {k.replace('_', ' ')}: {v}" for k, v in s.items()),
                  f"- earlier questions kept in context: {'all' if self.keep_turns is None else self.keep_turns}"]
        return "\n".join(lines)
