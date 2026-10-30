"""The agent loop: LLM plans, tools run GEMINI, the physics gate decides what reaches the user.

One call to :meth:`DesignAgent.ask` handles one user message:

1. The LLM sees the system prompt (brief, gaps, project notes), a compact
   history of earlier answers, and the current question's messages.
2. Each tool call is validated (gate 1) and run; year runs pass gates
   2-5 inside the tool. Results go back to the LLM as compact JSON.
3. ``ask_user`` ends the turn with a question; the user's next message
   continues the same question.
4. A final answer must pass gate 6 (every number traceable, runs
   cited). If not, the error goes back to the LLM, which tries again.

Everything is logged to a :class:`~gemini_agent.transcript.Transcript`.
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from gemini_agent.config import AgentConfig
from gemini_agent.knowledge import assumptions_ledger, brief_summary, system_prompt
from gemini_agent.llm import estimate_tokens, make_llm
from gemini_agent.memory import ProjectNotes, RunLedger, Scratchpad
from gemini_agent.physics_gate import check_answer
from gemini_agent.tools import ToolBox, compact_json, openai_tool_schemas
from gemini_agent.transcript import Transcript
from gemini_design.challenge import CHALLENGE, load_demand

DEFAULT_INPUTS = Path(__file__).resolve().parents[2] / "simulator_examples" / "hackathon_inputs"
HISTORY_TURNS = 4  # earlier question/answer pairs kept in the context
PREVIEW_CHARS = 400
_RUN_ID = re.compile(r"\bR\d{4}\b")
LOOP_PREFIXES = ("[physics gate]", "[agent loop]")  # loop feedback, not user input


@dataclass
class AgentReply:
    """What the user gets back from one :meth:`DesignAgent.ask`."""

    kind: str  # "answer", "question" or "failed"
    text: str
    run_ids: list = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0


class DesignAgent:
    """Physics-gated design agent for the GeoHackathon plant."""

    def __init__(self, config=None, llm=None, inputs_dir=None, session_name=None, meta=None):
        """Set up memory, tools and the transcript; ``llm`` defaults to the configured endpoint."""
        self.config = config or AgentConfig()
        self.llm = llm or make_llm(self.config)
        self.workspace = Path(self.config.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.demand = load_demand(inputs_dir or DEFAULT_INPUTS)
        self.ledger = RunLedger(self.workspace)
        self.notes = ProjectNotes(self.workspace)
        self.tools = ToolBox(
            self.demand, self.ledger, self.notes, self.workspace, self.config.screen_workers
        )
        self.tool_schemas = openai_tool_schemas()
        self.scratch = Scratchpad()
        self.history = []  # compact earlier turns: user question + final answer
        self.episode = []  # messages of the question being worked on
        self.pending_question = False
        name = session_name or time.strftime("session_%Y%m%d_%H%M%S")
        info = {
            "model": getattr(self.llm, "model", None) or self.config.model,
            "provider": self.config.provider,
            "base_url": self.config.base_url,
            "config": self.config.public_dict(),
        }
        info.update(meta or {})
        self.transcript = Transcript(self.workspace / "transcripts", name, info)

    # ------------------------------------------------------------ context
    def _messages(self):
        sys_msg = {"role": "system", "content": system_prompt(self.notes.prompt_text())}
        return [sys_msg] + self.history[-2 * HISTORY_TURNS :] + self.episode

    def _brief_sources(self):
        users = [
            m["content"]
            for m in self.episode
            if m["role"] == "user" and not m["content"].startswith(LOOP_PREFIXES)
        ]
        return [
            brief_summary(),
            CHALLENGE,
            {k: v["value"] for k, v in assumptions_ledger().items()},
            *users,
            *[m["content"] for m in self.history],
        ]

    def _evidence(self, answer):
        evidence = [m["content"] for m in self.episode if m["role"] == "tool"]
        for run_id in set(_RUN_ID.findall(answer)):
            if run_id in self.ledger.entries:
                evidence.append(self.ledger.get(run_id).get("headline", {}))
                summary = self.ledger.summary(run_id)
                if summary is not None:
                    evidence.append(summary)
        return evidence

    # ------------------------------------------------------------ main loop
    def ask(self, text):
        """Handle one user message; return an :class:`AgentReply`."""
        if not self.pending_question:
            self.scratch.clear()
            self.scratch.question = text
            self.episode = []
        self.pending_question = False
        self.episode.append({"role": "user", "content": text})
        self.transcript.log("user", text=text)
        tokens = {"prompt": 0, "completion": 0, "calls": 0}

        while self.scratch.steps < self.config.max_steps_per_question:
            self.scratch.steps += 1
            try:
                resp = self.llm.chat(self._messages(), self.tool_schemas)
            except Exception as exc:  # endpoint down, bad JSON, ...
                self.transcript.log("llm_error", error=str(exc))
                return self._finish("failed", f"The language model could not be reached: {exc}")
            tokens["prompt"] += resp.prompt_tokens
            tokens["completion"] += resp.completion_tokens
            tokens["calls"] += 1
            self.transcript.log(
                "llm",
                content=resp.content,
                reasoning=resp.reasoning,
                tool_calls=[{"name": c.name, "arguments": c.arguments} for c in resp.tool_calls],
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                reasoning_tokens=resp.reasoning_tokens,
                estimated=resp.estimated_tokens,
                latency_s=round(resp.latency_s, 2),
            )
            self.episode.append(resp.as_message())

            if resp.tool_calls:
                question = None
                for call in resp.tool_calls:
                    if call.name == "ask_user":
                        question = call.arguments.get("question", "").strip()
                        default = call.arguments.get("default_if_no_answer", "")
                        if default:
                            question += f" (If you do not know: {default}.)"
                        result = {"status": "question sent to the user; wait for the answer"}
                    else:
                        result = self.tools.call(call.name, call.arguments)
                    content = compact_json(result)
                    self.scratch.tool_results.append((call.name, result))
                    self.episode.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": content,
                        }
                    )
                    self.transcript.log(
                        "tool",
                        name=call.name,
                        arguments=call.arguments,
                        result_preview=content[:PREVIEW_CHARS],
                        result_tokens=estimate_tokens(content),
                        seconds=result.get("seconds", 0) if isinstance(result, dict) else 0,
                    )
                if question:
                    self.pending_question = True
                    return self._finish("question", question, tokens)
                continue

            answer = resp.content.strip()
            if not answer:
                self.episode.append(
                    {"role": "user", "content": "[agent loop] Empty reply. Answer or call a tool."}
                )
                continue
            errors = check_answer(
                answer, self._evidence(answer), self._brief_sources(), self.ledger
            )
            if errors:
                self.scratch.gate_retries += 1
                self.transcript.log("gate_reject", errors=errors, answer=answer)
                if self.scratch.gate_retries > self.config.max_gate_retries:
                    return self._finish(
                        "failed",
                        "I could not produce an answer whose numbers all trace back to a "
                        "simulation run, so I am not giving one. Latest valid runs: "
                        + ", ".join(r["run_id"] for r in self.ledger.table(5) if r["valid"]),
                        tokens,
                    )
                self.episode.append(
                    {
                        "role": "user",
                        "content": "[physics gate] Answer rejected: "
                        + " ".join(errors)
                        + " Fix this and answer again.",
                    }
                )
                continue
            cited = sorted(set(_RUN_ID.findall(answer)))
            self.transcript.log("gate_pass", cited=cited)
            return self._finish("answer", answer, tokens, cited)

        return self._finish(
            "failed",
            f"I stopped after {self.config.max_steps_per_question} steps without a validated "
            "answer. Please narrow the question.",
            tokens,
        )

    def _finish(self, kind, text, tokens=None, run_ids=None):
        tokens = tokens or {"prompt": 0, "completion": 0, "calls": 0}
        self.transcript.log("reply", reply_kind=kind, text=text, run_ids=run_ids or [])
        if kind != "question":
            # session memory keeps only the question and the validated answer
            self.history.append({"role": "user", "content": self.scratch.question})
            self.history.append({"role": "assistant", "content": text})
        self.transcript.save()
        return AgentReply(
            kind=kind,
            text=text,
            run_ids=run_ids or [],
            prompt_tokens=tokens["prompt"],
            completion_tokens=tokens["completion"],
            llm_calls=tokens["calls"],
        )

    def close(self):
        """Write the transcript files; return their paths."""
        return self.transcript.save()


def dump_json(obj):
    """Pretty JSON for CLI output."""
    return json.dumps(obj, indent=2, default=str)
