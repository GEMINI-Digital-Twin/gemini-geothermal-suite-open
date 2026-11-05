"""Deterministic checks of the user's request (no LLM).

``screen_request`` compares the numbers a user asks for with the brief's hard limits before the
model sees the message, so an infeasible request (500 m3/h per doublet) is answered with the limit
instead of a clarifying question. ``request_mismatches`` compares an explicitly requested design
with the design the answer presents, or the evaluate_design calls made in the same turn (S5: '10 MW
electric chiller' was simulated as 10 MW absorption + 18 MW electric; S2: 'DH return is 50 C'
answered with a 100/45 C design).
"""

from __future__ import annotations

import json
import re

_NUM = r"(\d+(?:\.\d+)?)"
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_FIELDS = [  # (spec field, pattern); the first group is the value
    ("electric_chiller_mw", _NUM + r"\s*MW\s+(?:of\s+)?(?:an?\s+)?electric(?:al)?\s+chill"),
    ("absorption_chiller_mw", _NUM + r"\s*MW\s+(?:of\s+)?(?:an?\s+)?absorption"),
    ("backup_boiler_mw", _NUM + r"\s*MW\s+(?:[\w-]+\s+){0,2}boiler"),
    ("heat_pump_mw", _NUM + r"\s*MW\s+(?:[\w-]+\s+)?heat[- ]pump"),
    ("n_doublets", r"\b(\d|one|two|three|four|five|six)\s+(?:geothermal\s+)?doublets?\b"),
    ("well_depth_m", r"\b([1-5][,.]?\d{3})\s*m\b"),
    ("max_flow_m3h", _NUM + r"\s*m(?:3|³)\s*/\s*h"),
    (
        "dh_return_temperature_c",
        r"return(?:\s+temperature)?(?:\s+(?:is|of|at))?\s*[:=]?\s*" + _NUM + r"\s*°?\s*C\b",
    ),
]
BINDING = {"dh_return_temperature_c"}  # stated once, it is a design input even without other fields


def parse_request(text: str) -> dict:
    """Spec fields the user states with a single unambiguous value."""
    out = {}
    for name, pat in _FIELDS:
        vals = {
            float(_WORDS.get(v.lower(), None) or re.sub(r"[,]", "", v))
            for v in re.findall(pat, text, re.IGNORECASE)
        }
        if len(vals) == 1:
            out[name] = vals.pop()
    if re.search(r"\bgas(?:-fired)?\s+(?:backup\s+)?boiler", text, re.IGNORECASE):
        out["backup_fuel"] = "gas"
    elif re.search(r"\belectric(?:al)?\s+(?:backup\s+)?boiler", text, re.IGNORECASE):
        out["backup_fuel"] = "electric"
    if re.search(r"re-?inject", text, re.IGNORECASE):
        out["gas_handling"] = "keep_in_solution_reinject"
    elif re.search(r"\bburn(?:ed|t|ing)?\b.*\bgas\b|\bgas\b.*\bburn", text, re.IGNORECASE):
        out["gas_handling"] = "separate_and_burn"
    return out


def screen_request(text: str, constraints: dict) -> list[str]:
    """Requested values that break a hard limit of the brief."""
    req, notes = parse_request(text), []
    q = req.get("max_flow_m3h")
    if (
        q is not None
        and not constraints["min_flow_m3h_per_doublet"]
        <= q
        <= constraints["max_flow_m3h_per_doublet"]
    ):
        notes.append(
            f"{q:g} m3/h per doublet is outside the brief's hard limit of "
            f"{constraints['min_flow_m3h_per_doublet']:g}-{constraints['max_flow_m3h_per_doublet']:g} m3/h"  # noqa: E501
        )
    n = req.get("n_doublets")
    if n is not None and not constraints["n_doublets_min"] <= n <= constraints["n_doublets_max"]:
        notes.append(
            f"{n:g} doublets is outside the brief's limit of "
            f"{constraints['n_doublets_min']}-{constraints['n_doublets_max']} doublets"
        )
    return notes


def request_mismatches(
    text: str, calls: list[dict], presented: list[dict] | None = None
) -> list[dict]:
    """The user specified a design (>= 2 fields, or a binding one) but the design the answer presents  # noqa: E501
    (cited by ID), or else every evaluate_design call this turn, differs from it."""
    req = parse_request(text)
    req.pop("max_flow_m3h", None)  # a flow cap is not always a design field the user fixes
    calls = presented or calls
    if not calls or not (len(req) >= 2 or BINDING & req.keys()):
        return []

    def same(a, b):
        return (
            a == b
            if isinstance(b, str)
            else isinstance(a, (int, float)) and abs(float(a) - b) < 1e-6
        )

    match = [c for c in calls if all(same(c.get(k, _DEFAULTS.get(k)), v) for k, v in req.items())]
    if match:
        # an "evaluate exactly" request: fields the user did not mention must keep the documented
        # defaults (S6 deep slipped 100 m3/h and an electric boiler into a 300 m3/h gas design)
        if len(req) < 2 or any(not _deviations(c, req) for c in match):
            return []
        dev = _deviations(match[0], req)
        return [
            {
                "type": "request",
                "claim": text.strip()[:160],
                "detail": "the user did not ask for "
                + ", ".join(f"{k}={v}" for k, v in dev.items())
                + " (defaults: "
                + ", ".join(f"{k}={_DEFAULTS[k]}" for k in dev)
                + "): evaluate exactly the requested design with the defaults for everything else",
            }
        ]
    c = calls[-1]
    diff = {
        k: (v, c.get(k, _DEFAULTS.get(k)))
        for k, v in req.items()
        if not same(c.get(k, _DEFAULTS.get(k)), v)
    }
    return [
        {
            "type": "request",
            "claim": text.strip()[:160],
            "detail": "the user asked for "
            + ", ".join(
                f"{k}={v[0]:g}" if not isinstance(v[0], str) else f"{k}={v[0]}"
                for k, v in diff.items()
            )
            + (
                " but the design presented has "
                if presented
                else " but evaluate_design was called with "
            )
            + ", ".join(f"{k}={v[1]}" for k, v in diff.items())
            + (
                f" (and absorption_chiller_mw={c.get('absorption_chiller_mw')})"
                if "absorption_chiller_mw" not in req and c.get("absorption_chiller_mw")
                else ""
            ),
        }
    ]


def design_hint(text: str) -> str | None:
    """Harness note for an explicitly specified design (>= 2 fields): evaluate exactly it, ask nothing.  # noqa: E501
    (A 4B model otherwise applies the 'ask about priority and site' step to an evaluation request.)
    """
    req = parse_request(text)
    req.pop("dh_return_temperature_c", None) if len(req) < 2 else None
    if len(req) < 2:
        return None
    fields = ", ".join(f"{k}={v}" for k, v in req.items())
    return (
        f"(harness) The user specified a design: call evaluate_design with exactly {fields} and the "  # noqa: E501
        "defaults for everything else, then verify_design on it. Do not ask the user anything."
    )


_MIN_LCOE = re.compile(
    r"\b(cheapest|lowest[- ]cost|minimi[sz]e (?:the )?cost|cost only|as cheap as possible)\b", re.I
)
_MIN_CO2 = re.compile(
    r"\b(lowest (?:co2|co₂|emissions?)|minimi[sz]e (?:co2|co₂|emissions?)|zero[- ]carbon|"
    r"at any cost|regardless of (?:the )?cost|whatever (?:the|it) costs?)\b",
    re.I,
)
_BALANCED = re.compile(
    r"\b(balanc\w*|reasonable cost|trade[- ]?off|cost and (?:co2|co₂|emissions)|"
    r"(?:co2|co₂|emissions) and cost|low (?:co2|co₂|emissions) at)\b",
    re.I,
)
_DESIGN_REQ = re.compile(
    r"\b(design|build|plan|propose|size|dimension|lay ?out|configure|optimi[sz]e)\b", re.I
)
_ANY_OBJECTIVE = re.compile(
    r"\b(cost|cheap|lcoe|co2|co₂|emission\w*|carbon|balanc\w*|green|price)\b|€", re.I
)


def objective_hint(text: str) -> str | None:
    """The search objective the user's wording means (the agent may override, with reasons)."""
    if _BALANCED.search(text):
        why = "the user asked for a balance / low CO2 at reasonable cost (CO2 priced at 200 EUR/t)"
        obj = "balanced"
    elif _MIN_CO2.search(text):
        why, obj = "the user asked for the lowest CO2 and accepts the cost", "min_co2"
    elif _MIN_LCOE.search(text):
        why, obj = "the user asked for the cheapest design", "min_lcoe"
    else:
        return None
    return f"(harness) Objective for search_designs: {obj} -- {why}."


def missing_priority_hint(text: str, design_exists: bool, mode: str) -> str | None:
    """A design request with no cost/CO2 wording, before any design exists, in interactive mode:
    the agent must ask the one clarifying question instead of silently assuming a default."""
    if mode == "auto" or design_exists or len(parse_request(text)) >= 2:
        return None
    if _DESIGN_REQ.search(text) and not _ANY_OBJECTIVE.search(text):
        return (
            "(harness) The request states no cost vs CO2 priority: call ask_user once about it "
            "(offer 'balanced' as the default) and stop; design in the next turn."
        )
    return None


def _same(a, b) -> bool:
    return (
        a == b if isinstance(b, str) else isinstance(a, (int, float)) and abs(float(a) - b) < 1e-6
    )


def _defaults() -> dict:
    from gemini_agent.physics.design import DesignSpec

    return DesignSpec().model_dump()


_DEFAULTS = _defaults()


def _deviations(call: dict, req: dict) -> dict:
    """Spec fields the user did not state that differ from the documented defaults."""
    return {
        k: call[k]
        for k in _SPEC_ARGS
        if k not in req and call.get(k) is not None and not _same(call[k], _DEFAULTS[k])
    }


_SPEC_ARGS = (
    "well_depth_m",
    "n_doublets",
    "max_flow_m3h",
    "dh_return_temperature_c",
    "heat_pump_mw",
    "absorption_chiller_mw",
    "electric_chiller_mw",
    "backup_boiler_mw",
    "backup_fuel",
    "gas_handling",
)


def requested_design(
    text: str, evaluations: dict, current: str | None = None, verified: set | None = None
) -> dict | None:
    """The user fixed the design: the evaluated design that is exactly it (id + label), or else the
    evaluate_design arguments that produce it (the current design's fields with the user's values).
    None when the request does not fix a design or nothing was evaluated yet."""
    req = parse_request(text)
    req.pop("max_flow_m3h", None)
    if not evaluations or not (len(req) >= 2 or BINDING & req.keys()):
        return None
    exact = len(req) >= 2  # "evaluate exactly": everything the user did not state keeps its default
    matches = [
        (did, ev)
        for did, ev in evaluations.items()
        if all(_same(ev.spec.model_dump().get(k), v) for k, v in req.items())
        and (not exact or not _deviations(ev.spec.model_dump(), req))
    ]
    if matches:  # a verified match first (S2: the 50 C search candidate was never stress-tested)
        verified = verified or set()
        did, ev = next(((d, e) for d, e in matches if d in verified), matches[0])
        return {
            "design_id": did,
            "label": ev.spec.label(),
            "args": None,
            "verified": did in verified,
        }
    if exact:
        args = {k: _DEFAULTS[k] for k in _SPEC_ARGS}
    else:
        base = evaluations[current if current in evaluations else list(evaluations)[-1]].spec
        args = {k: getattr(base, k) for k in _SPEC_ARGS}
    args.update(req)
    return {"design_id": None, "label": None, "args": args}


# phenomenon the user may ask about -> (wording, registry name parts, where the inputs come from)
_CAPABILITIES = {
    "seasonal / underground heat storage": (
        re.compile(
            r"\b(seasonal|underground|thermal|heat|aquifer)[- ]storage\b|\bstor(e|ing)\b.{0,60}"
            r"\b(surplus|summer|heat|winter)\b|\bATES\b|\bBTES\b",
            re.I | re.S,
        ),
        ("ates", "storage", "btes"),
        "seasonal_balance on the current design gives the inputs (summer surplus, winter boiler "
        "heat)",
    ),
    "heat-network losses": (
        re.compile(r"\b(network|pipe|pipeline|distribution)\s+(heat\s+)?loss", re.I),
        ("network", "pipe", "loss"),
        "analyze_demand gives the delivered heat",
    ),
    "solar thermal": (
        re.compile(r"\bsolar[- ](thermal|collector)", re.I),
        ("solar",),
        "fetch_weather gives the site weather",
    ),
}


def missing_model_hint(text: str, registered: list[str]) -> str | None:
    """Missing-model detection: the request names a phenomenon; is a registered GEMINI component
    covering it? If not, the Model Forge path is the in-scope answer (never 'off-topic')."""
    for topic, (pat, keys, inputs) in _CAPABILITIES.items():
        if not pat.search(text):
            continue
        have = [m for m in registered if any(k in m.lower() for k in keys)]
        if have:
            return (
                f"(harness) {topic}: registered GEMINI model(s) {have} cover it -- {inputs}; "
                "use run_model on them. This is in scope."
            )
        return (
            f"(harness) Missing model: none of the {len(registered)} registered GEMINI components "
            f"covers {topic}. This is in scope, not off-topic. Read skill model-forge (read_file "
            f"/skills/model-forge/SKILL.md); {inputs}; write a declarative JSON spec and call "
            "generate_model; then run_model with those inputs and quantify the effect with fact "
            "IDs (deep profile: delegate this to model-builder)."
        )
    return None


_COMPARE = re.compile(
    r"\b(why not|instead of|rather than|compared? (?:to|with)|versus|vs\.?|what about|"
    r"would .{0,60}\b(?:cheaper|better|lower|higher|worse)|cheaper than)\b",
    re.I,
)
_DEPTHS = re.compile(r"\b(\d{1,2}[.,]?\d{3}|\d\.\d)\s*(?:m|km)\b", re.I)


def comparison_hint(text: str, current: dict | None, current_id: str | None = None) -> str | None:
    """A 'why not X' question about an alternative to the current design: the alternative must be
    simulated, not recalled. Gives the exact evaluate_design call (the current design with only the
    named fields changed) so that nothing else is silently dropped."""
    if not current or not _COMPARE.search(text):
        return None
    alt, changes = {k: current.get(k) for k in _SPEC_ARGS}, []
    for m in _DEPTHS.finditer(text):
        v = float(m.group(1).replace(",", ""))
        v = v * 1000 if v < 10 else v
        if abs(v - float(current.get("well_depth_m", 0))) > 1:
            alt["well_depth_m"], _ = v, changes.append(f"well_depth_m={v:g}")
            break
    req = parse_request(text)
    for k in ("n_doublets", "electric_chiller_mw", "backup_boiler_mw", "dh_return_temperature_c"):
        if k in req and abs(float(req[k]) - float(current.get(k, 0))) > 1e-6:
            alt[k], _ = req[k], changes.append(f"{k}={req[k]:g}")
    if re.search(r"\bheat[- ]pump", text, re.I) and not current.get("heat_pump_mw"):
        alt["heat_pump_mw"], _ = 10.0, changes.append("heat_pump_mw=10 (typical size; say so)")
    if re.search(r"\babsorption", text, re.I) and not current.get("absorption_chiller_mw"):
        alt["absorption_chiller_mw"] = current.get("electric_chiller_mw") or 10.0
        alt["electric_chiller_mw"] = 0.0
        changes.append("absorption chillers instead of electric")
    if "gas_handling" in req and req["gas_handling"] != current.get("gas_handling"):
        alt["gas_handling"], _ = req["gas_handling"], changes.append(
            f"gas_handling={req['gas_handling']}"
        )
    if not changes:
        return None
    alt = {k: (int(v) if k == "n_doublets" else v) for k, v in alt.items()}
    ids = f"['{current_id}', <new design_id>]" if current_id else "[current, new design_id]"
    return (
        "(harness) Comparison question: do not answer from memory. Call evaluate_design with "
        f"exactly {json.dumps(alt)} (the current design with {', '.join(changes)}; everything else "
        f"unchanged), then compare_designs({ids}) and quote both results with fact IDs."
    )
