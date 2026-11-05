"""Read what the agent claimed, and look the claims up in its run ledger.

Gate 6 already checks that every number in an answer can be traced to a run. These
helpers check what the answer *says*: which design it recommends, which verdict it
gives, and whether those match the runs and the oracle.
"""

import re

RUN_ID = re.compile(r"\bR\d{4}\b")
_RECOMMENDED = re.compile(r"recommended\s*:\s*\[?\s*(R\d{4})", re.I)
_VERDICT = re.compile(r"(verdict|premise)\s*:\s*\**\s*([A-Za-z_][A-Za-z_ \-]*)", re.I)


def cited_runs(text):
    """Run ids in ``text`` in order of first appearance."""
    return list(dict.fromkeys(RUN_ID.findall(text or "")))


def design_runs(ledger, run_ids):
    """The cited run ids that are year runs of a design."""
    return [r for r in run_ids if r in ledger.entries and ledger.get(r)["kind"] == "design"]


def recommended_run(text, ledger):
    """The run the answer recommends: a 'Recommended: [Rxxxx]' line, else the first cited."""
    m = _RECOMMENDED.findall(text or "")
    if m and m[-1] in ledger.entries:
        return m[-1]
    runs = design_runs(ledger, cited_runs(text))
    return runs[0] if runs else None


def verdict(text, label="verdict"):
    """The value of the last 'Verdict: X' (or 'Premise: X') line, upper case, or None."""
    found = [v for k, v in _VERDICT.findall(text or "") if k.lower() == label.lower()]
    if not found:
        return None
    return re.sub(r"[\s\-]+", "_", found[-1].strip()).upper().strip("_")


def mentions(text, *patterns):
    """True if any regex pattern matches ``text`` (case-insensitive)."""
    return any(re.search(p, text or "", re.I) for p in patterns)


def run_info(ledger, run_id):
    """Design arguments, overrides and KPIs of a design run (None if unknown)."""
    if not run_id or run_id not in ledger.entries:
        return None
    e = ledger.get(run_id)
    if e["kind"] != "design":
        return None
    req = dict(e.get("request") or {})
    overrides = dict(e.get("overrides") or req.pop("assumptions", {}) or {})
    req.pop("assumptions", None)
    if "chp" not in req and "chp_capacity_mw_el" in req:  # screen runs store the full Design
        req["chp"] = float(req["chp_capacity_mw_el"] or 0) > 0
    head = e.get("headline", {})
    return {
        "run_id": run_id,
        "args": req,
        "overrides": overrides,
        "valid": bool(e.get("valid")),
        "feasible": bool(head.get("meets_all_hard_rules")) and bool(e.get("valid")),
        "lcoe": head.get("lcoe_eur_per_mwh"),
        "co2": head.get("co2_t_per_year"),
        "design": head.get("design"),
        "failed_rules": head.get("failed_rules", []),
    }


def all_design_runs(ledger):
    """run_info for every design run in the ledger."""
    return [run_info(ledger, r) for r, e in ledger.entries.items() if e["kind"] == "design"]


def overrides_match(have, want, rel=0.02):
    """True if ``have`` sets every key of ``want`` to (about) the same value."""
    for k, v in (want or {}).items():
        if k not in (have or {}):
            return False
        x = float(have[k])
        if abs(x - float(v)) > rel * max(abs(float(v)), 1.0):
            return False
    return True


def args_match(have, want):
    """True if a run's design arguments include ``want`` (numbers compared loosely)."""
    for k, v in want.items():
        x = have.get(k)
        if isinstance(v, bool):
            if bool(x) != v:
                return False
        elif isinstance(v, str):
            if (x if x is not None else "legacy" if k == "chiller_type" else None) != v:
                return False
        elif x is None or abs(float(x) - float(v)) > 1e-6 * max(1.0, abs(float(v))):
            return False
    return True
