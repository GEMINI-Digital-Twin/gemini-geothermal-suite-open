"""Guardrails between the LLM and the tools, and between the LLM and the user.

1. ``check_arguments`` - before a tool runs: type, enum and bound checks from
   the JSON schema (a small model sometimes sends strings, or 4 doublets).
2. ``check_provenance`` - for values that are FACTS rather than design choices
   (an assumption the user supposedly gave), the number must actually appear
   in what the user wrote. This is the rule that would have stopped
   qwen2.5:7b inventing a 150 degC drive temperature in our tool-calling test.
3. ``check_claims`` - before an answer reaches the user: every number in it
   must match a number from a tool result or the user's own messages, within
   the rounding the answer shows. Unsupported numbers are sent back to the
   model once for correction; if they persist the answer is flagged.
"""

import re

NUM_RE = re.compile(r"(?<![A-Za-z_\d.])[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d])|(?<![A-Za-z_\d.])[-+]?\d+(?:\.\d+)?(?![\d])")
IGNORE_SMALL_INT = 10  # list numbering, counts like "2 doublets" are not treated as claims


def _type_ok(v, t):
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool) or (isinstance(v, float) and v.is_integer())
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "string":
        return isinstance(v, str)
    if t == "array":
        return isinstance(v, list)
    return True


def _coerce(v, t):
    """Small models often send '1500' instead of 1500; coerce when unambiguous."""
    if t in ("number", "integer") and isinstance(v, str):
        try:
            f = float(v.replace(",", ""))
            return int(f) if t == "integer" and f.is_integer() else f
        except ValueError:
            return v
    return v


def check_arguments(schema: dict, args: dict):
    """Returns (cleaned_args, errors)."""
    p = schema["function"]["parameters"]
    props, req = p.get("properties", {}), p.get("required", [])
    errors, clean = [], {}
    for k in req:
        if k not in args:
            errors.append(f"missing required argument '{k}'")
    for k, v in args.items():
        if k not in props:
            errors.append(f"unknown argument '{k}'")
            continue
        spec = props[k]
        v = _coerce(v, spec.get("type"))
        if spec.get("type") == "array" and isinstance(v, list):
            it = spec.get("items", {})
            v = [_coerce(x, it.get("type")) for x in v]
            for x in v:
                if not _type_ok(x, it.get("type")):
                    errors.append(f"'{k}' items must be {it.get('type')}, got {x!r}")
                elif "minimum" in it and x < it["minimum"] or "maximum" in it and x > it["maximum"]:
                    errors.append(f"'{k}' item {x} outside {it.get('minimum')}-{it.get('maximum')}")
        elif not _type_ok(v, spec.get("type")):
            errors.append(f"'{k}' must be {spec.get('type')}, got {v!r}")
        else:
            if "enum" in spec and v not in spec["enum"]:
                errors.append(f"'{k}' must be one of {spec['enum']}, got {v!r}")
            if "minimum" in spec and v < spec["minimum"] or "maximum" in spec and v > spec["maximum"]:
                errors.append(f"'{k}'={v} outside allowed range {spec.get('minimum')}-{spec.get('maximum')}")
            if spec.get("type") == "integer" and isinstance(v, float):
                v = int(v)
        clean[k] = v
    return clean, errors


def numbers_in(text: str):
    out = []
    for m in NUM_RE.finditer(text or ""):
        s = m.group(0).replace(",", "")
        try:
            out.append((float(s), len(s.split(".")[1]) if "." in s else 0, m.group(0)))
        except ValueError:
            pass
    return out


def check_provenance(tool: str, args: dict, user_texts: list):
    """Facts must come from the user. Design choices (depth, doublets) are free."""
    if tool == "set_assumption" and args.get("source") == "user":
        said = {v for t in user_texts for v, _, _ in numbers_in(t)}
        if float(args.get("value", float("nan"))) not in said:
            return [f"value {args.get('value')} is labelled source='user' but the user never wrote that number. "
                    "Ask the user for the value instead of assuming it."]
    return []


# ---------------------------------------------------------------- claim checking
# Unit categories: a number quoted with a unit must match evidence of the SAME
# unit (so "COP 3.5" cannot be "supported" by a 3.5 MW demand value).
KEY_UNITS = [("_pct", "%"), ("_c", "C"), ("_gwh", "GWh"), ("_mw", "MW"), ("_kt", "kt"), ("kt_per_year", "kt"),
             ("m3h", "m3/h"), ("_bar", "bar"), ("cop", "COP")]
ANSWER_UNIT_RE = re.compile(r"\s*(°\s*C\b|°C|deg\s*C|C\b|GWh|MWh|MW|%|kt\b|m³/h|m3/h|bar\b)")
COP_BEFORE_RE = re.compile(r"COP[^0-9.]{0,25}$", re.I)
STRICT = {"C", "GWh", "MW", "%", "kt", "m3/h", "bar", "COP"}
COMPONENT_TERMS = ["heat pump", "chiller", "absorption", "thermal storage", "storage tank", "chp"]
HEDGE_RE = re.compile(r"\b(no|not|missing|without|lack|cannot|could|would|propose|proposed|future|next|add|adding|"
                      r"once|until|yet|consider|option|alternative|if|were|hypothetical|absent|unavailable|need|needs|require|requires|"
                      r"required)\b", re.I)


def _key_unit(key):
    k = str(key).lower()
    for suf, u in KEY_UNITS:
        if k.endswith(suf) or suf in k:
            return u
    return None


def _norm_unit(u):
    u = u.replace(" ", "").replace("deg", "°")
    return {"°C": "C", "C": "C", "m³/h": "m3/h"}.get(u, u)


def new_evidence():
    return {"any": set()}


def add_evidence(ev, obj, unit=None):
    """Add every number in a tool result / user text, tagged with its unit when the key says it."""
    if isinstance(obj, bool) or obj is None:
        return ev
    if isinstance(obj, (int, float)):
        ev["any"].add(float(obj))
        if unit:
            ev.setdefault(unit, set()).add(float(obj))
    elif isinstance(obj, str):
        for v, _, raw, u in numbers_with_units(obj):
            ev["any"].add(v)
            if u:
                ev.setdefault(u, set()).add(v)
        for part in re.findall(r"\d+", obj):
            ev["any"].add(float(part))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            add_evidence(ev, v, _key_unit(k) or unit)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            add_evidence(ev, v, unit)
    return ev


def numbers_with_units(text):
    out = []
    for m in NUM_RE.finditer(text or ""):
        s = m.group(0).replace(",", "")
        try:
            v = float(s)
        except ValueError:
            continue
        mu = ANSWER_UNIT_RE.match(text, m.end())
        unit = _norm_unit(mu.group(1)) if mu else None
        if unit is None and COP_BEFORE_RE.search(text[max(0, m.start() - 30):m.start()]):
            unit = "COP"
        out.append((v, len(s.split(".")[1]) if "." in s else 0, m.group(0), unit))
    return out


def _matches(v, decimals, pool, unit):
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    rel = 0.005 * abs(v)
    for e in pool:
        if abs(v - e) <= max(tol, rel):
            return True
        if unit in (None, "kt", "GWh") and (abs(v - e / 1e3) <= tol or abs(v - e * 1e3) <= max(tol, rel)):
            return True
    return False


def check_claims(answer: str, evidence: dict):
    """Numbers in the answer not supported by evidence (respecting shown precision and units)."""
    unsupported = []
    for v, decimals, raw, unit in numbers_with_units(answer):
        if unit is None and v.is_integer() and abs(v) <= IGNORE_SMALL_INT:
            continue
        if unit in STRICT:
            pool = evidence.get(unit, set())
            if unit == "kt":
                pool = pool | {x / 1e3 for x in evidence.get("t", set())}
        else:
            pool = evidence["any"]
        if not _matches(v, decimals, pool, unit):
            unsupported.append(raw + (f" {unit}" if unit else ""))
    return unsupported


def check_components(answer: str, design_texts: list, user_texts=()):
    """Components the answer presents as part of the evaluated design but that no evaluated design contains.
    Components the user asked about may be discussed (e.g. 'what COP will our heat pump have?')."""
    asked = " ".join(user_texts).lower()
    designs = " ".join(design_texts).lower()
    designs = designs.split("not included")[0] if "not included" in designs else designs
    problems = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", answer):
        low = sentence.lower()
        for term in COMPONENT_TERMS:
            if term in low and term not in designs and term not in asked and not HEDGE_RE.search(low):
                problems.append(term)
    return sorted(set(problems))


# ---------------------------------------------------------------- statement checks (added after demo 2)
def _plain(text):
    return re.sub(r"[*_`]", "", text or "")


COMPLIANCE_RE = re.compile(r"\b(respects|meets|satisf(?:y|ies)|complies with|fulfils?|fulfills?)\s+(?:all|every)\s+"
                           r"(?:the\s+)?(?:\w+\s+)?(constraints|requirements|limits)|all\s+(?:the\s+)?constraints\s+"
                           r"(?:are\s+)?(?:met|satisfied|respected)|fully\s+compliant", re.I)
NEG_RE = re.compile(r"\b(not|n't|no|never|except|apart from|but|fails?|violat\w*)\b", re.I)


INTENT_RE = re.compile(r"\b(ensure|once|until|whether|would|could|to make|so that|if|aim|goal|need|needs|must)\b", re.I)


def check_compliance_claims(answer, any_feasible_design: bool):
    """'X meets all constraints' when no evaluated design does (statements of intent are fine)."""
    if any_feasible_design:
        return []
    bad = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", _plain(answer)):
        if COMPLIANCE_RE.search(sent) and not NEG_RE.search(sent) and not INTENT_RE.search(sent):
            bad.append(sent.strip()[:120])
    return bad


ATTR_RE = re.compile(r"(?:specified|given|provided|set|defined)\s+by\s+the\s+organi[sz]ers|"
                     r"organi[sz]ers\s+(?:have\s+|has\s+)?(?:specified|given|provided|set|defined)", re.I)


def check_attribution(answer, not_given_terms):
    """Claims that the organisers specified something they did not."""
    bad = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", _plain(answer)):
        low = sent.lower()
        for m in ATTR_RE.finditer(sent):
            before = low[max(0, m.start() - 25):m.start()]
            if re.search(r"\b(not|n't|never|no)\b", before) or re.search(r"\b(not|n't|never)\b", m.group(0).lower()):
                continue
            for term in not_given_terms:
                if term.lower() in low or term.split()[-1].lower() in low:
                    bad.append(term)
    return sorted(set(bad))


FUTURE_RE = re.compile(r"\b(?:we|i)(?:'ll|\s+will)\s+(?:now\s+|then\s+|first\s+)?(?:re-?evaluate|evaluate|run|compare|"
                       r"explore|check|calculate|simulate|re-?run|test|proceed)|\blet'?s\s+(?:re-?evaluate|evaluate|explore|run|"
                       r"compare|check|refine|test)|to proceed,?\s+(?:we|i)\s+will", re.I)


def check_unfinished_actions(answer):
    """The answer announces work instead of doing it."""
    return [m.group(0) for m in FUTURE_RE.finditer(_plain(answer))]


DESIGN_UNITS = {"%", "GWh", "kt", "MW"}


def check_design_numbers(answer, design_evidence: dict, user_evidence: dict):
    """A number quoted in the context of a design must exist in THAT design's results.

    Context = design names on the line, or the last design name seen (numbered
    blocks like '1. **3x3000m:**' followed by bullets); headings reset it.
    """
    bad, ctx = [], None
    names = sorted(design_evidence, key=len, reverse=True)
    for line in _plain(answer).split("\n"):
        here = [n for n in names if re.search(rf"(?<![\w.]){re.escape(n)}(?![\w.])", line)]
        if here:
            ctx = here
        elif line.lstrip().startswith("#") or not line.strip():
            ctx = None if line.lstrip().startswith("#") else ctx
        if not ctx:
            continue
        scrubbed = line
        for n in ctx:  # numbers inside the names themselves are not claims
            scrubbed = scrubbed.replace(n, " ")
        for v, dec, raw, unit in numbers_with_units(scrubbed):
            if unit not in DESIGN_UNITS:
                continue
            pool = set().union(*(design_evidence[n].get(unit, set()) for n in ctx)) | user_evidence.get(unit, set())
            if not _matches(v, dec, pool, unit):
                bad.append(f"{raw} {unit} (not in results of {', '.join(ctx)})")
    return bad


SUPERLATIVE_RE = re.compile(r"(lowest|least|minimum|smallest|best)\s+(?:\w+\s+){0,2}(co2|emissions?|carbon)|"
                            r"(co2|emissions?)\s+(?:\w+\s+){0,2}(lowest|least|minimum)|most\s+(?:viable|efficient|promising)", re.I)
DEPTH_RE = re.compile(r"(\d{4})\s?m\b")


def check_superlatives(answer, lowest_name):
    """'X has the lowest CO2' must name the design the tools ranked lowest (or its depth)."""
    if not lowest_name:
        return []
    lowest_depth = re.match(r"\d+x(\d+)m", lowest_name)
    bad = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", _plain(answer)):
        if not SUPERLATIVE_RE.search(sent) or NEG_RE.search(sent):
            continue
        names = re.findall(r"\b\d+x\d+m(?:_\w+)?\b", sent)
        depths = DEPTH_RE.findall(sent)
        mentioned = names or depths
        if not mentioned:
            continue
        ok = lowest_name in names or (lowest_depth and lowest_depth[1] in depths and not names)
        if not ok:
            bad.append(sent.strip()[:110])
    return bad
