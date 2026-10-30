"""Three memory layers.

* :class:`Scratchpad` - within one question: plan, tool results, retries.
  Cleared after the answer.
* :class:`RunLedger` - across the session (and kept on disk): every run
  with id, design, assumption overrides, headline KPIs and gate verdict.
  Lets the agent say "we tried 3 doublets, it cost X" without re-running.
* :class:`ProjectNotes` - across sessions: agreed assumptions, user
  decisions and lessons learned, as plain JSON + Markdown judges can read.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class Scratchpad:
    """Working memory for one question."""

    question: str = ""
    plan: str = ""
    tool_results: list = field(default_factory=list)  # (tool name, compact result)
    cited_runs: set = field(default_factory=set)
    gate_retries: int = 0
    steps: int = 0

    def clear(self):
        """Forget everything (called after each final answer)."""
        self.__init__()


def run_key(kind, payload):
    """Stable hash of a run request, used to reuse identical runs."""
    text = json.dumps({"kind": kind, **payload}, sort_keys=True, default=str)
    return hashlib.sha1(text.encode()).hexdigest()[:16]


class RunLedger:
    """Every simulation the agent ran, with full results on disk."""

    def __init__(self, workspace):
        """Open (or create) the ledger in ``workspace``."""
        self.dir = Path(workspace)
        self.runs_dir = self.dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "run_ledger.jsonl"
        self.entries = {}
        self._by_key = {}
        self._daily = {}
        self._summaries = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    e = json.loads(line)
                    self.entries[e["run_id"]] = e
                    if e.get("key"):
                        self._by_key[e["key"]] = e["run_id"]

    def next_id(self):
        """Return the next free run id (R0001, R0002, ...)."""
        nums = [int(r[1:]) for r in self.entries if r[1:].isdigit()]
        return f"R{(max(nums) + 1 if nums else 1):04d}"

    def find(self, key):
        """Return the run id of an identical earlier run, or None."""
        return self._by_key.get(key)

    def add(self, kind, key, request, headline, gate, summary=None, daily=None, extra=None):
        """Store a run; return its id."""
        run_id = self.next_id()
        entry = {
            "run_id": run_id,
            "time": _now(),
            "kind": kind,
            "key": key,
            "request": request,
            "headline": headline,
            "gate": gate,
            "valid": bool(gate.get("passed", True)),
        }
        if extra:
            entry.update(extra)
        self.entries[run_id] = entry
        if key:
            self._by_key[key] = run_id
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(exist_ok=True)
        if summary is not None:
            self._summaries[run_id] = summary
            (run_dir / "summary.json").write_text(
                json.dumps(summary, indent=1, default=float), encoding="utf-8"
            )
        if daily is not None:
            self._daily[run_id] = daily
            daily.to_csv(run_dir / "daily.csv", index=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=float) + "\n")
        return run_id

    def get(self, run_id):
        """Return the ledger entry of a run (KeyError if unknown)."""
        return self.entries[run_id]

    def summary(self, run_id):
        """Return the full summary dict of a run (from memory or disk)."""
        if run_id not in self._summaries:
            path = self.runs_dir / run_id / "summary.json"
            self._summaries[run_id] = (
                json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            )
        return self._summaries[run_id]

    def daily(self, run_id):
        """Return the daily DataFrame of a run (from memory or disk), or None."""
        if run_id not in self._daily:
            path = self.runs_dir / run_id / "daily.csv"
            self._daily[run_id] = pd.read_csv(path) if path.exists() else None
        return self._daily[run_id]

    def table(self, limit=10):
        """Return the latest runs as compact rows (for the agent's context)."""
        rows = []
        for e in list(self.entries.values())[-limit:]:
            rows.append(
                {
                    "run_id": e["run_id"],
                    "kind": e["kind"],
                    "valid": e["valid"],
                    **{k: v for k, v in (e.get("headline") or {}).items() if k != "top"},
                }
            )
        return rows


class ProjectNotes:
    """Long-lived notes: decisions, agreed assumptions, lessons learned."""

    KINDS = ("decision", "assumption", "lesson", "model")

    def __init__(self, workspace):
        """Open (or create) the notes file in ``workspace``."""
        self.dir = Path(workspace)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "project_notes.json"
        self.notes = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def add(self, kind, text, source="agent"):
        """Append a note and save JSON + Markdown."""
        if kind not in self.KINDS:
            raise ValueError(f"kind must be one of {self.KINDS}")
        note = {"time": _now(), "kind": kind, "text": text.strip(), "source": source}
        self.notes.append(note)
        self.path.write_text(json.dumps(self.notes, indent=1), encoding="utf-8")
        (self.dir / "project_notes.md").write_text(self.markdown(), encoding="utf-8")
        return note

    def search(self, query=""):
        """Return notes whose text contains every word of ``query`` (all if empty)."""
        words = query.lower().split()
        return [n for n in self.notes if all(w in n["text"].lower() for w in words)]

    def prompt_text(self, limit=12):
        """Return the latest notes as one line each, for the system prompt."""
        return " | ".join(f"{n['kind']}: {n['text']}" for n in self.notes[-limit:])

    def markdown(self):
        """Render the notes as Markdown."""
        lines = ["# Project notes (agent memory across sessions)", ""]
        for n in self.notes:
            lines.append(f"- **{n['kind']}** ({n['time']}, {n['source']}): {n['text']}")
        return "\n".join(lines) + "\n"
