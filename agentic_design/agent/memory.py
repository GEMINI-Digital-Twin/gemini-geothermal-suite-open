"""Long-term memory: what the agent has evaluated, changed and decided.

Short-term memory is the chat history (trimmed). Long-term memory is this
JSON log, which survives between sessions and is summarised into the
system prompt at start-up, so the agent can say "we already tried 3x2500 m
yesterday and it failed C8" without re-running anything.
"""

import json
import time
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "memory" / "design_log.json"


class Memory:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)
        self.data = {"designs": {}, "assumption_changes": [], "decisions": [], "sessions": 0}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        self.data["sessions"] += 1
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    # ------------------------------------------------------------ writes
    def record_design(self, name, design_params, result, assumptions=None):
        self.data["designs"].pop(name, None)  # re-insert so the most recent stays last
        self.data["designs"][name] = {"params": design_params, "result": result, "assumptions": assumptions,
                                      "time": time.strftime("%Y-%m-%d %H:%M")}
        self.save()

    def record_assumption(self, name, old, new, reason, source):
        self.data["assumption_changes"].append({
            "name": name, "old": old, "new": new, "reason": reason, "source": source,
            "time": time.strftime("%Y-%m-%d %H:%M")})
        self.save()

    def record_decision(self, text, based_on):
        self.data["decisions"].append({"decision": text, "based_on": based_on, "time": time.strftime("%Y-%m-%d %H:%M")})
        self.save()

    # ------------------------------------------------------------ reads
    def design(self, name):
        return self.data["designs"].get(name)

    def assumption_overrides(self):
        """Latest value per assumption name (applied at start-up)."""
        out = {}
        for c in self.data["assumption_changes"]:
            out[c["name"]] = c["new"]
        return out

    def summary(self, max_designs=8) -> str:
        """Compact text for the system prompt (kept short to save tokens)."""
        lines = []
        designs = list(self.data["designs"].items())[-max_designs:]
        if designs:
            lines.append("Designs evaluated earlier (name: feasible | geothermal % | CO2 kt | violations):")
            for name, d in designs:
                r = d["result"]
                k = r.get("kpi", {})
                v = ",".join(x.split(":")[0] for x in r.get("violations", [])) or "none"
                lines.append(f"- {name}: {r.get('meets_all_constraints')} | {k.get('heating_geothermal_share_pct')} | "
                             f"{k.get('co2_kt_per_year')} | {v}")
        if self.data["assumption_changes"]:
            lines.append("Assumption changes: " + "; ".join(
                f"{c['name']} {c['old']}->{c['new']} ({c['source']}: {c['reason']})" for c in self.data["assumption_changes"][-5:]))
        if self.data["decisions"]:
            lines.append("Decisions so far: " + "; ".join(d["decision"] for d in self.data["decisions"][-5:]))
        return "\n".join(lines) if lines else "No earlier work in memory."
