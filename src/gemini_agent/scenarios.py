"""Demo questions for the report appendix, with a scripted policy for offline runs.

Each scenario is a list of user turns. When the agent asks a question,
the next canned turn answers it. The same scenarios run against a live
LLM (``run_agent_transcripts.py --backend live``); the scripted policy
only exists so the tools, physics gate, memory and logging can be shown
and tested without a model server. Scripted transcripts are labelled as
such and must not be presented as LLM output.
"""

import json

DRY_COOLER_CODE = '''"""Dry cooler (air-cooled heat rejection) for the chiller condenser circuit."""

import math

from gemini_model.model_abstract import StaticModel


class DryCooler(StaticModel):
    """Water-to-air dry cooler: NTU-effectiveness with the water side as C_min.

    Parameters: ``ua`` (W/K), ``fan_power_fraction`` (fan power / heat rejected),
    ``water_density`` (kg/m3), ``water_cp`` (J/kg/K).
    Inputs: ``water_temperature_in`` (degC), ``water_flow_rate`` (m3/s),
    ``air_temperature`` (degC). Outputs: ``heat_rejected`` (W),
    ``water_temperature_out`` (degC), ``fan_power`` (W), ``effectiveness``.
    """

    def __init__(self):
        """Defaults for a 10 MW unit."""
        super().__init__()
        self.parameters = {
            "ua": 1.5e6,
            "fan_power_fraction": 0.02,
            "water_density": 1000.0,
            "water_cp": 4186.0,
        }

    def calculate_output(self, u, x=None):
        """Heat rejected to air; zero when the water is not warmer than the air."""
        p = self.parameters
        c_water = p["water_density"] * p["water_cp"] * u["water_flow_rate"]
        if c_water <= 0 or u["water_temperature_in"] <= u["air_temperature"]:
            eff, q = 0.0, 0.0
        else:
            eff = 1.0 - math.exp(-p["ua"] / c_water)
            q = eff * c_water * (u["water_temperature_in"] - u["air_temperature"])
        t_out = u["water_temperature_in"] - (q / c_water if c_water > 0 else 0.0)
        self.output = {
            "heat_rejected": q,
            "water_temperature_out": t_out,
            "fan_power": p["fan_power_fraction"] * q,
            "effectiveness": eff,
        }
'''

DRY_COOLER_TESTS = """from dry_cooler import DryCooler


def run(t_in, flow, air):
    m = DryCooler()
    m.calculate_output(
        {"water_temperature_in": t_in, "water_flow_rate": flow, "air_temperature": air}
    )
    return m.get_output()


def test_energy_balance():
    out = run(38.0, 0.3, 25.0)
    c = 1000.0 * 4186.0 * 0.3
    assert abs(out["heat_rejected"] - c * (38.0 - out["water_temperature_out"])) < 1e-6


def test_outlet_between_air_and_inlet():
    out = run(38.0, 0.3, 25.0)
    assert 25.0 < out["water_temperature_out"] < 38.0
    assert 0.0 < out["effectiveness"] < 1.0


def test_no_heat_when_air_is_hotter():
    out = run(30.0, 0.3, 32.0)
    assert out["heat_rejected"] == 0.0
    assert out["water_temperature_out"] == 30.0
"""

THERMAL_STORAGE_CODE = '''"""Seasonal hot-water heat store (pit or tank), one day per call."""

from gemini_model.model_abstract import StaticModel

HOURS_PER_DAY = 24.0


class ThermalStorage(StaticModel):
    """Hot-water heat store with a power rating and a standing loss.

    The state of charge is passed in and returned, so the model itself has
    no hidden state and one call is one 24 h day: standing loss on the
    starting energy first, then charge or discharge, each limited by the
    power rating, the free room and the energy left.

    Parameters: ``capacity_mwh``, ``power_mw``, ``loss_fraction_per_day``.
    Inputs: ``soc_mwh``, ``charge_request_mw``, ``discharge_request_mw``.
    Outputs: ``soc_mwh``, ``charge_mw``, ``discharge_mw``, ``loss_mwh``.
    """

    def __init__(self):
        """Defaults for a 10 GWh pit store with a 10 MW rating."""
        super().__init__()
        self.parameters = {
            "capacity_mwh": 10000.0,
            "power_mw": 10.0,
            "loss_fraction_per_day": 0.001,
        }

    def calculate_output(self, u, x=None):
        """Step one day; never exceed capacity, power or the energy stored."""
        p = self.parameters
        cap, power = p["capacity_mwh"], p["power_mw"]
        soc = min(max(u["soc_mwh"], 0.0), cap)
        loss = soc * p["loss_fraction_per_day"]
        soc -= loss
        charge = min(max(u["charge_request_mw"], 0.0), power, (cap - soc) / HOURS_PER_DAY)
        discharge = min(max(u["discharge_request_mw"], 0.0), power, soc / HOURS_PER_DAY)
        if charge > 0 and discharge > 0:  # one direction per day: keep the larger request
            if u["charge_request_mw"] >= u["discharge_request_mw"]:
                discharge = 0.0
            else:
                charge = 0.0
        soc += HOURS_PER_DAY * (charge - discharge)
        self.output = {
            "soc_mwh": soc,
            "charge_mw": charge,
            "discharge_mw": discharge,
            "loss_mwh": loss,
        }
'''

THERMAL_STORAGE_TESTS = """from thermal_storage import ThermalStorage


def step(soc, charge=0.0, discharge=0.0, **params):
    m = ThermalStorage()
    m.update_parameters(params)
    m.calculate_output(
        {"soc_mwh": soc, "charge_request_mw": charge, "discharge_request_mw": discharge}
    )
    return m.get_output()


def test_energy_balance():
    out = step(4000.0, charge=8.0)
    assert abs(4000.0 + 24.0 * (out["charge_mw"] - out["discharge_mw"]) - out["loss_mwh"]
               - out["soc_mwh"]) < 1e-9


def test_power_limit():
    out = step(5000.0, discharge=50.0, power_mw=10.0)
    assert out["discharge_mw"] == 10.0


def test_never_overfills_or_goes_negative():
    full = step(9990.0, charge=10.0)
    assert full["soc_mwh"] <= 10000.0 + 1e-9
    empty = step(20.0, discharge=10.0)
    assert empty["soc_mwh"] >= 0.0
    assert empty["discharge_mw"] < 10.0


def test_standing_loss():
    out = step(1000.0, loss_fraction_per_day=0.01)
    assert abs(out["loss_mwh"] - 10.0) < 1e-9
    assert abs(out["soc_mwh"] - 990.0) < 1e-9
"""

SCENARIOS = {
    "01_design_brief_incomplete": {
        "title": "Open design request with missing inputs (agent asks first)",
        "expect": {
            "first_reply": "question",
            "tools_any": ["screen", "run_design"],
            "final": "answer",
        },
        "turns": [
            "Design me a heating and cooling system for the district.",
            "I don't know the real return temperatures, go ahead with your defaults.",
        ],
    },
    "02_offtopic_weather": {
        "title": "Irrelevant question",
        "expect": {"no_tools": True, "final": "answer"},
        "turns": ["What's the weather in Delft tomorrow?"],
    },
    "03_incomplete_whatif": {
        "title": "Incomplete what-if question (which value?)",
        "expect": {
            "first_reply": "question",
            "tools_any": ["sensitivity", "run_design"],
            "final": "answer",
        },
        "turns": [
            "What happens to the cost if the heating return temperature is different?",
            "Try 50 degC.",
        ],
    },
    "04_hallucination_caught": {
        "title": "Physics gate rejects an invented number, agent corrects itself",
        "expect": {"tools_any": ["run_design", "screen"], "final": "answer"},
        "turns": ["Is the two-doublet boiler design cheaper than heating with gas only?"],
    },
    "05_uncertainty_permeability": {
        "title": "Subsurface uncertainty (bonus)",
        "expect": {"tools_any": ["sensitivity"], "final": "answer"},
        "turns": ["How robust is the two-doublet 3.1 km design if permeability is lower?"],
    },
    "06_write_missing_model": {
        "title": "Agent writes a missing model (dry cooler) with tests",
        "expect": {"model_written": True, "final": "answer"},
        "turns": [
            "GEMINI has no dry cooler model. Add one so we can check chiller heat rejection."
        ],
    },
    "07_invalid_tool_call": {
        "title": "Out-of-range request caught by gate 1",
        "expect": {"final": "answer"},
        "turns": ["Run four doublets at 3.1 km with a boiler and electric chillers."],
    },
    "09_explore_ambitious": {
        "title": "Agent explores more ambitious designs against the pick, writes the storage "
        "model one of them needs, and records why each is accepted or rejected",
        "expect": {
            "tools_all": ["run_design", "compare_runs", "log_option", "write_model"],
            "model_written": True,
            "final": "answer",
        },
        "turns": [
            "Our pick is two doublets at 3.1 km with a boiler, a 12 MW electric chiller and a "
            "CHP. Would something more ambitious do better? Try a heat pump, absorption "
            "cooling, three doublets and deeper wells, and record why you keep or drop each.",
            "Now try one doublet with seasonal heat storage instead of the second doublet.",
            "So, would a more ambitious design score better than our pick?",
        ],
    },
    "10_design_with_objective": {
        "title": "Open design with the client's objective stated: cost, CO2 and resilience",
        "live_only": True,  # no scripted policy: this one tests what a real model decides
        "expect": {"tools_any": ["screen", "run_design"], "final": "answer"},
        "turns": [
            "Design the heating and cooling plant for the district. We want the lowest cost, "
            "but CO2 matters to us: count it at 100 EUR per tonne when you weigh options, on "
            "top of the 80 already in the cost. Cost the plant on a normal year; separately, it "
            "must still meet demand if the geothermal wells trip on the coldest days. Use the "
            "measured weather."
        ],
    },
    "08_memory_recall": {
        "title": "Memory across questions",
        "expect": {"tools_any": ["memory_read"], "final": "answer"},
        "turns": ["What have we decided so far, and which runs back it up?"],
    },
}


def check_behaviour(scenario, replies, events):
    """Return a list of failed expectations for a finished scenario (empty = pass).

    ``replies`` are the AgentReply objects in order; ``events`` the transcript events.
    """
    expect = SCENARIOS[scenario].get("expect", {})
    tools = [e for e in events if e["kind"] == "tool"]
    names = {e["name"] for e in tools}
    failed = []
    if "first_reply" in expect and replies and replies[0].kind != expect["first_reply"]:
        failed.append(f"first reply should be a {expect['first_reply']}, was {replies[0].kind}")
    if "final" in expect and replies and replies[-1].kind != expect["final"]:
        failed.append(f"final reply should be an {expect['final']}, was {replies[-1].kind}")
    if expect.get("no_tools") and tools:
        failed.append(f"should not call tools, called {sorted(names)}")
    if "tools_all" in expect and not set(expect["tools_all"]) <= names:
        failed.append(f"should call all of {expect['tools_all']}")
    if "tools_any" in expect and not names & set(expect["tools_any"]):
        failed.append(f"should call one of {expect['tools_any']}")
    if expect.get("model_written") and not any(
        e["name"] == "write_model" and '"ok":true' in e["result_preview"] for e in tools
    ):
        failed.append("no model passed its tests and was registered")
    return failed


# ------------------------------------------------------------ scripted policy helpers


def _tool_results(messages, name):
    out = []
    for m in messages:
        if m["role"] == "tool" and m.get("name") == name:
            out.append(json.loads(m["content"]))
    return out


def _last(messages, name):
    results = _tool_results(messages, name)
    return results[-1] if results else None


def _call(tool, **args):
    return {"tool_calls": [(tool, args)]}


def _think(reasoning, tool, **args):
    return {"content": reasoning, "tool_calls": [(tool, args)]}


def _fmt(x, nd=1):
    return f"{x:,.{nd}f}"


def _design_answer(messages):
    screen = _last(messages, "screen")
    check = _last(messages, "cross_check")
    best = screen["best_by_lcoe"][0]
    low = screen["lowest_co2"]
    text = (
        f"I screened {screen['designs_run']} designs; {screen['meet_all_rules']} designs meet "
        f"every hard rule and every day of demand. Cheapest: {best['design']} at "
        f"{_fmt(best['lcoe_eur_per_mwh'])} EUR/MWh with {_fmt(best['co2_t_per_year'], 0)} t "
        f"CO2 per year and {_fmt(best['geothermal_share_of_heat_pct'])} % of heat from "
        f"geothermal [{best['run_id']}]. "
    )
    if low and low["run_id"] != best["run_id"]:
        text += (
            f"Lowest CO2: {low['design']} at {_fmt(low['co2_t_per_year'], 0)} t per year "
            f"and {_fmt(low['lcoe_eur_per_mwh'])} EUR/MWh [{low['run_id']}]. "
        )
    agree = "agrees" if check.get("agrees") else "does not agree"
    text += (
        f"GEMINI's own Solver re-run of the peak day ({check['date']}) {agree} with the "
        f"dispatcher (supply {_fmt(check['solver_supply_temperature_c'])} degC). "
        "Assumed: heating return 40 degC, cooling return 26 degC, NL 2027 prices."
    )
    return {"content": text}


def _whatif_answer(messages):
    base = _tool_results(messages, "run_design")[-1]
    sens = _last(messages, "sensitivity")
    row = sens["rows"][0]
    return {
        "content": (
            f"With a 50 degC heating return, {base['design']} still meets all demand "
            f"(meets all rules: {row['meets_all_hard_rules']}). LCOE goes from "
            f"{_fmt(base['lcoe_eur_per_mwh'], 2)} to {_fmt(row['lcoe_eur_per_mwh'], 2)} EUR/MWh "
            f"and purchased gas from {_fmt(base['purchased_gas_mwh'], 0)} to "
            f"{_fmt(row['purchased_gas_mwh'], 0)} MWh per year [{base['run_id']}, "
            f"{row['run_id']}]. A warmer return leaves less room to cool the brine, so a "
            "little more boiler heat is needed."
        )
    }


def _gas_only_wrong(messages):
    r = _last(messages, "run_design")
    return {
        "content": (
            f"Yes. The two-doublet design costs {_fmt(r['lcoe_eur_per_mwh'])} EUR/MWh "
            f"[{r['run_id']}], while a gas-only plant would cost about 55 EUR/MWh."
        )
    }


def _gas_only_fixed(messages):
    r = _last(messages, "run_design")
    return {
        "content": (
            f"The two-doublet boiler design costs {_fmt(r['lcoe_eur_per_mwh'])} EUR/MWh and "
            f"buys only {_fmt(r['purchased_gas_mwh'], 0)} MWh of gas per year, with "
            f"{_fmt(r['geothermal_share_of_heat_pct'])} % of heat from geothermal "
            f"[{r['run_id']}]. I have no gas-only reference run, so I can not give its cost "
            "without inventing a number; a boiler-only plant model would be needed to compare."
        )
    }


def _perm_answer(messages):
    s = _last(messages, "sensitivity")
    parts = [
        f"{row['permeability_md']:.0f} mD: {_fmt(row['lcoe_eur_per_mwh'])} EUR/MWh, "
        f"meets all rules {row['meets_all_hard_rules']} [{row['run_id']}]"
        for row in s["rows"]
    ]
    return {
        "content": f"{s['design']} across permeability: "
        + "; ".join(parts)
        + ". Lower permeability means more drawdown and ESP power, so cost rises."
    }


def _model_answer(messages):
    r = _last(messages, "write_model")
    if not r.get("ok"):
        return {"content": "The dry cooler model failed its tests, so I did not register it."}
    return {
        "content": (
            f"Added a dry cooler model ({r['class']}), registered as '{r['registered_as']}'. "
            f"Its tests pass ({r['pytest']}): energy balance, outlet between air and inlet "
            "temperature, and no heat rejection when the air is hotter than the water. The "
            f"harness acceptance tests also pass ({r['harness_tests']}). It can now be wired "
            "after the electric chiller condenser in a project JSON."
        )
    }


def _invalid_answer(messages):
    r = _last(messages, "run_design")
    return {
        "content": (
            "The brief allows at most 3 doublets, so I ran the largest allowed plant instead: "
            f"{r['design']} costs {_fmt(r['lcoe_eur_per_mwh'])} EUR/MWh and meets all rules: "
            f"{r['meets_all_hard_rules']} [{r['run_id']}]."
        )
    }


def _memory_answer(messages):
    # Notes are prose the agent wrote earlier: gate 6 does not take their numbers as
    # evidence, so quote what was decided and point to the runs for the numbers.
    mem = _last(messages, "memory_read")
    notes = (
        "; ".join(n["text"].split(" Trade-off:")[0].rstrip(".") for n in mem["notes"])
        or "nothing yet"
    )
    runs = ", ".join(r["run_id"] for r in mem["recent_runs"] if r.get("valid"))
    return {
        "content": f"Decisions and notes so far: {notes}. Valid recent runs: {runs}. They are "
        "not all on the same basis (the last ones vary an assumption in a sensitivity), so "
        "the numbers of each are in its run."
    }


PICK = {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"}
PICK_CHP = {**PICK, "chp": True, "chiller_capacity_mw": 12}

# (label, run_design arguments, what the scripted policy expects to learn from it)
AMBITIOUS_OPTIONS = [
    (
        "heat pump instead of boiler",
        {**PICK_CHP, "upgrade": "heat_pump"},
        "a 3.1 km well already gives brine hot enough for the HEX, so the heat pump adds "
        "CAPEX and has little left to lift",
    ),
    (
        "absorption cooling",
        {**PICK_CHP, "cooling": "absorption"},
        "brine-driven cooling cuts grid power but takes heat the boiler then replaces",
    ),
    (
        "three doublets",
        {**PICK_CHP, "n_doublets": 3},
        "a third doublet is idle most of the year, and its gas adds CO2",
    ),
    (
        "deeper wells (3.4 km)",
        {**PICK_CHP, "depth_m": 3400},
        "hotter brine almost removes purchased gas, but the extra drilling costs more than "
        "it saves",
    ),
    (
        "deep wells with absorption (4 km)",
        {**PICK_CHP, "depth_m": 4000, "cooling": "absorption"},
        "hotter brine drives the absorption chiller better, yet the drilling dominates",
    ),
    (
        "shallow wells with a heat pump (2.5 km)",
        {**PICK_CHP, "depth_m": 2500, "upgrade": "heat_pump"},
        "the organisers' trade-off: cheaper wells, but the heat pump and its power cost more",
    ),
    (
        "everything at once (3 doublets, 4 km, heat pump, absorption)",
        {
            **PICK_CHP,
            "n_doublets": 3,
            "depth_m": 4000,
            "upgrade": "heat_pump",
            "cooling": "absorption",
        },
        "the most ambitious plant on paper",
    ),
]

STORAGE_OPTIONS = [
    (
        "one doublet + 20 GWh seasonal store",
        {**PICK_CHP, "n_doublets": 1, "storage_mwh": 20000, "storage_mw": 12},
        "summer geothermal heat is kept for winter instead of drilling a second doublet",
    ),
    (
        "one doublet + 25 GWh seasonal store",
        {**PICK_CHP, "n_doublets": 1, "storage_mwh": 25000, "storage_mw": 12},
        "a store large enough to stop buying gas",
    ),
]


def _baseline(messages):
    """First successful run of the question (the pick; failed runs have no run id)."""
    return next(r for r in _tool_results(messages, "run_design") if "run_id" in r)


def _scripted_verdict(cmp):
    """Return the scripted stand-in's verdict (a live LLM decides for itself)."""
    pareto = cmp["pareto"]
    if pareto.startswith("dominates"):
        return "accept"
    if pareto.startswith("trade-off") and abs(cmp["lcoe_change_pct"]) <= 5.0:
        return "alternative"
    return "reject"


def _option_reason(cmp, hint):
    d, pareto = cmp["delta"], cmp["pareto"]
    return (
        f"{pareto[0].upper() + pareto[1:]}: LCOE {d['lcoe_eur_per_mwh']:+.2f} EUR/MWh "
        f"({cmp['lcoe_change_pct']:+.1f} %), CO2 {d['co2_t_per_year']:+,.0f} t/yr, CAPEX "
        f"{d['capex_meur']:+.1f} MEUR; {hint}."
    )


def _run_options(options):
    return lambda m: {
        "content": "Run every option for the full year in one go, each with its own GEMINI run.",
        "tool_calls": [("run_design", args) for _, args, _ in options],
    }


def _compare_options(n_runs, baseline_from="first"):
    def step(messages):
        runs = _tool_results(messages, "run_design")
        base = _baseline(messages)["run_id"]
        new = [r["run_id"] for r in runs[-n_runs:] if "run_id" in r]
        return {
            "content": f"Compare each option with the pick [{base}].",
            "tool_calls": [("compare_runs", {"run_id": r, "baseline_run_id": base}) for r in new],
        }

    return step


def _log_options(options):
    def step(messages):
        cmps = _tool_results(messages, "compare_runs")[-len(options) :]
        calls = []
        for (label, _, hint), cmp in zip(options, cmps):
            calls.append(
                (
                    "log_option",
                    {
                        "option": label,
                        "run_id": cmp["run_id"],
                        "baseline_run_id": cmp["baseline_run_id"],
                        "verdict": _scripted_verdict(cmp),
                        "reason": _option_reason(cmp, hint),
                    },
                )
            )
        return {"content": "Record a verdict and the reason for each option.", "tool_calls": calls}

    return step


def _explore_answer(messages):
    base = _baseline(messages)
    logs = _tool_results(messages, "log_option")
    parts = []
    for c in _tool_results(messages, "compare_runs"):
        parts.append(
            f"{c['design']} {_fmt(c['run']['lcoe_eur_per_mwh'], 2)} EUR/MWh [{c['run_id']}]"
        )
    kept = [lg["option"] for lg in logs if lg.get("verdict") != "reject"]
    accepted = [lg["option"] for lg in logs if lg.get("verdict") == "accept"]
    text = (
        f"The pick {base['design']} costs {_fmt(base['lcoe_eur_per_mwh'], 2)} EUR/MWh with "
        f"{_fmt(base['co2_t_per_year'], 0)} t CO2 per year [{base['run_id']}]. Options: "
        + "; ".join(parts)
        + ". "
    )
    if accepted:
        text += "Accepted (cheaper and lower CO2): " + ", ".join(accepted) + ". "
    else:
        text += "None is both cheaper and lower in CO2, so the pick stays. "
    if kept:
        text += "Kept as alternatives for the report: " + ", ".join(kept) + ". "
    text += "Every verdict and its reason is in the exploration log."
    return {"content": text}


def _storage_answer(messages):
    base = _baseline(messages)
    model = _last(messages, "write_model")
    runs = [r for r in _tool_results(messages, "run_design") if r.get("storage_discharge_mwh")]
    sens = _last(messages, "sensitivity")
    logs = _tool_results(messages, "log_option")
    text = (
        f"GEMINI had no storage model, so the first storage run stopped. I wrote one "
        f"({model['class']}, tests: {model['pytest']}) and registered it as "
        f"'{model['registered_as']}'; the year runs below use it. "
    )
    for r, lg in zip(runs, logs):
        text += (
            f"{r['design']}: {_fmt(r['lcoe_eur_per_mwh'], 2)} EUR/MWh, "
            f"{_fmt(r['co2_t_per_year'], 0)} t CO2, {_fmt(r['purchased_gas_mwh'], 0)} MWh of "
            f"purchased gas, {_fmt(r['storage_discharge_mwh'], 0)} MWh from the store "
            f"[{r['run_id']}] ({lg['verdict']}). "
        )
    rows = "; ".join(
        f"{row['storage_cost_eur_per_mwh']:.0f} EUR/MWh of capacity: "
        f"{_fmt(row['lcoe_eur_per_mwh'], 2)} EUR/MWh [{row['run_id']}]"
        for row in sens["rows"]
    )
    text += (
        f"The pick costs {_fmt(base['lcoe_eur_per_mwh'], 2)} EUR/MWh [{base['run_id']}]. "
        f"The storage price decides it: {rows}."
    )
    return {"content": text}


def _recall_answer(messages):
    mem = _last(messages, "memory_read")
    rows = mem["exploration"]
    accepted = [r for r in rows if r["verdict"] == "accept"]
    alts = [r for r in rows if r["verdict"] == "alternative"]
    text = f"I explored {len(rows)} options against the pick. "
    if accepted:
        text += (
            "These beat it on both cost and CO2: "
            + "; ".join(
                f"{r['design']} {_fmt(r['lcoe_eur_per_mwh'], 2)} EUR/MWh [{r['run_id']}]"
                for r in accepted
            )
            + ". "
        )
    else:
        text += (
            "None beats it on both cost and CO2, so on the numbers a more ambitious design "
            "would not score better on the design half. "
        )
    if alts:
        text += (
            "Closest alternatives: "
            + "; ".join(
                f"{r['design']} {_fmt(r['lcoe_eur_per_mwh'], 2)} EUR/MWh and "
                f"{_fmt(r['co2_t_per_year'], 0)} t CO2 [{r['run_id']}]"
                for r in alts
            )
            + ". "
        )
    text += "Reasons for every verdict are in the exploration log."
    return {"content": text}


def scripted_steps(scenario):
    """Return the scripted policy steps for one scenario."""
    if scenario == "01_design_brief_incomplete":
        return [
            _think("A design request. First check what the brief gives.", "describe_inputs"),
            _think(
                "Supply temperatures are given but return temperatures are not; they set the "
                "flow in both networks, so I ask before running anything.",
                "ask_user",
                question="The brief gives supply temperatures (100 degC heating, 20 degC "
                "cooling) but not the return temperatures. Do you know them?",
                default_if_no_answer="I will use 40 degC heating return and 26 degC cooling "
                "return",
            ),
            _think(
                "User accepts the defaults. Record that, then screen the main options.",
                "memory_write",
                kind="assumption",
                text="User accepted default return temperatures 40 degC heating / 26 degC "
                "cooling (no real values available).",
            ),
            _call(
                "screen",
                n_doublets=[1, 2, 3],
                depths_m=[2800, 3100],
                upgrades=["boiler", "heat_pump"],
                coolings=["electric", "absorption"],
                chp=[False, True],
            ),
            lambda m: _call("cross_check", run_id=_last(m, "screen")["best_by_lcoe"][0]["run_id"]),
            _design_answer,
        ]
    if scenario == "02_offtopic_weather":
        return [
            {
                "content": "That is outside what I can help with here: I design and check the "
                "geothermal heating and cooling plant. I can test how hot summer air would "
                "change the electric chillers' power use, if that helps."
            }
        ]
    if scenario == "03_incomplete_whatif":
        return [
            _think(
                "The user wants a what-if on the heating return temperature but gives no "
                "value. Ask, rather than guess.",
                "ask_user",
                question="Which heating return temperature should I test? The current "
                "assumption is 40 degC.",
                default_if_no_answer="I will test 50 degC",
            ),
            _think("Run the base design first, then vary the return.", "run_design", **PICK),
            lambda m: _call(
                "sensitivity",
                run_id=_last(m, "run_design")["run_id"],
                parameter="heating_return_c",
                values=[50],
            ),
            _whatif_answer,
        ]
    if scenario == "04_hallucination_caught":
        return [
            _call("run_design", **PICK),
            _gas_only_wrong,
            _gas_only_fixed,
        ]
    if scenario == "05_uncertainty_permeability":
        return [
            _call("run_design", **PICK),
            lambda m: _call(
                "sensitivity",
                run_id=_last(m, "run_design")["run_id"],
                parameter="permeability_md",
                values=[50, 100, 200],
            ),
            _perm_answer,
        ]
    if scenario == "06_write_missing_model":
        return [
            _think(
                "list_models shows no dry cooler, so write one as a StaticModel with tests.",
                "list_models",
            ),
            _call(
                "write_model",
                name="dry_cooler",
                register_as="dry_cooler",
                code=DRY_COOLER_CODE,
                test_code=DRY_COOLER_TESTS,
            ),
            _model_answer,
        ]
    if scenario == "07_invalid_tool_call":
        return [
            _call("run_design", **{**PICK, "n_doublets": 4}),
            _think(
                "Gate 1 rejected 4 doublets: the brief caps it at 3. Run 3 instead and say so.",
                "run_design",
                **{**PICK, "n_doublets": 3},
            ),
            _invalid_answer,
        ]
    if scenario == "08_memory_recall":
        return [_call("memory_read"), _memory_answer]
    if scenario == "09_explore_ambitious":
        n_opt, n_sto = len(AMBITIOUS_OPTIONS), len(STORAGE_OPTIONS)
        storage_args = STORAGE_OPTIONS[0][1]
        return [
            # turn 1: conventional upgrades, each against the pick
            _think(
                "Run the pick first as the baseline, then every option against it.",
                "run_design",
                **PICK_CHP,
            ),
            _run_options(AMBITIOUS_OPTIONS),
            _compare_options(n_opt),
            _log_options(AMBITIOUS_OPTIONS),
            _explore_answer,
            # turn 2: storage needs a model GEMINI does not have
            _think(
                "Storage is not a design option in GEMINI. Check the model slots.",
                "list_models",
            ),
            _think(
                "The thermal_storage slot is empty; try the run to see what it needs.",
                "run_design",
                **storage_args,
            ),
            _think(
                "The run names the interface it needs. Write a daily-step store with a power "
                "limit and standing loss, with tests for the energy balance and limits.",
                "write_model",
                name="thermal_storage",
                register_as="thermal_storage",
                code=THERMAL_STORAGE_CODE,
                test_code=THERMAL_STORAGE_TESTS,
            ),
            lambda m: {
                "content": "Model registered. Run the baseline (reused) and both store sizes.",
                "tool_calls": [("run_design", PICK_CHP)]
                + [("run_design", args) for _, args, _ in STORAGE_OPTIONS],
            },
            _compare_options(n_sto),
            lambda m: _think(
                "Storage cost is a low-confidence assumption; test it on the larger store.",
                "sensitivity",
                run_id=_tool_results(m, "run_design")[-1]["run_id"],
                parameter="storage_cost_eur_per_mwh",
                values=[300, 500, 800],
            ),
            _log_options(STORAGE_OPTIONS),
            _storage_answer,
            # turn 3: recall from the exploration log
            _call("memory_read", query="exploration"),
            _recall_answer,
        ]
    raise KeyError(scenario)
