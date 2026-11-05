"""Fact ledger and numeric provenance check (anti-hallucination layer).

Every tool result is stored as a fact with an ID (F1, F2, ...). The agent cites
fact IDs; ``provenance_check`` extracts every number from a piece of text and
verifies it against the numbers recorded in the ledger (plus the brief's fixed
inputs). Numbers that cannot be traced are reported as unsupported -- the
verifier rejects final answers that contain them. ``claim_check`` does the same
for words: a comparison ("lower LCOE than ...") or a design attribute ("the
2500 m option") must agree with the numbers it rests on.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from dataclasses import dataclass, field

NUM_RE = re.compile(
    r"(?<![A-Za-z_#\d])[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?"
)  # 50-300 = 2 numbers
# Numbers that are structural, not engineering claims.
TRIVIAL = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 100.0, 2026.0, 2027.0}


def _numbers_in(obj) -> list[float]:
    """All numeric leaves of a JSON-like object."""
    out: list[float] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_numbers_in(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_numbers_in(v))
    elif isinstance(obj, str):
        out.extend(_parse(m) for m in NUM_RE.findall(obj))
    return [x for x in out if math.isfinite(x)]  # inf (e.g. no break-even) would match every number


UNIT_HINTS = [  # (field-name suffix, accepted unit spellings), most specific first
    (
        "eur_per_mwh",
        {
            "€/mwh",
            "eur/mwh",
            "euro/mwh",
            "€ per mwh",
            "eur per mwh",
            "euro per mwh",
            "per mwh",
            "/mwh",
        },
    ),
    ("kg_per_mwh", {"kg/mwh", "kg per mwh", "kg co2/mwh", "kg co₂/mwh"}),
    ("_meur", {"m€", "meur", "million", "million eur", "million euro", "mln"}),
    ("_gwh", {"gwh"}),
    ("_mwh", {"mwh"}),
    ("_mw", {"mw"}),
    ("_kw", {"kw"}),
    ("co2_t", {"t", "tonnes", "tonne", "tons", "ton", "t/yr", "t co2", "t co₂", "tco2", "t/year"}),
    ("_t_per_year", {"t", "tonnes", "t/yr", "t/year"}),
    ("_pct", {"%", "percent"}),
    ("_m3h", {"m3/h", "m³/h"}),
    ("_bar", {"bar"}),
    ("_c", {"°c", "c", "degc", "deg c"}),
    ("_k", {"k", "kelvin"}),
]
UNIT_TOKEN_RE = re.compile(
    r"^\s*(€\s*per\s*mwh|eur\s*per\s*mwh|euro\s*per\s*mwh|per\s*mwh|per\s*kwh|€/mwh|eur/mwh|€/kwh|eur/kwh|/mwh|/kwh|"  # noqa: E501
    r"kg/mwh|kg|tonnes|tonne|tons|ton|t/yr|t|gwh|mwh|kwh|mw|kw|m€|meur|million|%|m³/h|m3/h|bar|°c|k|euros?|eur|€)"  # noqa: E501
    r"(?:\s*(?:/|per\s+)(?:yr|year|a|annum)\b)?(?![a-z0-9/²³])",
    re.IGNORECASE,
)


def _numbers_with_keys(obj, key: str = "") -> list[tuple[float, str]]:
    """(value, leaf field name) pairs of a JSON-like object."""
    out: list[tuple[float, str]] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append((float(obj), key))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            # a leaf without a unit in its name inherits the parent's (cooling_supply_gwh.absorption -> GWh)  # noqa: E501
            child = str(k) if _expected_units(str(k)) or not key else f"{key}.{k}"
            out.extend(_numbers_with_keys(v, child))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_numbers_with_keys(v, key))
    return out


def _strings_numbers(obj) -> list[float]:
    """Numbers that occur inside string values of a JSON-like object."""
    if isinstance(obj, str):
        return [_parse(m) for m in NUM_RE.findall(obj)]
    if isinstance(obj, dict):
        return [x for v in obj.values() for x in _strings_numbers(v)]
    if isinstance(obj, (list, tuple)):
        return [x for v in obj for x in _strings_numbers(v)]
    return []


def _expected_units(key: str) -> set[str] | None:
    k = key.lower()
    if "." in k:  # parent.leaf: the leaf name wins if it carries a unit, else the parent's
        leaf, parent = k.rsplit(".", 1)[1], k.rsplit(".", 1)[0]
        return _expected_units(leaf) or _expected_units(parent.split(".")[-1])
    for suffix, units in UNIT_HINTS:
        if k.endswith(suffix) or k == suffix.strip("_"):
            return units
    return None


# unit tokens that are scale variants of one quantity: a slip among them is a real error
_FAMILIES = [
    {"gwh", "mwh", "kwh"},
    {"mw", "kw"},
    {"t", "tonnes", "tonne", "tons", "ton", "t/yr", "t/year", "kg"},
    {"€/mwh", "eur/mwh", "€/kwh", "eur/kwh", "/mwh", "/kwh", "per mwh", "per kwh"},
]


def _same_family(unit: str, expected: list[set[str]]) -> bool:
    return any(unit in fam and any(e & fam for e in expected) for fam in _FAMILIES)


def unit_check(text: str, ledger: "FactLedger") -> list[dict]:
    """Numbers quoted with a unit that contradicts the unit of the fact they match exactly. A number
    that also occurs unkeyed (brief text, design labels) is only flagged for a scale slip within one
    quantity (MWh for GWh, kW for MW, kg for t, per kWh for per MWh), never across quantities."""
    keyed, free = [], _numbers_in(ledger.seed)
    for f in ledger.facts:
        keyed.extend(_numbers_with_keys(f.result))
        free.extend(
            _strings_numbers(f.result)
        )  # numbers inside labels ("DH 100/45 C") carry no unit key
    issues = []
    for m in NUM_RE.finditer(text):
        x = _parse(m.group())
        tail = text[m.end() : m.end() + 16]
        um = UNIT_TOKEN_RE.match(tail.replace("\u202f", " "))
        if not um or x in TRIVIAL:
            continue
        unit = um.group(1).lower().replace(" ", " ")
        free_match = any(abs(x - v) <= 1e-9 + 0.006 * abs(v) for v in free)
        if unit in {"%", "percent"} and any(
            abs(x / 100 - v) <= 0.006 * abs(v) for v, _ in keyed if v
        ):
            continue  # a fraction quoted as a percentage (probability 0.483 -> 48.3 %)
        cands = [k for v, k in keyed if v != 0 and abs(x - v) <= 0.006 * abs(v) + 0.051]
        expected = [u for u in (_expected_units(k) for k in cands) if u]
        if free_match and not _same_family(unit, expected):
            continue
        if expected and not any(
            unit in e or unit.replace(" ", "") in {s.replace(" ", "") for s in e} for e in expected
        ):
            issues.append(
                {"number": x, "unit_written": unit, "fact_fields": sorted(set(cands))[:3]}
            )
    return issues


def _parse(token: str) -> float:
    return float(token.replace(",", ""))


@dataclass
class Fact:
    """One recorded tool result."""

    fid: str
    tool: str
    args: dict
    result: dict
    t: float = field(default_factory=time.time)


class FactLedger:
    """Append-only store of tool results with ID allocation."""

    def __init__(self, seed: dict | None = None):
        self._lock = threading.Lock()
        self.facts: list[Fact] = []
        self.seed = seed or {}  # e.g. the brief's fixed inputs (citable as "brief")

    def record(self, tool: str, args: dict, result: dict) -> str:
        """Store a result; returns its fact ID."""
        with self._lock:
            fid = f"F{len(self.facts) + 1}"
            self.facts.append(Fact(fid, tool, dict(args), result))
            return fid

    def get(self, fid: str) -> Fact | None:
        """Fact by ID."""
        return next((f for f in self.facts if f.fid == fid), None)

    def known_numbers(self) -> list[float]:
        """Every number the agent is allowed to quote."""
        nums = _numbers_in(self.seed)
        for f in self.facts:
            # an argument the tool overrode is not a fact (asked samples=1000, result says samples=60)  # noqa: E501
            args = {
                k: v
                for k, v in f.args.items()
                if not (isinstance(f.result, dict) and k in f.result and f.result[k] != v)
            }
            nums.extend(_numbers_in(args))
            nums.extend(_numbers_in(f.result))
        return nums

    def to_jsonl(self) -> str:
        """Ledger as JSON lines (for the evidence appendix)."""
        return "\n".join(
            json.dumps(
                {"id": f.fid, "tool": f.tool, "args": f.args, "result": f.result}, default=str
            )
            for f in self.facts
        )


def _matches(x: float, known: list[float]) -> bool:
    """x equals a known number up to the rounding a writer would apply."""
    if x in TRIVIAL:
        return True
    for k in known:
        if k == 0:
            if abs(x) < 1e-9:
                return True
            continue
        if abs(x - k) <= max(0.051 * 10 ** _decimals_scale(x), 0.006 * abs(k)):
            return True
        # unit rescaling the writer may apply (MW<->kW, GWh<->MWh, t<->kt, M€) -- to measured values,  # noqa: E501
        # not to small counts and flags (1 doublet, probability 1.0 would make any 1,000 "traceable")  # noqa: E501
        if k == int(k) and abs(k) <= 10:
            continue
        for s in (1e3, 1e-3, 1e6, 1e-6, 100.0, 0.01):
            if abs(x - k * s) <= 0.001 * abs(k * s):  # a converted value keeps its digits
                return True
    return False


def _decimals_scale(x: float) -> int:
    """Rounding granularity implied by how x is written (0 -> integers)."""
    s = repr(x)
    return 0 if "." not in s or s.endswith(".0") else -len(s.split(".")[1])


_PCT_MARK = re.compile(
    r"\bP\d{2}\b|median|percentile|range|uncertaint|monte carlo|–|\bto\b|\bcover", re.I
)


def _exact(x: float, values) -> bool:
    return any(abs(x - v) < 0.006 for v in values)


def _percentile_check(text: str, ledger: FactLedger) -> list[dict]:
    """A Monte Carlo percentile quoted as if it were the design's own value (S1 deep: the P50
    LCOE of 46.2 presented as 'LCOE', the design's being 44.1). A number that is exactly a
    P10/P50/P90 of an uncertainty result, and not exactly any other recorded value, must be
    labelled as a percentile on its line."""
    pct, plain = {}, []
    for f in ledger.facts:
        for v, k in _numbers_with_keys(f.result):
            if re.search(r"\.P\d{2}$", k):
                pct.setdefault(v, (f.fid, k))
            else:
                plain.append(v)
    issues = []
    for line in text.splitlines():
        if _PCT_MARK.search(line):
            continue
        for m in NUM_RE.finditer(re.sub(r"\bF\d+\b", "", line)):
            x = _parse(m.group())
            if x in TRIVIAL or _exact(x, plain):
                continue
            hit = next(((v, fid, k) for v, (fid, k) in pct.items() if _exact(x, [v])), None)
            if hit is None and not _matches(x, plain):
                hit = next(((v, fid, k) for v, (fid, k) in pct.items() if _matches(x, [v])), None)
            if hit:
                v, fid, k = hit
                issues.append(
                    {
                        "type": "percentile",
                        "claim": line.strip()[:120],
                        "detail": f"{x:g} is the {k.split('.')[-1]} of the uncertainty analysis "
                        f"[{fid}] ({k.split('.')[0]}), not the design's value: label it as a "
                        "percentile or quote evaluate_design's number",
                    }
                )
                break
    return issues


def provenance_check(text: str, ledger: FactLedger) -> dict:
    """Numbers in ``text`` that are not traceable to the ledger or the brief."""
    raw = text
    text = re.sub(r"\bF\d+\b", "", text)  # fact IDs are citations, not claims
    text = re.sub(r"\b[0-9a-f]{10}\b", "", text)  # design IDs
    found = [_parse(m) for m in NUM_RE.findall(text)]
    known = ledger.known_numbers()
    unsupported = sorted({x for x in found if not _matches(x, known)})
    units = unit_check(text, ledger)
    claims = claim_check(raw, ledger)  # design IDs identify the design a claim is about
    claims += _percentile_check(raw, ledger)
    have = {f.fid for f in ledger.facts}
    claims += [  # a citation of a fact that does not exist is a fabricated source
        {
            "type": "citation",
            "claim": f"[{fid}]",
            "detail": f"no fact {fid} exists in this session (the ledger has {len(have)} facts)",
        }
        for fid in dict.fromkeys(re.findall(r"\bF\d+\b", raw))
        if fid not in have
    ]
    return {
        "numbers_checked": len(found),
        "unsupported": unsupported,
        "unit_mismatches": units,
        "claim_issues": claims,
        "traceable_pct": round(
            100 * (1 - len([x for x in found if x in unsupported]) / max(1, len(found))), 1
        ),
        "passed": not unsupported and not units and not claims,
    }


# --- claim check: comparisons and design attributes must agree with the numbers they rest on -------------  # noqa: E501

_METRIC_KEYS = {  # metric -> result fields that carry it
    "lcoe": ("lcoe_eur_per_mwh",),
    "co2": ("co2_t", "co2_t_per_year"),
    "share": ("geothermal_share_pct", "geothermal_share_of_heat_pct"),
    "capex": ("capex_meur",),
}
_METRIC_WORDS = [  # most specific first
    ("capex", r"capex|capital cost|investment"),
    ("lcoe", r"lcoe|levell?i[sz]ed cost(?: of \w+)?|cost of (?:energy|heat)|cost"),
    ("co2", r"co2|co₂|emissions?"),
    ("share", r"geothermal share|share"),
]
_PHRASES = [  # comparative phrases that name their metric implicitly
    (r"\bless expensive\b|\bcheaper\b|\bmore cost[- ]effective\b", "lower", "lcoe"),
    (r"\bmore expensive\b|\bcostlier\b|\bless cost[- ]effective\b", "higher", "lcoe"),
]
_DIR_RE = re.compile(
    r"\b(higher|greater|larger|more|lower|less|smaller|reduced|fewer)\s+((?:[\w-]+\s+){0,2}?)"
    r"(" + "|".join(w for _, w in _METRIC_WORDS) + r")\b",
    re.IGNORECASE,
)
_DEPTH_RE = re.compile(r"\b([1-5][,.]?\d{3})\s*(?:m\b|meters?\b|metres?\b)", re.IGNORECASE)
_THAN_RE = re.compile(r"\b(?:than|compared (?:to|with)|versus|vs\.?|relative to)\s", re.IGNORECASE)
_NEGATIONS = [  # (equipment, how a design label shows it, how an answer denies it)
    (
        "backup boiler",
        r"\bboiler\b",
        r"\b(?:no|without(?: an?)?)\s+(?:[\w-]+\s+)?(?:backup\s+)?boiler\b",
    ),
    ("heat pump", r"\bHP\s+[\d.]+\s*MW", r"\b(?:no|without(?: an?)?)\s+heat[- ]pumps?\b"),
    ("absorption chiller", r"\bAbsCh\b", r"\b(?:no|without(?: an?)?)\s+absorption\b"),
]
_LOWER = {"lower", "less", "smaller", "reduced", "fewer"}
_UNITS = {"lcoe": "EUR/MWh", "co2": "t/yr", "share": "%", "capex": "MEUR"}


def _designs(obj, out: dict | None = None) -> dict:
    """design_id -> {depth, hp_mw, lcoe, co2, share, capex} for every design summary in a tool "
    "result."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        label = obj.get("label")
        if isinstance(label, str) and any(k in obj for keys in _METRIC_KEYS.values() for k in keys):
            d = re.search(r"@\s*(\d+)\s*m\b", label)
            hp = re.search(r"\bHP\s*([\d.]+)\s*MW", label)
            rec = {
                "label": label,
                "depth": float(d.group(1)) if d else None,
                "hp_mw": float(hp.group(1)) if hp else 0.0,
            }
            for m, keys in _METRIC_KEYS.items():
                v = next((obj[k] for k in keys if isinstance(obj.get(k), (int, float))), None)
                if v is not None:
                    rec[m] = float(v)
            out.setdefault(obj.get("design_id") or label, rec)
        for v in obj.values():
            _designs(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _designs(v, out)
    return out


def _depths(text: str) -> list[float]:
    return [
        float(x) for x in dict.fromkeys(re.sub(r"[,.]", "", g) for g in _DEPTH_RE.findall(text))
    ]


_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def _colon(line: str) -> bool:
    return line.rstrip().rstrip("*_").endswith(":")


def _blocks(text: str) -> list[str]:
    """A top-level line plus its indented continuation lines (one bullet with its sub-bullets); a
    paragraph ending in ':' also owns the list that follows it ('the best 2500 m design is:' +
    KPIs).
    """
    blocks: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip():
            blocks.append([])
        elif line[:1].isspace() and blocks and blocks[-1]:
            blocks[-1].append(line)
        else:
            blocks.append([line])

    def opens_list(b: list[str]) -> bool:  # 'the best design is:' (+ the items it already owns)
        return _colon(b[-1]) or (_colon(b[0]) and all(_ITEM.match(x) for x in b[1:]))

    out: list[list[str]] = []
    for b in (b for b in blocks if b):
        # an item that is itself a header ('- **Designs at 3100 m:**') starts its own block
        if out and _ITEM.match(b[0]) and not _colon(b[0]) and opens_list(out[-1]):
            out[-1].extend(b)
        else:
            out.append(list(b))
    return ["\n".join(b) for b in out]


def _close(x: float, v: float) -> bool:
    return abs(x - v) <= max(0.051 * 10 ** _decimals_scale(x), 0.006 * abs(v))


def _fit(nums: list[float], r: dict) -> tuple[int, float]:
    """(metrics of design r quoted in nums, minus their summed relative error)."""
    n, err = 0, 0.0
    for m in _METRIC_KEYS:
        hits = [abs(x - r[m]) / max(abs(r[m]), 1e-9) for x in nums if m in r and _close(x, r[m])]
        if hits:
            n, err = n + 1, err + min(hits)
    return n, -err


def claim_check(text: str, ledger: "FactLedger") -> list[dict]:
    """Qualitative claims that contradict the recorded numbers.

    1. attribute: a block quotes the KPIs of a design but names a depth (or a heat pump) that design
       does not have -- e.g. a 3100 m design's numbers presented as 'the 2500 m option';
    2. comparison: 'X has lower LCOE than Y' where the values quoted for X and Y (or, if the answer
       quotes none, the cheapest recorded design at each depth) say the opposite.
    """
    designs: dict = {}
    for f in ledger.facts:
        _designs(f.result, designs)
    if not designs:
        return []
    text = re.sub(r"\*\*|__", "", text)
    issues, quoted = (
        [],
        {},
    )  # quoted: depth named in the answer -> metric values the answer gives for it
    for block in _blocks(text):
        nums = [_parse(m) for m in NUM_RE.findall(block)]
        score = {did: _fit(nums, r) for did, r in designs.items()}
        best = max(score.values())
        named = _depths(
            re.sub(r'"[^"\n]*"|`[^`\n]*`|\u201c[^\u201d\n]*\u201d', "", block)
        )  # not quoted labels
        if best[0] < 2 or not named:
            continue
        # near-twin designs (DH 100/45 vs 100/50) differ by 0.1 %: rank by match count, then by error  # noqa: E501
        match = [designs[d] for d, s in score.items() if s[0] == best[0] and s[1] >= best[1] - 1e-4]
        # a design with the named depth must be clearly beaten (2+ more matching KPIs): one
        # coincidence (a Monte Carlo percentile equal to another design's CO2) is not evidence
        named_best = max(
            (s[0] for d, s in score.items() if designs[d]["depth"] in named), default=0
        )
        if not any(r["depth"] in named for r in match) and best[0] - named_best >= 2:
            r = match[0]
            issues.append(
                {
                    "type": "attribute",
                    "claim": block.strip().splitlines()[0][:120],
                    "detail": f"the numbers quoted belong to '{r['label']}' ({r['depth']:.0f} m), "
                    f"not to a {'/'.join(f'{d:.0f}' for d in named)} m design",
                }
            )
        head = block.strip().splitlines()[0].lower()
        if re.search(r"\bwith (?:a |an )?heat pump", head) and all(r["hp_mw"] == 0 for r in match):
            issues.append(
                {
                    "type": "attribute",
                    "claim": head[:120],
                    "detail": f"the numbers quoted belong to '{match[0]['label']}', which has "
                    "no heat pump",
                }
            )
        if len(named) == 1:
            quoted.setdefault(named[0], {m: match[0][m] for m in _METRIC_KEYS if m in match[0]})
    cited = [
        designs[d] for d in dict.fromkeys(re.findall(r"\b[0-9a-f]{10}\b", text)) if d in designs
    ]
    for r in cited:  # "no backup boiler" about a design (cited by ID) that has one
        for unit, has, pat in _NEGATIONS:
            m = re.search(pat, text, re.IGNORECASE)
            if m and re.search(has, r["label"]):
                issues.append(
                    {
                        "type": "attribute",
                        "claim": m.group(0),
                        "detail": f"says no {unit}, but '{r['label']}' has one",
                    }
                )
    for sent in re.split(r"(?<=[.;!?])\s+|\n+", text):
        named = _depths(sent)
        if len(named) != 2:
            continue
        than = _THAN_RE.search(sent)
        comp = next(
            (
                d
                for d in named
                if than
                and _DEPTH_RE.search(sent, than.end())
                and float(re.sub(r"[,.]", "", _DEPTH_RE.search(sent, than.end()).group(1))) == d
            ),
            named[1],
        )
        subj = named[0] if comp == named[1] else named[1]
        claims, rest = [], sent
        for pat, direction, metric in _PHRASES:
            if re.search(pat, rest, re.IGNORECASE):
                claims.append((direction, metric))
                rest = re.sub(pat, " ", rest, flags=re.IGNORECASE)
        for m in _DIR_RE.finditer(rest):
            word = m.group(3).lower()
            metric = next(k for k, w in _METRIC_WORDS if re.fullmatch(w, word, re.IGNORECASE))
            claims.append(("lower" if m.group(1).lower() in _LOWER else "higher", metric))
        for direction, metric in claims:
            vals = []
            for depth in (subj, comp):
                v = quoted.get(depth, {}).get(metric)
                if (
                    v is None
                ):  # the answer quotes nothing for this depth: cheapest recorded design there
                    pool = [
                        r
                        for r in designs.values()
                        if r["depth"] == depth and metric in r and "lcoe" in r
                    ]
                    v = min(pool, key=lambda r: r["lcoe"])[metric] if pool else None
                vals.append(v)
            a, b = vals
            if a is None or b is None:
                continue
            if (direction == "lower" and a >= b) or (direction == "higher" and a <= b):
                issues.append(
                    {
                        "type": "comparison",
                        "claim": sent.strip()[:160],
                        "detail": f"says {subj:.0f} m has {direction} {metric} than {comp:.0f} m, "
                        f"but the values are {a:g} vs {b:g} {_UNITS[metric]}",
                    }
                )
    return issues
