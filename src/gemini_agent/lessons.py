"""Persistent memory written by the harness: every verifier rejection becomes a lesson.

The agent's prompt carries ``memory/AGENTS.md`` (see ``agents.memory_block``). Models may append
lessons themselves with ``edit_file``; small models rarely do. So the harness does it
deterministically: when a draft is rejected, the type of each issue maps to one general rule, which
is appended once (deduplicated) and read by every later session. The file is capped so the prompt
cannot grow without bound.
"""

from __future__ import annotations

import time
from pathlib import Path

MAX_LESSONS = 12  # beyond the seed line; oldest dropped first

RULES = {
    "request": "When the user specifies a design, simulate and present exactly that design "
    "(every stated capacity, depth and temperature).",
    "design": "Recommend only the latest design of the turn, and only after verify_design "
    "(stress tests, uncertainty, GEMINI solver) has passed on it.",
    "attribute": "Quote KPIs only for the design they belong to: check the depth and equipment "
    "in the design label before describing it.",
    "comparison": "Before writing 'cheaper', 'lower' or 'higher', compare the two numbers from the "
    "tool results.",
    "unit": "Write each number with the unit of its fact field (e.g. EUR/MWh, t CO2/yr, MW).",
    "unsupported": "Every number must come from a tool result or the brief; never quote a number "
    "that is not in a recorded fact.",
    "citation": "Cite only fact IDs that exist in this session; to quote a number, call the tool "
    "that produces it first.",
    "percentile": "A Monte Carlo P10/P50/P90 is not the design's value: label percentiles as such; "
    "the design's LCOE and CO2 come from evaluate_design.",
}


def lessons_for(prov: dict) -> list[str]:
    """General rules implied by a verifier result (one per issue type, in a stable order)."""
    kinds: list[str] = []
    for c in prov.get("claim_issues", []):
        kinds.append(c.get("type") or "attribute")
    if prov.get("unit_mismatches"):
        kinds.append("unit")
    if prov.get("unsupported"):
        kinds.append("unsupported")
    out: list[str] = []
    for k in kinds:
        rule = RULES.get(k)
        if rule and rule not in out:
            out.append(rule)
    return out


def record_lessons(memory_file: Path, lessons: list[str], session_id: str) -> list[str]:
    """Append new lessons to AGENTS.md (deduplicated, capped); returns the ones actually written."""
    memory_file = Path(memory_file)
    text = memory_file.read_text(encoding="utf-8") if memory_file.exists() else ""
    lines = text.rstrip("\n").split("\n") if text.strip() else []
    existing = [ln for ln in lines if ln.startswith("- ")]
    written = []
    for lesson in lessons:
        if any(lesson in ln for ln in existing):
            continue
        entry = (
            f"- ({time.strftime('%Y-%m-%d')}, session {session_id}, verifier rejection) {lesson}"
        )
        lines.append(entry)
        existing.append(entry)
        written.append(lesson)
    learned = [ln for ln in lines if ", verifier rejection) " in ln]  # never the seed
    if len(learned) > MAX_LESSONS:  # keep the seed and the newest lessons
        drop = set(learned[: len(learned) - MAX_LESSONS])
        lines = [ln for ln in lines if ln not in drop]
    if written:
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written
