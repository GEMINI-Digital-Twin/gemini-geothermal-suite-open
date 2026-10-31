"""The agent loop: LLM decides, tools compute, guards check, memory remembers.

    user -> LLM -> (tool call -> argument + provenance check -> tool -> result)* -> answer
         -> claim check (numbers must come from tools/user) -> user

Every step is recorded so a session can be exported as a transcript (the
evidence appendix the organisers asked for) with token counts.
"""

import json
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
is 10 MW). Prefer the lowest CO2 among designs that meet all constraints, and say what costs are not modelled. \
Store final choices with record_decision.
5. Before comparing or explaining designs, call compare_designs with exactly those designs (it refreshes results for \
the current assumptions). Quote each number only for the design it belongs to. Change only what the user asks; keep \
other design parameters at their defaults unless you state why. Never say a design meets all constraints unless its \
meets_all_constraints is true. Do not announce future actions: do them now with a tool, or ask the user.
6. Justify decisions with the specific KPIs, the computed heating_limit_on_peak_day and the constraint results. \
Name the assumptions used. Describe only components listed in a design's 'design' field; anything else is missing \
or proposed and must be called that. Compare a KPI only for the same design.
7. Be concise: short paragraphs or bullets, no repetition.

Memory from earlier sessions:
{memory}"""


class Agent:
    def __init__(self, llm, toolbox: ToolBox, max_steps=12, max_history=40):
        self.llm, self.tools = llm, toolbox
        self.max_steps, self.max_history = max_steps, max_history
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT.format(memory=toolbox.memory.summary())}]
        self.user_texts, self.evidence, self.design_texts = [], guard.new_evidence(), []
        self.user_evidence, self.design_evidence, self.feasible = guard.new_evidence(), {}, set()
        self.design_co2 = {}
        self.not_given = toolbox.get_challenge_inputs()["not_given_by_challenge"]
        self.events = []  # transcript
        self.stats = {"llm_calls": 0, "prompt_tokens": 0, "output_tokens": 0, "tool_calls": 0,
                      "rejected_tool_calls": 0, "claim_corrections": 0, "unverified_answers": 0, "turns": 0}

    # ----------------------------------------------------------------- internals
    def _llm(self):
        out = self.llm.chat(self.messages, SCHEMAS)
        self.stats["llm_calls"] += 1
        self.stats["prompt_tokens"] += out["prompt_tokens"]
        self.stats["output_tokens"] += out["output_tokens"]
        return out

    def _run_tool(self, name, args):
        if name not in SCHEMA_BY_NAME:
            return {"error": f"unknown tool '{name}'. Available: {sorted(SCHEMA_BY_NAME)}"}, False
        clean, errs = guard.check_arguments(SCHEMA_BY_NAME[name], args)
        errs += guard.check_provenance(name, clean, self.user_texts)
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

    def _lowest_co2(self):
        best = None
        for name, ev in self.design_evidence.items():
            co2 = self.design_co2.get(name)
            if co2 is not None and (best is None or co2 < best[1]):
                best = (name, co2)
        return best[0] if best else None

    def _collect_design_evidence(self, obj):
        """Numbers per design name, so a figure can be checked against the design it is quoted for."""
        if isinstance(obj, dict):
            if isinstance(obj.get("name"), str) and ("kpi" in obj or "co2_kt_per_year" in obj):
                ev = self.design_evidence.setdefault(obj["name"], guard.new_evidence())
                guard.add_evidence(ev, obj)
                co2 = obj.get("co2_kt_per_year", (obj.get("kpi") or {}).get("co2_kt_per_year"))
                if co2 is not None:
                    self.design_co2[obj["name"]] = co2
                if obj.get("meets_all_constraints") is True or (obj.get("violations") == [] and "kpi" in obj):
                    self.feasible.add(obj["name"])
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    self._collect_design_evidence(v)
        elif isinstance(obj, list):
            for v in obj:
                self._collect_design_evidence(v)

    def _trim(self):
        """Keep the system prompt and the most recent complete turns."""
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
        corrections_left, answer, verified = 1, "", True
        tools_this_turn = 0
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
                        self._collect_design_texts(result)
                        self._collect_design_evidence(result)
                    payload = json.dumps(result, separators=(",", ":"), default=str)
                    self.messages.append({"role": "tool", "content": payload, "tool_name": c["name"]})
                    self.events.append(("tool", c["name"], c["arguments"], payload, ok))
                continue
            answer = out["content"]
            bad = guard.check_claims(answer, self.evidence) + guard.check_design_numbers(
                answer, self.design_evidence, self.user_evidence)
            comps = guard.check_components(answer, self.design_texts, self.user_texts)
            stmts = []
            for s_ in guard.check_superlatives(answer, self._lowest_co2()):
                stmts.append(f"you write '{s_}', but the lowest-CO2 design in the tool results is {self._lowest_co2()}")
            if tools_this_turn == 0 and any(u in guard.DESIGN_UNITS for _, _, _, u in guard.numbers_with_units(answer)) \
                    and not any(u in guard.DESIGN_UNITS for _, _, _, u in guard.numbers_with_units(self.user_texts[-1])):
                stmts.append("you quote design results without calling any tool for this question; numbers from earlier "
                             "turns may belong to other designs or assumptions. Call compare_designs for exactly the "
                             "designs you discuss (e.g. ['2x2500m','3x2500m']) and answer from that result")
            for s_ in guard.check_compliance_claims(answer, bool(self.feasible)):
                stmts.append(f"you state '{s_}', but no evaluated design has meets_all_constraints=true")
            for t_ in guard.check_attribution(answer, self.not_given):
                stmts.append(f"you attribute the {t_} to the organisers, but get_challenge_inputs lists it under "
                             "not_given_by_challenge; say it is not given and ask the user")
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
        lines += ["## Session statistics", "", *(f"- {k.replace('_', ' ')}: {v}" for k, v in s.items())]
        return "\n".join(lines)
