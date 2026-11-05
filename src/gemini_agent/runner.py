"""Conversation runner shared by the CLI and the web cockpit.

One ``AgentRunner`` = one conversation: a Session (tools, ledger), a compiled
deep agent with an in-memory checkpointer (multi-turn), and a TraceRecorder.
Every final answer is passed through the deterministic provenance check; the
result is attached to the answer (and logged) so untraceable numbers are visible.
Before the model runs, the request is screened against the brief's hard limits.
Any rejected number, unit or claim (incl. a design simulated differently from
the one the user specified) triggers one revision request; the revised answer
is kept only if it has fewer issues, and the first draft is logged.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from ollama import ResponseError

from gemini_agent.agents import build_agent, memory_block
from gemini_agent.forge import load_generated
from gemini_agent.ledger import provenance_check
from gemini_agent.lessons import lessons_for, record_lessons
from gemini_agent.request_check import (
    comparison_hint,
    design_hint,
    missing_model_hint,
    missing_priority_hint,
    objective_hint,
    request_mismatches,
    requested_design,
    screen_request,
)
from gemini_agent.service import default_weather
from gemini_agent.tools import Session
from gemini_agent.tracing import TraceRecorder
from gemini_simulator.registry import COMPONENT_REGISTRY


class AgentRunner:
    """Holds one agent conversation."""

    def __init__(
        self,
        model: str | None = None,
        profile: str = "deep",
        mode: str = "interactive",
        harness: str = "lean",
        run_root: str | Path = "runs",
        on_event=None,
        llm=None,
        router=None,
        service=None,
        inputs_note: str | None = None,
    ):
        self.session_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.run_dir = Path(run_root) / self.session_id
        self.session = (
            Session(mode=mode, run_dir=self.run_dir, svc=service)
            if service is not None
            else Session(mode=mode, run_dir=self.run_dir)
        )  # service: custom inputs (cockpit)
        if self.session.svc.weather is None:  # the brief names no site: documented default, logged
            self.session.svc.weather = default_weather(self.session.svc.brief)
            self.session.assumptions_used.append(
                {
                    "question": "plant site (not in the brief; weather drives cooling-tower water)",
                    "assumed": "default site, loaded by the harness: "
                    + self.session.svc.weather.source,
                }
            )
        self.trace = TraceRecorder(self.run_dir / "trace.jsonl", on_event=on_event)
        self.profile, self.model_name, self.harness = profile, model, harness
        self.revise = os.environ.get("GEODESIGN_REVISE", "1") != "0"
        self.router = router  # optional gemini_agent.router.Router (None = off)
        self.workspace = Path(run_root) / "workspace"
        self.agent = build_agent(
            self.session,
            profile=profile,
            model=llm or model,
            workspace=self.workspace,
            harness=harness,
            checkpointer=InMemorySaver(),
        )
        self.thread = {
            "configurable": {"thread_id": self.session_id},
            "recursion_limit": 120,
            "callbacks": [self.trace],
        }
        self.transcript: list[dict] = []
        (self.run_dir / "meta.json").write_text(
            json.dumps(
                {
                    "model": model,
                    "profile": profile,
                    "mode": mode,
                    "harness": harness,
                    "inputs": inputs_note or "default",
                    "weather": self.session.svc.weather.source,
                    "llm_host": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
                    "router": (
                        None
                        if router is None
                        else {"temperature": router.temperature, "threshold": router.threshold}
                    ),
                    # what the agent remembered from earlier sessions when this one started
                    "memory_at_start": memory_block(self.workspace).split("\n", 1)[-1],
                },
                indent=2,
            )
        )

    def ask(self, message: str) -> dict:
        """Run one user turn to completion; returns answer + provenance + token summary."""
        # One clarifying question per turn -- none in the turn that answers our previous question.
        answered = bool(self.transcript and self.transcript[-1].get("pending_question"))
        self.session.question_budget = 0 if answered else 1
        if self.session.ask_tool is not None and self.session.mode != "auto":
            self.session.ask_tool.return_direct = not answered  # read by the agent loop at run time
        self.session.pending_question = None
        self.session.last_call = None
        self._retries = 0
        t0 = time.time()
        before, facts0 = len(self.trace.events), len(self.session.ledger.facts)
        screen = screen_request(message, self.session.svc.brief.constraints)
        content = (
            message
            if not screen
            else (
                f"{message}\n\n(harness request screen) {'; '.join(screen)}. First tell the "
                f"user this cannot be "
                "built as asked and quote the limit; then you may evaluate the closest "
                "feasible alternative."
            )
        )
        notes = (
            []
            if screen
            else [
                h
                for h in (
                    design_hint(message),
                    objective_hint(message),
                    missing_priority_hint(
                        message, bool(self.session.evaluations), self.session.mode
                    ),
                    missing_model_hint(message, self._registered_models()),
                    comparison_hint(message, self._current_spec(), self.session.current_design),
                )
                if h
            ]
        )
        if notes:
            content = content + "\n\n" + "\n".join(notes)
        hint = notes or None
        route = self._route(message, answered) if self.router is not None and not screen else None
        if route and route.get("reply"):  # the router answered a trivial turn itself: no agent call
            return self._record(
                {
                    "user": message,
                    "answer": route["reply"],
                    "pending_question": self.session.pending_question,
                    "nudges": 0,
                    "revised_from": None,
                    "request_screen": screen,
                    "router": route,
                    "provenance": provenance_check(route["reply"], self.session.ledger),
                    "seconds": round(time.time() - t0, 1),
                    "llm_calls": 1,
                    "prompt_tokens": route["prompt_tokens"],
                    "completion_tokens": route["completion_tokens"],
                    "tool_calls": [],
                    "current_design": self.session.current_design,
                }
            )
        state = self._invoke(content)
        answer, nudges = _final_text(state), 0
        # Small models sometimes stop with an empty message mid-procedure: nudge them (max 2x).
        while (
            (not answer or _tool_call_as_text(answer))
            and not self.session.pending_question
            and nudges < 2
        ):
            nudges += 1
            state = self._invoke(NUDGE)
            answer = _final_text(state)
        if self.session.pending_question and not answer.strip().endswith("?"):
            answer = (answer + "\n\n" if answer else "") + self.session.pending_question
        prov = self._verify(message, answer, facts0)
        first = None
        # Verifier feedback loop: any rejected number, unit or claim gets one revision request.
        if self.revise and not self.session.pending_question and _n_issues(prov):
            first = {"answer": answer, "provenance": prov}
            wanted = requested_design(
                message, self.session.evaluations, self.session.current_design, self._stressed()
            )
            if (
                wanted and wanted["design_id"] and wanted.get("verified")
            ):  # the exact design exists: tell the model what to copy
                wanted["fact"] = self._design_fact(wanted["design_id"])
                wanted["avoid"] = [
                    i for i in dict.fromkeys(_DESIGN_ID.findall(answer)) if i != wanted["design_id"]
                ]
            state = self._invoke(_revision_request(prov, wanted))
            revised = _final_text(state)
            rprov = self._verify(message, revised, facts0) if revised else None
            if rprov and _n_issues(rprov) < _n_issues(prov):
                answer, prov = revised, rprov
        # Memory: a rejected draft becomes a general lesson that every later session reads.
        lessons = (
            record_lessons(
                self.workspace / "memory" / "AGENTS.md",
                lessons_for(first["provenance"]),
                self.session_id,
            )
            if first
            else []
        )
        turn_events = self.trace.events[before:]
        llm = [e for e in turn_events if e["type"] == "llm"]
        turn = {
            "user": message,
            "answer": answer,
            "pending_question": self.session.pending_question,
            "nudges": nudges,
            "revised_from": first,
            "memory_lessons": lessons,
            "request_screen": screen,
            "harness_notes": hint,
            "router": route,
            "provenance": prov,
            "seconds": round(time.time() - t0, 1),
            "llm_calls": len(llm),
            "llm_retries": self._retries,
            "prompt_tokens": sum(e["prompt_tokens"] for e in llm),
            "completion_tokens": sum(e["completion_tokens"] for e in llm),
            "tool_calls": [e["tool"] for e in turn_events if e["type"] == "tool_end"],
            "current_design": self.session.current_design,
        }
        return self._record(turn)

    def _record(self, turn: dict) -> dict:
        self.transcript.append(turn)
        with open(self.run_dir / "transcript.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(turn, default=str) + "\n")
        (self.run_dir / "ledger.jsonl").write_text(self.session.ledger.to_jsonl())
        return turn

    def _route(self, message: str, answering: bool) -> dict | None:
        """Optional router decision; its reply (if confident) is written into the agent's memory."""
        design = bool(self.session.evaluations)
        previous = self.transcript[-1]["user"] if self.transcript else None
        try:
            d = self.router.classify(message, design, previous)
        except Exception as exc:  # router trouble must never block the agent
            return {"error": str(exc)}
        self.trace.record_llm(
            "router",
            self.router.model,
            d["prompt_tokens"],
            d["completion_tokens"],
            d["latency_s"],
            f"{d['label']} ({d['confidence']:.2f})",
        )
        d["reply"] = self.router.reply(d, self.session.mode, design, answering)
        if d["reply"]:
            from langchain_core.messages import AIMessage, HumanMessage

            # so the agent sees this exchange when the user answers the router's question
            self.agent.update_state(
                self.thread, {"messages": [HumanMessage(message), AIMessage(d["reply"])]}
            )
            if d["label"] == "incomplete":
                self.session.pending_question = d["reply"]
        return d

    def _invoke(self, content: str):
        """One agent call. An LLM-server error (Ollama rejects a malformed tool call with a 500)
        is retried once from the last checkpoint, with a note to the agent."""
        for attempt in (1, 2):
            try:
                return self.agent.invoke(
                    {"messages": [{"role": "user", "content": content}]}, self.thread
                )
            except ResponseError:
                self._retries += 1
                if attempt == 2:
                    raise
                time.sleep(3)
                content = (
                    "(harness) The model server rejected your last tool call (malformed JSON "
                    "arguments) and dropped it. Continue: call the tool again with valid arguments."
                )

    def _stressed(self) -> set:
        """Design ids that went through the stress tests (verify_design) in this session."""
        return {
            f.args.get("design_id")
            for f in self.session.ledger.facts
            if f.tool == "stress_test_design"
        }

    def _design_fact(self, design_id: str) -> dict | None:
        """The recorded KPIs of a design (its evaluate_design / add_capacity_margin fact) and its
        +10 % demand stress result, for a revision that must present exactly this design."""
        facts = self.session.ledger.facts
        kpi = next(
            (
                f
                for f in reversed(facts)
                if isinstance(f.result, dict)
                and f.result.get("design_id") == design_id
                and "lcoe_eur_per_mwh" in f.result
            ),
            None,
        )
        if kpi is None:
            return None
        stress = next(
            (
                f
                for f in reversed(facts)
                if f.tool == "stress_test_design"
                and f.args.get("design_id") == design_id
                and f.args.get("scenario") == "demand_plus_10"
            ),
            None,
        )
        return {
            "fid": kpi.fid,
            "lcoe": kpi.result.get("lcoe_eur_per_mwh"),
            "co2": kpi.result.get("co2_t_per_year"),
            "share": kpi.result.get("geothermal_share_of_heat_pct"),
            "plus10": None if stress is None else (stress.fid, stress.result.get("feasible")),
        }

    def _current_spec(self) -> dict | None:
        cur = self.session.current_design
        ev = self.session.evaluations.get(cur) if cur else None
        return ev.spec.model_dump() if ev else None

    @staticmethod
    def _registered_models() -> list[str]:
        load_generated()  # models created by the Model Forge in earlier sessions
        return sorted(COMPONENT_REGISTRY)

    def _verify(self, message: str, answer: str, facts0: int) -> dict:
        """Provenance + unit + claim checks, plus: was the design the user specified the one "
        "simulated?"""
        prov = provenance_check(answer, self.session.ledger)
        calls = [f.args for f in self.session.ledger.facts[facts0:] if f.tool == "evaluate_design"]
        ev = self.session.evaluations
        shown = [
            ev[i].spec.model_dump() for i in dict.fromkeys(_DESIGN_ID.findall(answer)) if i in ev
        ]
        req = request_mismatches(message, calls, shown) + self._design_status(
            answer, facts0, message
        )
        if req:
            prov["claim_issues"] = prov["claim_issues"] + req
            prov["passed"] = False
        return prov

    def _design_status(self, answer: str, facts0: int, message: str = "") -> list[dict]:
        """Rule 5 made checkable: a recommended design must be the latest one of the turn and, when the  # noqa: E501
        turn searched for a design, it must have been through verify_design's stress tests."""
        s, facts = self.session, self.session.ledger.facts
        ids = [i for i in dict.fromkeys(_DESIGN_ID.findall(answer)) if i in s.evaluations]
        turn = facts[facts0:]
        if not ids or not any(
            f.tool in ("search_designs", "add_capacity_margin", "evaluate_design") for f in turn
        ):
            return []
        issues, latest = [], s.current_design
        wanted = requested_design(message, s.evaluations, None, self._stressed())
        asked_for = bool(wanted and wanted["design_id"] in ids)
        if (
            latest
            and latest not in ids
            and not asked_for
            and any(f.tool == "add_capacity_margin" for f in turn)
        ):
            issues.append(
                {
                    "type": "design",
                    "claim": ids[0],
                    "detail": f"the answer presents design {ids[0]}, but this turn replaced it "
                    f"with {latest} "
                    f"({s.evaluations[latest].spec.label()}); present the latest design",
                }
            )
        stressed = {f.args.get("design_id") for f in facts if f.tool == "stress_test_design"}
        rec = ids[0]  # the design the answer presents is the first id it names
        if any(f.tool == "search_designs" for f in turn) and rec not in stressed:
            issues.append(
                {
                    "type": "design",
                    "claim": rec,
                    "detail": f"design {rec} is recommended but was never verified (stress "
                    "tests, uncertainty, "
                    "GEMINI solver); run verify_design on it first",
                }
            )
        return issues


def _final_text(state) -> str:
    msgs = state.get("messages", [])
    for m in reversed(msgs):
        if getattr(m, "type", "") == "ai" and (m.content or "").strip():
            c = m.content
            text = (
                c
                if isinstance(c, str)
                else "".join(b.get("text", "") for b in c if isinstance(b, dict))
            )
            text = _THINK.sub("", text).replace("</think>", "").replace("<think>", "").strip()
            if text:
                return text
    return ""


def _n_issues(prov: dict) -> int:
    return len(prov["unsupported"]) + len(prov["unit_mismatches"]) + len(prov["claim_issues"])


def _revision_request(prov: dict, requested: dict | None = None) -> str:
    """Harness message listing what the verifier rejected, as precise as the check itself. For a
    request mismatch it names the design to present, or the exact evaluate_design call to make."""
    lines = [
        f"- {u['number']} is written as '{u['unit_written']}' but the fact is {u['fact_fields'][0]}"
        for u in prov["unit_mismatches"]
    ]
    for c in prov["claim_issues"]:
        line = f"- \"{c['claim']}\": {c['detail']}"
        if c.get("type") == "request" and requested:
            if requested["design_id"] and requested.get("verified") is False:
                line += (
                    f"\n  -> Design {requested['design_id']} ({requested['label']}) matches the "
                    "request but was never verified: run verify_design on it; if a check fails, "
                    "add_capacity_margin on the part it names and verify again; then present the "
                    "verified design with its own numbers (never another design's check results)."
                )
            elif requested["design_id"]:
                line += (
                    f"\n  -> Your first line must be exactly 'Design ID: {requested['design_id']}' "
                    f"({requested['label']}): it is the design the user asked for."
                )
                fact = requested.get("fact")
                if fact:
                    line += (
                        f" Quote its own numbers from [{fact['fid']}]: LCOE {fact['lcoe']} EUR/MWh"
                        + (f", CO2 {fact['co2']:,.0f} t/yr" if fact.get("co2") is not None else "")
                        + (
                            f", geothermal share {fact['share']} %"
                            if fact.get("share") is not None
                            else ""
                        )
                        + "."
                    )
                    if fact.get("plus10"):
                        sfid, ok = fact["plus10"]
                        verdict = "passes" if ok else "FAILS"
                        line += f" Its +10 % demand test {verdict} [{sfid}]: say so."
                if requested.get("avoid"):
                    line += (
                        f" Do not present {', '.join(requested['avoid'])} as the design; a larger-"
                        "chiller variant may be named in one closing sentence as a recommendation."
                    )
                line += " Do not call tools for this."
            else:
                line += (
                    f"\n  -> Call evaluate_design with exactly {json.dumps(requested['args'])}, "
                    "then verify_design on the returned design_id, and present that design."
                )
        lines.append(line)
    if prov["unsupported"]:
        lines.append(
            f"- these numbers are in no tool result: {prov['unsupported']} -- call the tool that "
            "produces each (e.g. reservoir_at_depth, well_performance) or remove it"
        )
    redo = prov["unsupported"] or any(
        c.get("type") in ("request", "design") for c in prov["claim_issues"]
    )
    return (
        "(harness) The verifier rejected your answer:\n"
        + "\n".join(lines)
        + "\nFix only these errors and rewrite the answer (rule 10), using only numbers from tool results. "  # noqa: E501
        + (
            "If the design itself was wrong, call evaluate_design with exactly the requested "
            "design; run "
            "verify_design once on the design you recommend (deep profile: delegate it to "
            "risk-verifier); do not "
            "repeat any other step."
            if redo
            else "Do not call tools."
        )
    )


NUDGE = (
    "(harness) Your last reply was empty or a tool call written as text. Call tools through "
    "the tool "
    "interface; continue with the next step of your plan, or give the final answer in plain words."
)
_TOOL_TEXT = re.compile(r"^\s*[a-z_]+\s*\n?\s*\{\s*\"[a-z_]+\"\s*:", re.S)


def _tool_call_as_text(answer: str) -> bool:
    """e.g. 'ask_user\n{"question": ...}' -- a small model printing a tool call instead of "
    "making it."""
    return bool(_TOOL_TEXT.match(answer)) or answer.lstrip().startswith('{"name"')


_DESIGN_ID = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{10}(?![0-9a-f])"
)  # also inside paths: design_2bc0849d0d
_THINK = re.compile(r"<think>.*?</think>", re.S)  # reasoning models may leak their scratchpad
