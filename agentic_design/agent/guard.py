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
KEY_UNITS = [("eur_per_mwh", "EUR/MWh"), ("_meur", "MEUR"), ("_pct", "%"), ("_c", "C"), ("_gwh", "GWh"), ("_mw", "MW"), ("_kt", "kt"), ("kt_per_year", "kt"),
             ("m3h", "m3/h"), ("_bar", "bar"), ("cop", "COP")]
ANSWER_UNIT_RE = re.compile(r"\s*(EUR\s*/\s*MWh|EUR\s+per\s+MWh|€\s*/\s*MWh|EUR\s*/\s*t\b|EUR\s+per\s+t\w*|MEUR|M€|"
                            r"°\s*C\b|°C|deg\s*C|C\b|GWh|MWh|MW|%|kt\b|m³/h|m3/h|bar\b)")
COP_BEFORE_RE = re.compile(r"COP[^0-9.]{0,25}$", re.I)
STRICT = {"C", "GWh", "MW", "%", "kt", "m3/h", "bar", "COP", "EUR/MWh", "MEUR"}
COMPONENT_TERMS = ["heat pump", "chiller", "absorption", "thermal storage", "storage tank", "chp"]
HEDGE_RE = re.compile(r"\b(no|not|neither|nor|none|missing|without|lack|cannot|could|would|propose|proposed|future|next|"
                      r"assumptions?|assumed|efficiency\s*\(|eta|lorenz|η|can|"
                      r"once|until|yet|consider|option|alternative|if|were|hypothetical|absent|unavailable|need|needs|require|requires|"
                      r"required)\b", re.I)


def _key_unit(key):
    k = str(key).lower()
    for suf, u in KEY_UNITS:  # exact suffix first: 'heat_pump_cop' must not match '_c' (a temperature)
        if k.endswith(suf):
            return u
    for suf, u in (("kt_per_year", "kt"), ("m3h", "m3/h"), ("cop", "COP"), ("_pct", "%")):
        if suf in k:
            return u
    return None


def _norm_unit(u):
    u = u.replace(" ", "").replace("deg", "°")
    if re.fullmatch(r"(EUR/MWh|EURperMWh|€/MWh)", u):
        return "EUR/MWh"
    if re.fullmatch(r"(MEUR|M€)", u):
        return "MEUR"
    if u.startswith("EUR/t") or u.startswith("EURpert"):
        return "EUR/t"
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


DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
SENT_END_RE = re.compile(r"[!?\n]|\.(?=\s)")
EFFICIENCY_BEFORE_RE = re.compile(r"(efficiency|eta|lorenz|η)[^0-9]{0,12}$", re.I)


def _sentence(text, i):
    starts = [m.end() for m in SENT_END_RE.finditer(text, 0, i)]
    m = SENT_END_RE.search(text, i)
    return text[(starts[-1] if starts else 0):(m.start() if m else len(text))]


def numbers_with_units(text):
    out = []
    text = DATE_RE.sub(lambda m: " " * len(m.group(0)), text or "")  # same length keeps positions
    # design names are not numbers: '2x3500m_HP1.5_EC10_RI' in a COP sentence was read as 'COP 2' (demo 10)
    text = re.sub(r"\b[1-3]x\d{3,4}m(?:_[A-Za-z]+[\d.]*)*", lambda m: " " * len(m.group(0)), text)
    for m in NUM_RE.finditer(text):
        s = m.group(0).replace(",", "")
        try:
            v = float(s)
        except ValueError:
            continue
        mu = ANSWER_UNIT_RE.match(text, m.end())
        unit = _norm_unit(mu.group(1)) if mu else None
        if unit is None and COP_BEFORE_RE.search(text[max(0, m.start() - 30):m.start()]):
            unit = "COP"
        if unit is None and v <= 20 and re.search(r"\bCOP\b", _sentence(text, m.start()), re.I) \
                and not EFFICIENCY_BEFORE_RE.search(text[max(0, m.start() - 30):m.start()]):
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


NAME_RE = re.compile(r"\b[1-3]x\d{3,4}m(?:_ID[\d.]+)?(?:_ESP\d+)?(?:_HP[\d.]+)?(?:_ABS[\d.]+)?(?:_EC[\d.]+)?(?:_RI)?\b")
TAG_COMPONENT = {"HP": "heat pump", "ABS": "absorption chiller", "EC": "electric chiller"}


def name_components(name):
    """Components and their sizes (MW) encoded in a canonical design name, e.g. 2x3500m_HP25_EC5."""
    return {TAG_COMPONENT[t]: float(v) for t, v in re.findall(r"_(HP|ABS|EC)([\d.]+)", name)}


def name_text(name):
    """A 'design' description built from a canonical name (sweep rows carry names, not descriptions)."""
    comps = name_components(name)
    inc = [f"{c} {v:g} MW" for c, v in comps.items()]
    miss = [c for c in TAG_COMPONENT.values() if c not in comps] + ["thermal storage"]
    return f"{name}: heating heat exchanger" + "".join("; " + x for x in inc) + ". NOT included: " + ", ".join(miss) + "."


def _expand_name(n, known):
    """A shorthand like '3x2500m' that was never evaluated stands for the evaluated designs it prefixes
    (demo 8: '3x2500m' meant 3x2500m_HP15_ABS5_EC5_RI and the check wrongly said it had no absorption chiller)."""
    if not known or n in known:
        return [n]
    full = [k for k in known if k.startswith(n + "_")]
    return full or [n]


def check_components(answer: str, design_texts: list, user_texts=(), known_names=()):
    """Components the answer presents as part of a plant that does not contain them.

    If a sentence names designs, the component must be in one of THOSE designs (from the name);
    otherwise it must be in at least one evaluated design. Hedged sentences ('could add a heat pump')
    and components the user asked about are allowed."""
    asked = " ".join(user_texts).lower()
    included = " ".join(t.lower().split("not included")[0] for t in design_texts)
    problems = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", answer):
        low = sentence.lower()
        named = NAME_RE.findall(sentence)
        expanded = [x for n in named for x in _expand_name(n, known_names)]
        pool = " ".join(name_text(n).lower().split("not included")[0] for n in expanded) if named else included
        for term in COMPONENT_TERMS:
            for m in re.finditer(re.escape(term), low):
                # a hedge must be NEAR the component (demo 13: "required" earlier in the sentence excused
                # "met through the backup boiler and heat pump")
                window = low[max(0, m.start() - 60):m.end() + 40]
                if HEDGE_RE.search(window) or term in pool or (not named and term in asked):
                    continue
                problems.append(term + (f" (not in {', '.join(named)})" if named else ""))
    return sorted(set(problems))


def check_geometry(tool, args, user_texts, esp_warning_seen=False):
    """Well geometry stays at its default unless the user asks (or a checker asked for a deeper ESP)."""
    asked = " ".join(user_texts).lower()
    errs = []
    if tool != "evaluate_design":
        return errs
    idm = args.get("well_inner_diameter_m")
    if idm is not None and abs(float(idm) - 0.20) > 1e-9 and not re.search(r"diameter|\bid\b|casing|tubing", asked):
        errs.append(f"well_inner_diameter_m={idm}: the user did not ask to change the well diameter; keep the default 0.20 m")
    esp = args.get("esp_depth_m")
    if esp is not None and abs(float(esp) - 650.0) > 1e-9 and not esp_warning_seen \
            and not re.search(r"\besp\b|pump depth|pump setting", asked):
        errs.append(f"esp_depth_m={esp}: no tool reported a low ESP intake and the user did not ask; keep the default 650 m")
    return errs


EXPLAIN_RE = re.compile(r"\b(why|explain|compare|comparison|difference|reason)\b", re.I)
DESIGN_TOPIC_RE = re.compile(r"\b(doublets?|depth|design|co2|heat pump|chiller|brine|flow)\b", re.I)


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
    sents = [x for x in re.split(r"(?<=[.!?])\s+|\n", _plain(answer)) if x.strip()]
    for i, sent in enumerate(sents):
        low = sent.lower()
        if re.match(r"\s*(these|this|those|they|it)\b", low) and i > 0:  # demo 13: "These values are ... provided by
            low = sents[i - 1].lower() + " " + low                     # the organisers" after naming the values
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


DESIGN_UNITS = {"%", "GWh", "kt", "MW", "EUR/MWh", "MEUR"}


def check_design_numbers(answer, design_evidence: dict, user_evidence: dict):
    """A number quoted in the context of a design must exist in THAT design's results.

    Context = design names on the line, or the last design name seen (numbered
    blocks like '1. **3x3000m:**' followed by bullets); headings reset it.
    """
    bad, ctx = [], None
    names = sorted(design_evidence, key=len, reverse=True)
    for line in _plain_keep_names(answer).split("\n"):
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


def check_superlatives(answer, lowest_names):
    """'X has the lowest CO2' must name a design the tools ranked lowest (overall or among feasible ones)."""
    if isinstance(lowest_names, str):
        lowest_names = [lowest_names]
    lowest_names = [n for n in (lowest_names or []) if n]
    if not lowest_names:
        return []
    depths = {re.match(r"\d+x(\d+)m", n)[1] for n in lowest_names if re.match(r"\d+x(\d+)m", n)}
    bad = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", _plain(answer)):
        if not SUPERLATIVE_RE.search(sent) or NEG_RE.search(sent):
            continue
        names = re.findall(r"\b\d+x\d+m(?:_[\w.]+)?\b", sent)
        ds = DEPTH_RE.findall(sent)
        if not (names or ds):
            continue
        ok = any(n in names for n in lowest_names) or (not names and any(d in depths for d in ds))
        if not ok:
            bad.append(sent.strip()[:110])
    return bad


# ---------------------------------------------------------------- checks added after demo 6
def _plain_keep_names(text):
    """Strip bold/code markers but keep underscores (field and design names contain them)."""
    return re.sub(r"[*`]", "", text or "")


FIELD_RE = re.compile(r"\b([a-z][a-z0-9_]*_(?:gwh|mw|pct|c|cop|kt_per_year|bar|m3h))\b\s*[=:]\s*\**\s*(-?\d+(?:\.\d+)?)", re.I)


def flat_fields(obj, out=None):
    """{lower-case key: set of numeric values} for every number in a result."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.setdefault(str(k).lower(), set()).add(float(v))
            else:
                flat_fields(v, out)
    elif isinstance(obj, list):
        for v in obj:
            flat_fields(v, out)
    return out


def check_field_citations(answer, design_fields: dict, turn_fields: dict):
    """'cooling_unmet_GWh = 0.0' must be that field's value for the design(s) in context; without a design
    name, for a design evaluated this turn (demo 6: 0.0 quoted for designs whose value was 23.74)."""
    bad, ctx = [], None
    names = sorted(design_fields, key=len, reverse=True)
    for line in _plain_keep_names(answer).split("\n"):
        here = [n for n in names if re.search(rf"(?<![\w.]){re.escape(n)}(?![\w.])", line)]
        if here:
            ctx = here
        elif line.lstrip().startswith("#"):
            ctx = None
        for m in FIELD_RE.finditer(line):
            key, v = m.group(1).lower(), float(m.group(2))
            dec = len(m.group(2).split(".")[1]) if "." in m.group(2) else 0
            pools = [design_fields[n].get(key) for n in ctx] if ctx else [turn_fields.get(key)]
            pool = set().union(*[p for p in pools if p])
            if pool and not _matches(v, dec, pool, "field"):  # no kt<->t rescaling for a named field
                bad.append(f"{m.group(1)} = {m.group(2)} (the results give {', '.join(f'{x:g}' for x in sorted(pool))}"
                           + (f" for {', '.join(ctx)})" if ctx else " for the designs evaluated in this question)"))
    return bad


PEAK_RE = re.compile(r"peak\s+(heating|cooling)\s+day", re.I)


def check_peak_dates(answer, peak_dates: dict):
    """A date called 'the peak cooling day' must be the peak cooling day."""
    bad = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", _plain_keep_names(answer)):
        for m in PEAK_RE.finditer(sent):
            for d in DATE_RE.findall(sent):
                if d != peak_dates.get(m.group(1).lower()):
                    bad.append(f"{d} is called the peak {m.group(1).lower()} day, but that is {peak_dates.get(m.group(1).lower())}")
    return sorted(set(bad))


RECOMMEND_RE = re.compile(r"\b(recommend\w*|best|remains|choose|chosen|optimal|final|select\w*)\b", re.I)


def check_oversized_recommendation(answer, oversized: dict):
    """Recommending a design the checker flagged as oversized (P8) - capital cost is not modelled, so this
    is how the agent ended up proposing a 20 MW heat pump that delivers 0.3 GWh/yr (demo 6)."""
    bad = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", _plain_keep_names(answer)):
        if not RECOMMEND_RE.search(sent) or NEG_RE.search(sent):
            continue
        for n in NAME_RE.findall(sent):
            if n in oversized:
                bad.append(f"{n} ({oversized[n]})")
    return sorted(set(bad))


# ---------------------------------------------------------------- check added after demo 7
FROM_TO_RE = re.compile(r"from\s+\**\s*(-?\d+(?:\.\d+)?)[^\d\n]{0,25}?\s+to\s+\**\s*(-?\d+(?:\.\d+)?)", re.I)
UP_RE = re.compile(r"\b(increas\w*|improv\w*|rose|rais\w*|higher|grew|up)\b", re.I)
DOWN_RE = re.compile(r"\b(decreas\w*|reduc\w*|fell|dropped|lower\w*|down|declin\w*)\b", re.I)


def check_change_direction(answer, changes: list):
    """'X increased from A to B' must match a before/after pair the tools reported, in that order
    (demo 7 wrote 'increased from 88.4 % to 89.0 %' for a share that fell from 89.0 to 88.4)."""
    bad = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", _plain_keep_names(answer)):
        for m in FROM_TO_RE.finditer(sent):
            x, y = float(m.group(1)), float(m.group(2))
            fwd = any(abs(x - b) < 0.051 and abs(y - a) < 0.051 for b, a in changes)
            rev = any(abs(x - a) < 0.051 and abs(y - b) < 0.051 for b, a in changes)
            if rev and not fwd:
                bad.append(f"'{m.group(0).strip()}' reverses before and after (the tools report {y:g} before, {x:g} after)")
            elif fwd and x != y:
                up, down = UP_RE.search(sent), DOWN_RE.search(sent)
                if (y > x and down and not up) or (y < x and up and not down):
                    bad.append(f"'{sent.strip()[:90]}' gives the wrong direction ({x:g} -> {y:g})")
    return bad


# ---------------------------------------------------------------- checks added after demo 13
DEMAND_CHANGE_RE = re.compile(r"\b(increas|decreas|chang|rais|reduc|lower|higher)\w*\s+(?:the\s+)?(?:district'?s?\s+)?"
                              r"(heating|cooling)\s+demand", re.I)


def check_demand_claims(answer):
    """The demand is fixed challenge data: an assumption or design change cannot raise or lower it (demo 13:
    'the lower return temperature increases the heating demand')."""
    return [m.group(0) for m in DEMAND_CHANGE_RE.finditer(_plain_keep_names(answer))
            if not NEG_RE.search(_sentence(_plain_keep_names(answer), m.start()))]


COMPARE_RE = re.compile(r"\b(higher|lower|more|less|greater|smaller)\b[^.\n]{0,80}?\(?(-?\d+(?:\.\d+)?)\s*[^\d.\n()]{0,12}\)?"
                        r"[^.\n\d]{0,40}?\b(?:compared\s+(?:to|with)|than)\b[^.\n\d]{0,60}?\(?(-?\d+(?:\.\d+)?)", re.I)


def check_comparisons(answer):
    """'X is higher (A) compared to Y (B)' with A < B (demo 13: 'slightly higher (70.3%) compared to (70.4%)')."""
    bad = []
    text = re.sub(r"\b[1-3]x\d{3,4}m(?:_[A-Za-z]+[\d.]*)*", "design", _plain_keep_names(answer))
    for m in COMPARE_RE.finditer(text):
        word, a, b = m.group(1).lower(), float(m.group(2)), float(m.group(3))
        up = word in ("higher", "more", "greater")
        if (up and a < b) or (not up and a > b):
            bad.append(m.group(0).strip()[:120])
    return bad


# ---------------------------------------------------------------- checks added after demo 14
COST_PRIORITY_RE = re.compile(r"\b(cheapest|lowest[- ]cost|least expensive|cost is the (?:top |main )?priority|"
                              r"lowest (?:levelised )?cost)\b", re.I)


def check_cost_claims(answer, cheapest):
    """'If cost is the top priority, choose X' must name the cheapest design (demo 14 named the recommended one).
    Statements about cost WITH the CO2 value are exempt (the recommended design is cheapest on that basis)."""
    if not cheapest:
        return []
    bad = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", _plain_keep_names(answer)):
        if not COST_PRIORITY_RE.search(sent) or re.search(r"co2|carbon|eib|450", sent, re.I) or NEG_RE.search(sent):
            continue
        names = NAME_RE.findall(sent)
        if names and cheapest not in names:
            bad.append(sent.strip()[:110])
    return bad


RETURN_100_RE = re.compile(r"return\s+temperature[^.\n]{0,40}?\b100\s*(?:°\s*)?C\b", re.I)


def check_return_temperature(answer):
    """100 C is the given SUPPLY temperature, never the return (demo 14)."""
    return [m.group(0) for m in RETURN_100_RE.finditer(_plain_keep_names(answer))]
