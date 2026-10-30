"""Session log: every message, tool call, gate verdict and token count.

Written as JSON lines (machine-readable) and rendered to Markdown for the
report appendix, with a token table per question.
"""

import json
import time
from pathlib import Path


class Transcript:
    """Collects events of one agent session and writes them to disk."""

    def __init__(self, folder, session_name, meta=None):
        """Create ``<folder>/<session_name>.jsonl`` (and ``.md`` on :meth:`save`)."""
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.name = session_name
        self.events = []
        self.meta = meta or {}
        self.jsonl = self.folder / f"{session_name}.jsonl"
        self.jsonl.write_text("")
        self.log("session_start", **self.meta)

    def log(self, kind, **data):
        """Append one event."""
        event = {"t": time.strftime("%H:%M:%S"), "kind": kind, **data}
        self.events.append(event)
        with self.jsonl.open("a") as f:
            f.write(json.dumps(event, default=str) + "\n")
        return event

    # ------------------------------------------------------------ token stats
    def token_rows(self):
        """Return one row per question: LLM calls, tool calls, prompt/completion tokens."""
        rows, current = [], None
        for e in self.events:
            if e["kind"] == "user":
                if current is None or current.get("closed"):
                    current = {
                        "question": e["text"][:80],
                        "llm_calls": 0,
                        "tool_calls": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "reasoning_tokens": 0,
                        "llm_seconds": 0.0,
                        "gate_rejections": 0,
                        "outcome": "",
                        "estimated": False,
                    }
                    rows.append(current)
            elif current is None:
                continue
            elif e["kind"] == "llm":
                current["llm_calls"] += 1
                current["prompt_tokens"] += e["prompt_tokens"]
                current["completion_tokens"] += e["completion_tokens"]
                current["reasoning_tokens"] += e.get("reasoning_tokens", 0) or 0
                current["llm_seconds"] += e.get("latency_s", 0.0) or 0.0
                current["estimated"] = current["estimated"] or e.get("estimated", False)
            elif e["kind"] == "tool":
                current["tool_calls"] += 1
            elif e["kind"] == "gate_reject":
                current["gate_rejections"] += 1
            elif e["kind"] == "reply":
                current["outcome"] = e["reply_kind"]
                current["closed"] = e["reply_kind"] != "question"
        for r in rows:
            r.pop("closed", None)
        return rows

    def totals(self):
        """Session totals of LLM calls and tokens."""
        rows = self.token_rows()
        return {
            "questions": len(rows),
            "llm_calls": sum(r["llm_calls"] for r in rows),
            "tool_calls": sum(r["tool_calls"] for r in rows),
            "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
            "completion_tokens": sum(r["completion_tokens"] for r in rows),
            "reasoning_tokens": sum(r["reasoning_tokens"] for r in rows),
            "llm_seconds": round(sum(r["llm_seconds"] for r in rows), 1),
        }

    # ------------------------------------------------------------ markdown
    def markdown(self):
        """Render the session for humans (report appendix)."""
        m = self.meta
        lines = [f"# Agent transcript: {self.name}", ""]
        if m:
            lines.append(
                f"LLM: `{m.get('model', '?')}` via {m.get('provider', '?')} "
                f"({m.get('backend_note', '')})".rstrip()
            )
            lines.append("")
        for e in self.events:
            k = e["kind"]
            if k == "user":
                lines += [f"**User:** {e['text']}", ""]
            elif k == "llm":
                tok = f"{e['prompt_tokens']} in / {e['completion_tokens']} out"
                if e.get("estimated"):
                    tok += " (estimated)"
                if e.get("reasoning"):
                    thought = e["reasoning"].replace("\n", " ")
                    if len(thought) > 600:
                        thought = thought[:600] + " ..."
                    lines += [f"> _model thinking_: {thought}", ""]
                if e.get("content"):
                    lines += [f"> _agent reasoning_ ({tok}): {e['content']}", ""]
                else:
                    lines += [f"> _LLM call_ ({tok})", ""]
            elif k == "tool":
                args = json.dumps(e["arguments"], default=str)
                result = e["result_preview"]
                lines += [
                    f"- tool `{e['name']}` {args}",
                    f"  - result ({e['result_tokens']} tokens, {e['seconds']} s): `{result}`",
                    "",
                ]
            elif k == "gate_reject":
                lines += [f"- **physics gate rejected the answer:** {'; '.join(e['errors'])}", ""]
            elif k == "gate_pass":
                lines += [f"- physics gate 6 (no orphan numbers): pass, cites {e['cited']}", ""]
            elif k == "reply":
                label = {"question": "Agent asks", "answer": "Agent", "failed": "Agent (gave up)"}
                lines += [f"**{label.get(e['reply_kind'], 'Agent')}:** {e['text']}", ""]
        rows = self.token_rows()
        if rows:
            lines += [
                "## Token use",
                "",
                "| question | LLM calls | tool calls | prompt tok | completion tok | "
                "gate rejections | outcome |",
                "|---|---|---|---|---|---|---|",
            ]
            for r in rows:
                q = r["question"].replace("|", "/")
                lines.append(
                    f"| {q} | {r['llm_calls']} | {r['tool_calls']} | {r['prompt_tokens']} | "
                    f"{r['completion_tokens']} | {r['gate_rejections']} | {r['outcome']} |"
                )
            t = self.totals()
            lines.append(
                f"| **total** | {t['llm_calls']} | {t['tool_calls']} | {t['prompt_tokens']} | "
                f"{t['completion_tokens']} | | |"
            )
            if any(r["estimated"] for r in rows):
                lines += ["", "Token counts marked estimated use ~4 characters per token."]
        return "\n".join(lines) + "\n"

    def save(self):
        """Write the Markdown rendering next to the JSONL; return both paths."""
        md = self.folder / f"{self.name}.md"
        md.write_text(self.markdown())
        return self.jsonl, md
