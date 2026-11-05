"""Replay a recorded agent session in the cockpit chat (for review and for the video pitch).

Plays back the real trace, transcript and ledger of a session from
``docs_geohackathon2026/evidence`` with the same "Steps taken" dropdown and verifier badge as a
live run, faster than real time and labelled as a replay. Nothing is re-generated: what you see is
what was logged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCENARIO_NAMES = {
    "S1": "Full design, no user",
    "S2": "Vague request",
    "S3": "Off-topic question",
    "S4": "Impossible request",
    "S5": "What-if follow-ups",
}
EVIDENCE = Path(__file__).resolve().parents[3] / "docs_geohackathon2026" / "evidence"
_LABEL = re.compile(
    r"(\d+)x doublet @ (\d+) m \(<= (\d+) m3/h\)(.*), DH (\d+)/(\d+) C, gas (reinjected|burned)"
)


def _jsonl(path: Path) -> list[dict]:
    return (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if path.exists()
        else []
    )


def list_sessions() -> list[tuple[str, str]]:
    """(label, path) of every recorded session, scenario first."""
    out = []
    for d in sorted(EVIDENCE.glob("2026*")):
        if (d / "transcript.jsonl").exists():
            meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
            router = " · router" if meta.get("router") else ""
            sc = meta.get("scenario", "?")
            model = str(meta.get("model", "?")).removesuffix("-q4_K_M")
            out.append(
                (f"{sc} · {SCENARIO_NAMES.get(sc, '')} · {model}{router} · {d.name}", str(d))
            )
    return sorted(out)


def spec_from_label(label: str):
    """DesignSpec back from DesignSpec.label() (the ledger stores labels of searched designs)."""
    from gemini_agent.physics.design import DesignSpec

    m = _LABEL.match(label or "")
    if not m:
        return None
    n, depth, flow, mid, sup, ret, gas = m.groups()
    kw = {
        "n_doublets": int(n),
        "well_depth_m": float(depth),
        "max_flow_m3h": float(flow),
        "dh_return_temperature_c": float(ret),
        "heating_supply_temperature_c": float(sup),
        "gas_handling": "keep_in_solution_reinject" if gas == "reinjected" else "separate_and_burn",
        "heat_pump_mw": 0.0,
        "absorption_chiller_mw": 0.0,
        "electric_chiller_mw": 0.0,
        "backup_boiler_mw": 0.0,
    }
    for key, pat in (
        ("heat_pump_mw", r"HP ([\d.]+) MW"),
        ("absorption_chiller_mw", r"AbsCh ([\d.]+) MW"),
        ("electric_chiller_mw", r"ElCh ([\d.]+) MW"),
    ):
        x = re.search(pat, mid)
        if x:
            kw[key] = float(x.group(1))
    b = re.search(r"(gas|electric) boiler ([\d.]+) MW", mid)
    if b:
        kw["backup_fuel"], kw["backup_boiler_mw"] = b.group(1), float(b.group(2))
    return DesignSpec(**kw)


def _label_of(design_id: str, ledger: list[dict]) -> str | None:
    def walk(o):
        if isinstance(o, dict):
            if o.get("design_id") == design_id and isinstance(o.get("label"), str):
                return o["label"]
            for v in o.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None

    for f in ledger:
        r = walk(f.get("result"))
        if r:
            return r
    return None


def split_turns(events: list[dict], turns: list[dict]) -> list[list[dict]]:
    """Trace events per user turn (each turn ends with its last recorded model call)."""
    out, i = [], 0
    for t in turns:
        need, chunk = t["llm_calls"], []
        while i < len(events) and need > 0:
            e = events[i]
            chunk.append(e)
            i += 1
            if e["type"] == "llm":
                need -= 1
        while i < len(events) and events[i]["type"] != "llm":  # tool results after the last call
            chunk.append(events[i])
            i += 1
        out.append(chunk)
    return out


def counters(events: list[dict]) -> str:
    """Token meter for a replay (same look as a live session)."""
    llm = [e for e in events if e["type"] == "llm"]
    facts = sum(
        1
        for e in events
        if e["type"] == "tool_end" and str(e.get("output", "")).startswith('{"fact_id"')
    )
    tok = sum(e["prompt_tokens"] + e["completion_tokens"] for e in llm)
    secs = int(sum(e["latency_s"] for e in llm))
    return (
        f"<div class='gd-meter'>Replay · <b>{len(llm)}</b> model calls · <b>{tok / 1000:.1f}k</b> tokens · "  # noqa: E501
        f"<b>{secs // 60} min</b> model time (recorded) · <b>{facts}</b> facts</div>"
    )


def session_service(ledger: list[dict]):
    """A design service with the same site weather the session loaded (so replayed KPIs match "
    "the answer)."""
    from gemini_agent.physics.weather import fetch_weather
    from gemini_agent.service import DesignService

    wx = None
    for f in ledger:
        a = f.get("args") or {}
        if f.get("tool") == "fetch_weather" and a.get("latitude") is not None:
            try:
                wx = fetch_weather(
                    str(a.get("location") or "site"),
                    float(a["latitude"]),
                    float(a["longitude"]),
                    int(a.get("reference_year") or 2023),
                )
            except Exception:  # offline without the cached year: fall back to constant tower water
                wx = None
    if wx is None:  # the harness loads the documented default site weather at session start
        try:
            from gemini_agent.service import default_weather

            wx = default_weather()
        except Exception:
            wx = None
    return DesignService(weather=wx)
