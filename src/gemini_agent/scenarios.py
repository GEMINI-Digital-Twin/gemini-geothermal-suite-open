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

SCENARIOS = {
    "01_design_brief_incomplete": {
        "title": "Open design request with missing inputs (agent asks first)",
        "turns": [
            "Design me a heating and cooling system for the district.",
            "I don't know the real return temperatures, go ahead with your defaults.",
        ],
    },
    "02_offtopic_weather": {
        "title": "Irrelevant question",
        "turns": ["What's the weather in Delft tomorrow?"],
    },
    "03_incomplete_whatif": {
        "title": "Incomplete what-if question (which value?)",
        "turns": [
            "What happens to the cost if the heating return temperature is different?",
            "Try 50 degC.",
        ],
    },
    "04_hallucination_caught": {
        "title": "Physics gate rejects an invented number, agent corrects itself",
        "turns": ["Is the two-doublet boiler design cheaper than heating with gas only?"],
    },
    "05_uncertainty_permeability": {
        "title": "Subsurface uncertainty (bonus)",
        "turns": ["How robust is the two-doublet 3.1 km design if permeability is lower?"],
    },
    "06_write_missing_model": {
        "title": "Agent writes a missing model (dry cooler) with tests",
        "turns": [
            "GEMINI has no dry cooler model. Add one so we can check chiller heat rejection."
        ],
    },
    "07_invalid_tool_call": {
        "title": "Out-of-range request caught by gate 1",
        "turns": ["Run four doublets at 3.1 km with a boiler and electric chillers."],
    },
    "08_memory_recall": {
        "title": "Memory across questions",
        "turns": ["What have we decided so far, and which runs back it up?"],
    },
}


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
        f"I screened {screen['designs_run']} designs; {screen['meet_all_rules']} meet every "
        f"hard rule and every day of demand. Cheapest: {best['design']} at "
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
            "temperature, and no heat rejection when the air is hotter than the water. It can "
            "now be wired after the electric chiller condenser in a project JSON."
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
    mem = _last(messages, "memory_read")
    notes = "; ".join(n["text"].rstrip(".") for n in mem["notes"]) or "nothing yet"
    runs = ", ".join(r["run_id"] for r in mem["recent_runs"] if r.get("valid"))
    return {"content": f"Decisions and notes so far: {notes}. Valid recent runs: {runs}."}


PICK = {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"}


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
    raise KeyError(scenario)
