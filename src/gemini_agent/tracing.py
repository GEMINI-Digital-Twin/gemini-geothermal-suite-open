"""Trace of every LLM call and tool call: tokens, latency, content (evidence log).

A LangChain callback handler records, per LLM call, the agent/subagent, prompt
and completion token counts (from the provider's usage metadata), latency and
any tool calls the model made; tool start/end events are logged too. Everything
is appended to ``runs/<session>/trace.jsonl`` and summarised for the UI/report.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


class TraceRecorder(BaseCallbackHandler):
    """Collects LLM/tool events; thread-safe; writes JSONL."""

    def __init__(self, path: str | Path | None = None, on_event=None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: list[dict] = []
        self._t0: dict[Any, float] = {}
        self._lock = threading.Lock()
        self.on_event = on_event

    # ---------------------------------------------------------------- helpers
    def _emit(self, ev: dict):
        ev["ts"] = round(time.time(), 3)
        with self._lock:
            self.events.append(ev)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, default=str) + "\n")
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception:  # UI callbacks must never break the agent
                pass

    @staticmethod
    def _agent_name(metadata: dict | None) -> str:
        md = metadata or {}
        return md.get("lc_agent_name") or md.get("langgraph_node") or "agent"

    # ------------------------------------------------------------- LLM events
    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kw):
        """Remember the start time of an LLM call."""
        self._t0[run_id] = time.time()

    def on_llm_end(self, response, *, run_id, metadata=None, **kw):
        """Record tokens, latency and tool calls of one LLM call."""
        dt = time.time() - self._t0.pop(run_id, time.time())
        gen = (
            response.generations[0][0] if response.generations and response.generations[0] else None
        )
        msg = getattr(gen, "message", None)
        usage = getattr(msg, "usage_metadata", None) or {}
        tool_calls = [
            {"name": tc.get("name"), "args": tc.get("args")}
            for tc in (getattr(msg, "tool_calls", None) or [])
        ]
        self._emit(
            {
                "type": "llm",
                "agent": self._agent_name(metadata),
                "model": (getattr(msg, "response_metadata", {}) or {}).get("model", ""),
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "latency_s": round(dt, 2),
                "tool_calls": tool_calls,
                "content": (getattr(msg, "content", "") or "")[:4000],
            }
        )

    def record_llm(
        self,
        agent: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_s: float,
        content: str = "",
    ):
        """An LLM call made outside LangChain (the optional router), so it counts in every total."""
        self._emit(
            {
                "type": "llm",
                "agent": agent,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_s": latency_s,
                "tool_calls": [],
                "content": content[:4000],
            }
        )

    # ------------------------------------------------------------ tool events
    def on_tool_start(self, serialized, input_str, *, run_id, metadata=None, **kw):
        """Remember tool start."""
        self._t0[run_id] = time.time()
        self._emit(
            {
                "type": "tool_start",
                "agent": self._agent_name(metadata),
                "tool": (serialized or {}).get("name"),
                "input": str(input_str)[:2000],
            }
        )

    def on_tool_end(self, output, *, run_id, metadata=None, **kw):
        """Record tool output (truncated) and duration."""
        dt = time.time() - self._t0.pop(run_id, time.time())
        content = getattr(output, "content", output)
        self._emit(
            {
                "type": "tool_end",
                "agent": self._agent_name(metadata),
                "tool": kw.get("name"),
                "latency_s": round(dt, 2),
                "output": str(content)[:3000],
            }
        )

    # --------------------------------------------------------------- summary
    def summary(self) -> dict:
        """Totals for the token meter."""
        llm = [e for e in self.events if e["type"] == "llm"]
        by_agent: dict[str, dict] = {}
        for e in llm:
            a = by_agent.setdefault(
                e["agent"], {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
            )
            a["calls"] += 1
            a["prompt_tokens"] += e["prompt_tokens"]
            a["completion_tokens"] += e["completion_tokens"]
        return {
            "llm_calls": len(llm),
            "prompt_tokens": sum(e["prompt_tokens"] for e in llm),
            "completion_tokens": sum(e["completion_tokens"] for e in llm),
            "llm_seconds": round(sum(e["latency_s"] for e in llm), 1),
            "tool_calls": sum(1 for e in self.events if e["type"] == "tool_end"),
            "by_agent": by_agent,
        }
