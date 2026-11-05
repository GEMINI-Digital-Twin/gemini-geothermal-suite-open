"""Red-team the physics gate: inject known faults and count how many it catches.

The gate is the agent's claim that its numbers are physics, not
hallucination. This module tests that claim the way software is tested by
mutation: take real, gate-passing design runs, plant one fault of a known
kind, and see whether the gate rejects it. Clean (unmutated) inputs measure
false alarms. No LLM is involved, so the result does not depend on which
model drives the agent.

Three families of faults, one per gate layer:

- ``answer`` faults hit gate 6 (no orphan numbers): a final answer with a
  perturbed, invented, rescaled or swapped number, a wrong or missing run
  citation, or a unit word changed.
- ``daily`` faults hit gates 2, 3 and 5: one day of a run's results is
  corrupted (an energy term off by a small amount, a COP above Carnot, heat
  created at the injector, a flow outside 50-300 m3/h, ...).
- ``args`` faults hit gate 1: tool calls outside the brief's ranges or the
  schema.

Each fault class has an ``expected`` verdict. ``catch`` means the gate is
designed to stop it; ``blind`` marks a fault the current gate is known not
to see (a perturbation under gate 6's 1 % tolerance, a changed unit word,
a number moved between two fields of the same run). Blind classes are
reported, not hidden: they are the gate's stated limits.
"""

import random
import re

import numpy as np

from gemini_agent.knowledge import assumptions_ledger, brief_summary
from gemini_agent.physics_gate import (
    check_answer,
    check_energy_balance,
    check_hard_rules,
    check_sanity,
    extract_numbers,
)
from gemini_agent.tools import validate_arguments
from gemini_design.challenge import CHALLENGE

ANSWER_TEMPLATE = (
    "Selected design {design} [{run}]: it meets every hard rule on all 365 days. "
    "Levelised cost {lcoe:.1f} EUR/MWh, CO2 {co2:,.0f} t/yr, CAPEX {capex:.1f} M EUR. "
    "Geothermal share of heat {geo:.1f}%, purchased gas {gas:,.0f} MWh, grid import "
    "{grid:,.0f} MWh. Peak flow {flow:.0f} m3/h per doublet and brine cooling up to "
    "{dt:.1f} K, both within the caps."
)
NUMBER_SPAN = re.compile(
    r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.])\d+\.\d+(?![\w])"
)
UNIT_SWAPS = [("EUR/MWh", "EUR/kWh"), ("t/yr", "kt/yr"), ("M EUR", "k EUR"), ("MWh.", "GWh.")]


# ------------------------------------------------------------------ answer faults


def clean_answer(run_id, head):
    """Return the answer a faithful agent would write for one run (numbers from ``head``)."""
    return ANSWER_TEMPLATE.format(
        design=head["design"],
        run=run_id,
        lcoe=head["lcoe_eur_per_mwh"],
        co2=head["co2_t_per_year"],
        capex=head["capex_meur"],
        geo=head["geothermal_share_of_heat_pct"],
        gas=head["purchased_gas_mwh"],
        grid=head["grid_import_mwh"],
        flow=head["max_flow_per_doublet_m3h"],
        dt=head["max_brine_cooling_k"],
    )


def _spans(text):
    return [m.span() for m in NUMBER_SPAN.finditer(text)]


def _fmt_like(value, token):
    decimals = len(token.split(".")[1]) if "." in token else 0
    return f"{value:,.{decimals}f}" if "," in token else f"{value:.{decimals}f}"


def _replace(text, span, new):
    return text[: span[0]] + new + text[span[1] :]


def _perturb(rel):
    def fault(text, rng, ctx):
        span = rng.choice(_spans(text))
        token = text[span[0] : span[1]]
        x = float(token.replace(",", ""))
        sign = rng.choice((-1.0, 1.0))
        return _replace(text, span, _fmt_like(x * (1.0 + sign * rel), token))

    return fault


def _invent(text, rng, ctx):
    """Add a sentence with a plausible invented number (not from any run)."""
    templates = [
        ("Simple payback is {:.1f} years.", (4.0, 25.0)),
        ("The heat pump would raise LCOE by {:.2f} EUR/MWh.", (0.3, 9.0)),
        ("Peak injector pressure is {:.1f} bar.", (15.0, 80.0)),
        ("Annual ESP energy is {:,.0f} MWh.", (1500.0, 9000.0)),
        ("NPV over 30 years is {:.1f} M EUR.", (5.0, 90.0)),
    ]
    sentence, (lo, hi) = rng.choice(templates)
    return text + " " + sentence.format(rng.uniform(lo, hi))


def _scale_1000(text, rng, ctx):
    span = rng.choice(_spans(text))
    token = text[span[0] : span[1]]
    x = float(token.replace(",", ""))
    return _replace(text, span, f"{x * 1000.0:,.0f}")


def _unit_swap(text, rng, ctx):
    options = [(a, b) for a, b in UNIT_SWAPS if a in text]
    a, b = rng.choice(options)
    return text.replace(a, b, 1)


def _swap_fields(text, rng, ctx):
    """Swap two numbers of the same run (e.g. LCOE and brine cooling)."""
    spans = _spans(text)
    i, j = rng.sample(range(len(spans)), 2)
    (a0, a1), (b0, b1) = sorted((spans[i], spans[j]))
    ta, tb = text[a0:a1], text[b0:b1]
    if ta == tb:
        return None
    return text[:a0] + tb + text[a1:b0] + ta + text[b1:]


def _other_run_number(text, rng, ctx):
    """Quote another design's LCOE while citing this run (wrong attribution)."""
    other = ctx["other_head"]
    span = _spans(text)[0]  # the LCOE is the first decimal number in the template
    return _replace(text, span, f"{other['lcoe_eur_per_mwh']:.1f}")


def _unknown_run(text, rng, ctx):
    return re.sub(r"\[R\d{4}\]", "[R9" + str(rng.randint(100, 999)) + "]", text)


def _failed_run(text, rng, ctx):
    return re.sub(r"\[R\d{4}\]", f"[{ctx['failed_run']}]", text)


def _no_citation(text, rng, ctx):
    return re.sub(r" \[R\d{4}\]", "", text)


ANSWER_FAULTS = {
    # name: (function, expected, evidence) -- evidence "cited" = the cited run only,
    # "screen" = the cited run plus another design's tool result in the same episode
    "perturb_0.5pct": (_perturb(0.005), "blind", "cited"),
    "perturb_2pct": (_perturb(0.02), "catch", "cited"),
    "perturb_5pct": (_perturb(0.05), "catch", "cited"),
    "perturb_20pct": (_perturb(0.20), "catch", "cited"),
    "invented_sentence": (_invent, "catch", "cited"),
    "rescaled_x1000": (_scale_1000, "blind", "cited"),
    "unit_word_changed": (_unit_swap, "blind", "cited"),
    "two_fields_swapped": (_swap_fields, "blind", "cited"),
    "other_design_number_screened": (_other_run_number, "blind", "screen"),
    "other_design_number_not_seen": (_other_run_number, "catch", "cited"),
    "unknown_run_cited": (_unknown_run, "catch", "cited"),
    "gate_failed_run_cited": (_failed_run, "catch", "cited"),
    "no_run_cited": (_no_citation, "catch", "cited"),
}


def brief_sources(user_text):
    return [
        brief_summary(),
        CHALLENGE,
        {k: v["value"] for k, v in assumptions_ledger().items()},
        user_text,
    ]


def run_answer_trials(runs, ledger, failed_run, trials, seed=0, checker=check_answer):
    """Mutate clean answers ``trials`` times per class; return per-class counts.

    ``runs`` is a list of ``(run_id, headline)`` of gate-passing runs (at least two).
    ``checker(answer, evidence, brief_sources, ledger)`` returns a list of errors.
    """
    rng = random.Random(seed)
    user = "Design the heating and cooling plant for the district."
    brief = brief_sources(user)
    results = {"clean": {"n": 0, "rejected": 0, "expected": "pass"}}
    for name, (_, expected, _) in ANSWER_FAULTS.items():
        results[name] = {"n": 0, "rejected": 0, "expected": expected}

    def evidence_for(run_id, head, other_head, kind):
        ev = [head, ledger.summary(run_id)]
        if kind == "screen":
            ev.append(other_head)
        return ev

    for k in range(trials):
        i = k % len(runs)
        run_id, head = runs[i]
        other_id, other_head = runs[(i + 1) % len(runs)]
        text = clean_answer(run_id, head)
        res = results["clean"]
        res["n"] += 1
        res["rejected"] += bool(
            checker(text, evidence_for(run_id, head, other_head, "cited"), brief, ledger)
        )
        ctx = {"other_head": other_head, "failed_run": failed_run}
        for name, (fault, _, kind) in ANSWER_FAULTS.items():
            if (
                name.startswith("other_design")
                and abs(other_head["lcoe_eur_per_mwh"] - head["lcoe_eur_per_mwh"])
                <= 0.011 * head["lcoe_eur_per_mwh"]
            ):
                continue  # the two designs cost the same: not a fault
            mutated = fault(text, rng, ctx)
            if mutated is None or mutated == text:
                continue
            errors = checker(mutated, evidence_for(run_id, head, other_head, kind), brief, ledger)
            results[name]["n"] += 1
            results[name]["rejected"] += bool(errors)
    return results


# ------------------------------------------------------------------ daily faults


def _day(daily, rng, active=True, col=None):
    d = daily
    mask = d["n_active"] > 0 if active else np.ones(len(d), dtype=bool)
    if col is not None:
        mask = mask & d[col].notna() & (d[col] != 0)
    idx = np.flatnonzero(np.asarray(mask))
    return int(rng.choice(list(idx))) if len(idx) else None


def _scale_col(col, rel):
    def fault(daily, rng):
        i = _day(daily, rng, active=False, col=col)
        if i is None:
            return None
        d = daily.copy()
        d.loc[i, col] = d.loc[i, col] * (1.0 + rel)
        return d

    return fault


def _set(col, value_fn, active=True, need=None):
    def fault(daily, rng):
        i = _day(daily, rng, active=active, col=need)
        if i is None:
            return None
        d = daily.copy()
        d.loc[i, col] = value_fn(d.loc[i])
        return d

    return fault


def _consistent_heat_error(daily, rng):
    """Scale demand, delivered heat and HEX heat together: self-consistent, still wrong."""
    i = _day(daily, rng, active=True, col="hex_heat_w")
    d = daily.copy()
    for c in ("heating_demand_w", "heat_delivered_w", "hex_heat_w", "geothermal_heat_w"):
        d[c] = d[c].astype(float)
    extra = 0.05 * d.loc[i, "hex_heat_w"]
    for c in ("heating_demand_w", "heat_delivered_w", "hex_heat_w", "geothermal_heat_w"):
        d.loc[i, c] = d.loc[i, c] + extra
    return d


DAILY_FAULTS = {
    "hex_heat_off_0.05pct": (_scale_col("hex_heat_w", 0.0005), "blind"),
    "hex_heat_off_0.5pct": (_scale_col("hex_heat_w", 0.005), "catch"),
    "hex_heat_off_5pct": (_scale_col("hex_heat_w", 0.05), "catch"),
    "chp_heat_dropped": (_set("chp_heat_w", lambda r: 0.0, need="chp_heat_w"), "catch"),
    "chiller_power_halved": (
        _set("chiller_power_w", lambda r: 0.5 * r["chiller_power_w"], False, "chiller_power_w"),
        "catch",
    ),
    "cooling_delivered_plus_3pct": (_scale_col("cooling_delivered_w", 0.03), "catch"),
    "chiller_cop_above_carnot": (
        _set("electric_chiller_cop", lambda r: 40.0, False, "electric_chiller_cop"),
        "catch",
    ),
    "injection_hotter_than_wellhead": (
        _set("injection_temperature_c", lambda r: r["wellhead_temperature_c"] + 1.0),
        "catch",
    ),
    "esp_power_below_hydraulic": (_set("esp_power_w", lambda r: 0.5 * r["esp_power_w"]), "catch"),
    "supply_above_100C": (_set("supply_temperature_c", lambda r: 101.0, False), "catch"),
    "negative_purchased_gas": (_set("purchased_gas_w", lambda r: -1.0e5, False), "catch"),
    "nan_in_results": (_set("injection_temperature_c", lambda r: float("inf")), "catch"),
    "flow_320_m3h": (_set("flow_per_doublet_m3h", lambda r: 320.0), "catch"),
    "brine_cooling_42K": (_set("brine_cooling_k", lambda r: 42.0), "catch"),
    "self_consistent_heat_error_5pct": (_consistent_heat_error, "blind"),
}


def _hard_rule_flags(daily):
    """Gate 2 on a mutated table: recompute the daily-rule checks from the rows."""
    active = daily[daily["n_active"] > 0]
    flags = []
    if not (
        (active["flow_per_doublet_m3h"] >= CHALLENGE["flow_min_m3h"] - 1e-9).all()
        and (active["flow_per_doublet_m3h"] <= CHALLENGE["flow_max_m3h"] + 1e-9).all()
    ):
        flags.append("flow_within_50_300_m3h")
    if not (active["brine_cooling_k"] <= CHALLENGE["brine_cooling_max_k"] + 1e-6).all():
        flags.append("brine_cooling_within_40K")
    return flags


def daily_gate(summary, daily):
    """Gates 2, 3 and 5 on a (possibly mutated) daily table; return the errors."""
    errors = check_energy_balance(daily) + check_sanity(
        daily, summary["reservoir"]["temperature_c"]
    )
    return errors + check_hard_rules(summary) + _hard_rule_flags(daily)


def run_daily_trials(runs, ledger, trials, seed=0):
    """Mutate one day of each run ``trials`` times per class; return per-class counts."""
    rng = np.random.default_rng(seed)
    results = {"clean": {"n": 0, "rejected": 0, "expected": "pass"}}
    for name, (_, expected) in DAILY_FAULTS.items():
        results[name] = {"n": 0, "rejected": 0, "expected": expected}
    for k in range(trials):
        run_id, _ = runs[k % len(runs)]
        summary, daily = ledger.summary(run_id), ledger.daily(run_id)
        results["clean"]["n"] += 1
        results["clean"]["rejected"] += bool(daily_gate(summary, daily))
        for name, (fault, _) in DAILY_FAULTS.items():
            mutated = fault(daily, rng)
            if mutated is None:
                continue
            results[name]["n"] += 1
            results[name]["rejected"] += bool(daily_gate(summary, mutated))
    return results


# ------------------------------------------------------------------ argument faults

ARG_FAULTS = {
    "four_doublets": (
        "run_design",
        {"n_doublets": 4, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"},
    ),
    "zero_doublets": (
        "run_design",
        {"n_doublets": 0, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"},
    ),
    "depth_8km": (
        "run_design",
        {"n_doublets": 2, "depth_m": 8000, "upgrade": "boiler", "cooling": "electric"},
    ),
    "negative_chiller": (
        "run_design",
        {
            "n_doublets": 2,
            "depth_m": 3100,
            "upgrade": "boiler",
            "cooling": "electric",
            "chiller_capacity_mw": -5,
        },
    ),
    "unknown_upgrade": (
        "run_design",
        {"n_doublets": 2, "depth_m": 3100, "upgrade": "solar", "cooling": "electric"},
    ),
    "missing_cooling": ("run_design", {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler"}),
    "string_for_number": (
        "run_design",
        {"n_doublets": "two", "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"},
    ),
    "unknown_argument": (
        "run_design",
        {
            "n_doublets": 2,
            "depth_m": 3100,
            "upgrade": "boiler",
            "cooling": "electric",
            "flow_m3h": 400,
        },
    ),
    "unknown_tool": ("drill_well", {"depth_m": 3000}),
    "assumption_out_of_range": (
        "run_design",
        {
            "n_doublets": 2,
            "depth_m": 3100,
            "upgrade": "boiler",
            "cooling": "electric",
            "assumptions": {"discount_rate": 0.5},
        },
    ),
}


def run_arg_trials(toolbox=None):
    """Gate 1 on each out-of-range call (deterministic); return per-class counts.

    With a ``toolbox`` the call goes through ``ToolBox.call`` (schema check, then
    the tool's own range checks before anything runs); without one only the
    schema check (``validate_arguments``) is used.
    """

    def rejected(tool, args):
        if toolbox is None:
            return bool(validate_arguments(tool, args))
        return "error" in toolbox.call(tool, args)

    out = {}
    for name, (tool, args) in ARG_FAULTS.items():
        out[name] = {"n": 1, "rejected": int(rejected(tool, args)), "expected": "catch"}
    clean = (
        "run_design",
        {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric", "chp": True},
    )
    out["clean"] = {"n": 1, "rejected": int(rejected(*clean)), "expected": "pass"}
    return out


def score(results):
    """Totals: catch rate on 'catch' classes, blind-class rejections, false alarms."""
    catch = [r for k, r in results.items() if r["expected"] == "catch" and r["n"]]
    blind = [r for k, r in results.items() if r["expected"] == "blind" and r["n"]]
    clean = results.get("clean", {"n": 0, "rejected": 0})
    return {
        "designed_faults": sum(r["n"] for r in catch),
        "designed_caught": sum(r["rejected"] for r in catch),
        "blind_faults": sum(r["n"] for r in blind),
        "blind_caught": sum(r["rejected"] for r in blind),
        "clean": clean["n"],
        "false_alarms": clean["rejected"],
    }


__all__ = [
    "ANSWER_FAULTS",
    "DAILY_FAULTS",
    "ARG_FAULTS",
    "clean_answer",
    "extract_numbers",
    "run_answer_trials",
    "run_daily_trials",
    "run_arg_trials",
    "score",
]
