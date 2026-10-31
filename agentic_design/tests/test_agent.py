"""Agent tests with a scripted stand-in for the LLM (no Ollama needed).

Each scenario reproduces a behaviour the judges asked to see, or a failure we
observed in the tool-calling test, and checks the guardrails react correctly.
"""

import json

import pytest

from agentic_design.agent.core import Agent
from agentic_design.agent.llm import ScriptedLLM
from agentic_design.agent.memory import Memory
from agentic_design.agent.tools import ToolBox


def call(_tool, **args):
    return {"tool_calls": [{"name": _tool, "arguments": args}]}


def last_tool_result(messages):
    return json.loads([m for m in messages if m["role"] == "tool"][-1]["content"])


@pytest.fixture
def mem(tmp_path):
    return Memory(tmp_path / "log.json")


def make(mem, steps):
    """steps: list of callables(messages) -> llm output, consumed in order."""
    it = iter(steps)
    return Agent(ScriptedLLM(lambda msgs: next(it)(msgs)), ToolBox(mem))


def test_design_answer_with_tool_numbers_passes(mem):
    def answer(msgs):
        k = last_tool_result(msgs)["kpi"]
        return {"content": f"2x3000m: geothermal {k['heating_geothermal_share_pct']}% of heating, "
                           f"CO2 {k['co2_kt_per_year']} kt/yr; cooling not yet modelled."}
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=2, depth_m=3000), answer])
    out = ag.ask("Evaluate 2 doublets at 3000 m.")
    assert "verifier warning" not in out
    assert ag.stats["claim_corrections"] == 0 and ag.stats["tool_calls"] == 1
    assert mem.design("2x3000m") is not None  # remembered


def test_invented_number_is_caught_and_corrected(mem):
    ag = make(mem, [
        lambda m: call("evaluate_design", n_doublets=2, depth_m=2500),
        lambda m: {"content": "The absorption chiller runs at a 150 C drive temperature."},  # hallucination
        lambda m: {"content": f"Geothermal covers {last_tool_result(m)['kpi']['heating_geothermal_share_pct']}% of heating; "
                              "no cooling model exists yet."},
    ])
    out = ag.ask("How good is 2 doublets at 2500 m?")
    assert ag.stats["claim_corrections"] == 1
    assert "150" not in out and "verifier warning" not in out
    assert any(e[0] == "verifier" and "150" in e[1] for e in ag.events)


def test_persistent_invention_is_flagged_to_user(mem):
    ag = make(mem, [lambda m: {"content": "Expect a COP of 4.7."}, lambda m: {"content": "Expect a COP of 4.7."}])
    out = ag.ask("Heat pump COP?")
    assert "verifier warning" in out and ag.stats["unverified_answers"] == 1


def test_out_of_range_arguments_rejected_before_running(mem):
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=4, depth_m=2500),
                    lambda m: {"content": f"Rejected: {last_tool_result(m)['problems'][0]}"}])
    ag.ask("Try 4 doublets.")
    assert ag.stats["rejected_tool_calls"] == 1
    assert mem.design("4x2500m") is None


def test_string_arguments_from_small_models_are_coerced(mem):
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets="1", depth_m="2500"),
                    lambda m: {"content": "Done."}])
    ag.ask("1 doublet at 2500 m")
    assert ag.stats["rejected_tool_calls"] == 0 and mem.design("1x2500m") is not None


def test_user_value_must_really_come_from_user(mem):
    ag = make(mem, [lambda m: call("set_assumption", name="heating_return_temperature_c", value=45,
                                    reason="user said so", source="user"),
                    lambda m: {"content": "What is your network return temperature?"}])
    ag.ask("Use the organisers' return temperature.")  # the user gave no number
    assert ag.stats["rejected_tool_calls"] == 1
    assert ag.tools.a.heating_return_temperature_c == 55.0


def test_user_value_accepted_and_remembered(tmp_path):
    mem = Memory(tmp_path / "log.json")
    ag = make(mem, [lambda m: call("set_assumption", name="heating_return_temperature_c", value=45,
                                    reason="network data from user", source="user"),
                    lambda m: {"content": "Return temperature set to 45 C."}])
    ag.ask("Our network returns at 45 C.")
    assert ag.tools.a.heating_return_temperature_c == 45
    # a new session loads it from long-term memory
    assert ToolBox(Memory(tmp_path / "log.json")).a.heating_return_temperature_c == 45


def test_irrelevant_question_uses_no_tools(mem):
    ag = make(mem, [lambda m: {"content": "That is outside geothermal design; I can't help with football."}])
    ag.ask("Who won the football match?")
    assert ag.stats["tool_calls"] == 0


def test_decision_must_cite_evaluated_designs(mem):
    ag = make(mem, [lambda m: call("record_decision", decision="Go deep", based_on_designs=["2x9999m"]),
                    lambda m: {"content": "I need to evaluate it first."}])
    ag.ask("Record the decision.")
    assert "never evaluated" in last_tool_result(ag.messages)["error"]


def test_transcript_has_tokens_and_verification(mem):
    ag = make(mem, [lambda m: {"content": "Hello."}])
    ag.ask("hi")
    md = ag.transcript_markdown()
    assert "tokens this turn" in md and "Session statistics" in md


def test_memory_summary_in_system_prompt(tmp_path):
    m1 = Memory(tmp_path / "log.json")
    ToolBox(m1).evaluate_design(2, 2500)
    ag = Agent(ScriptedLLM(lambda m: {"content": "x"}), ToolBox(Memory(tmp_path / "log.json")))
    assert "2x2500m" in ag.messages[0]["content"]


# ---------------------------------------------------------------- regressions from the first real demo (31 Oct)
def test_demo_failure_organisers_value_is_refused(mem):
    """qwen3:8b claimed 'the return temperature of 40 C, as specified by the organisers' - they specify none."""
    ag = make(mem, [lambda m: call("set_assumption", name="heating_return_temperature_c", value=40,
                                    reason="organiser value", source="organisers"),
                    lambda m: {"content": "The organisers did not give a return temperature. What is yours?"}])
    ag.ask("Use the network return temperature the organisers specified.")
    assert ag.stats["rejected_tool_calls"] == 1
    assert "did NOT specify" in last_tool_result(ag.messages)["error"]
    assert ag.tools.a.heating_return_temperature_c == 55.0


def test_demo_failure_cop_not_backed_by_unrelated_number(mem):
    """'COP approximately 3.5' passed because 3.5 MW (July heating mean) was in the evidence."""
    ag = make(mem, [lambda m: call("get_demand_summary"),
                    lambda m: {"content": "The COP would be approximately 3.5."},
                    lambda m: {"content": "I cannot give a COP: no heat pump model is connected yet. "
                                          "Which source and supply temperatures do you have in mind?"}])
    out = ag.ask("What COP will our heat pump have?")
    assert ag.stats["claim_corrections"] == 1 and "3.5" not in out


def test_demo_failure_nonexistent_heat_pump_flagged(mem):
    """The agent credited 'the heat pump system' although the evaluated design has none."""
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=3, depth_m=2500),
                    lambda m: {"content": "The heat pump system improved efficiency."},
                    lambda m: {"content": "The design has no heat pump; geothermal heat goes through the heat exchanger."}])
    ag.ask("Explain the result.")
    assert ag.stats["claim_corrections"] == 1
    assert any(e[0] == "verifier" and "heat pump" in e[1] for e in ag.events)


def test_heating_limit_diagnostic_explains_third_doublet(mem):
    tb = ToolBox(mem)
    assert tb.evaluate_design(3, 2500)["heating_limit_on_peak_day"].startswith("TEMPERATURE")
    assert not tb.evaluate_design(2, 3000)["heating_limit_on_peak_day"].startswith("TEMPERATURE")


def test_reevaluation_reports_change_for_same_design(mem):
    tb = ToolBox(mem)
    tb.evaluate_design(3, 2500)
    tb.set_assumption("heating_return_temperature_c", 45, "user value", "user")
    ch = tb.evaluate_design(3, 2500)["changes_vs_previous_evaluation_of_this_design"]
    old, new = ch["heating_geothermal_share_pct"]
    assert ch["assumptions_then"]["heating_return_temperature_c"] == 55.0 and new > old


def test_cooling_violation_names_the_real_cause(mem):
    v = ToolBox(mem).evaluate_design(2, 2500)["violations"][0]
    assert "NO cooling technology" in v and "cannot fix" in v


# ---------------------------------------------------------------- regressions from demo 2 (31 Oct, guardrails v2)
def test_demo2_false_compliance_claim_caught(mem):
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=3, depth_m=3000),
                    lambda m: {"content": "**Constraint Compliance:** The design respects all constraints."},
                    lambda m: {"content": "3x3000m fails C8: there is no cooling technology yet."}])
    out = ag.ask("Is 3x3000m feasible?")
    assert ag.stats["claim_corrections"] == 1 and "respects all constraints" not in out


def test_demo2_organiser_attribution_without_tool_call_caught(mem):
    ag = make(mem, [lambda m: {"content": "Since the organisers have specified the heating return temperature, "
                                          "we will re-evaluate the best design."},
                    lambda m: {"content": "The organisers did not give a return temperature. What does your network use?"}])
    out = ag.ask("Use the return temperature the organisers specified.")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "not_given_by_challenge" in note and "instead of doing it" in note
    assert "What does your network use" in out


def test_demo2_number_from_other_design_caught(mem):
    def answer(m):
        return {"content": "1. **3x3000m:**\n   - CO2: 15.08 kt/year"}  # 15.08 kt belongs to 1x2500m
    ag = make(mem, [lambda m: call("sweep_designs", depths_m=[2500, 3000], n_doublets_options=[1, 3]), answer,
                    lambda m: {"content": "1. **3x3000m:**\n   - CO2: 4.34 kt/year"}])
    ag.ask("Compare.")
    assert ag.stats["claim_corrections"] == 1


def test_demo2_geometry_change_gets_new_name(mem):
    tb = ToolBox(mem)
    tb.evaluate_design(3, 3000)
    r = tb.evaluate_design(3, 3000, well_inner_diameter_m=0.15)
    assert r["name"] == "3x3000m_ID0.15" and "non_default_parameters" in r
    assert "changes_vs_previous_evaluation_of_this_design" not in r  # never compared across geometries


def test_compare_refreshes_and_evaluates_by_name(mem):
    tb = ToolBox(mem)
    c = tb.compare_designs(["2x2500m", "3x2500m"])
    assert [d["name"] for d in c["designs"]] == ["2x2500m", "3x2500m"]
    assert all(d["heating_limit_on_peak_day"].startswith("TEMPERATURE") for d in c["designs"])
    tb.set_assumption("heating_return_temperature_c", 45, "user value", "user")
    c2 = tb.compare_designs(["2x2500m"])
    assert c2["designs"][0]["refreshed_for_current_assumptions"]
    assert c2["designs"][0]["heating_geothermal_share_pct"] > c["designs"][0]["heating_geothermal_share_pct"]


# ---------------------------------------------------------------- regressions from demo 3 (31 Oct, guardrails v3)
def test_demo3_wrong_lowest_co2_recommendation_caught(mem):
    ag = make(mem, [lambda m: call("sweep_designs", depths_m=[2500, 3000], n_doublets_options=[2, 3]),
                    lambda m: {"content": "The 2500m Depth design is the most viable option with the lowest CO2 emissions."},
                    lambda m: {"content": f"Lowest CO2: {last_tool_result(m)['lowest_co2_design']['name']}."}])
    ag.ask("Find the lowest-CO2 design.")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "3x3000m" in note


def test_demo3_old_numbers_without_tool_call_caught(mem):
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=3, depth_m=2500),
                    lambda m: {"content": "Done."},
                    # next turn: explains using earlier numbers, no tool call
                    lambda m: {"content": "The third doublet raises the share from 63.4% to 70.3%."},
                    lambda m: call("compare_designs", names=["2x2500m", "3x2500m"]),
                    lambda m: {"content": "Both are TEMPERATURE-limited; the third doublet adds little."}])
    ag.ask("Evaluate 3 doublets at 2500 m.")
    ag.ask("Why does a third doublet not help at 2500 m?")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "without calling any tool" in note
    assert ag.stats["tool_calls"] == 2


def test_component_the_user_asked_about_not_flagged(mem):
    ag = make(mem, [lambda m: {"content": "We need a heat pump model before a COP can be given. Which temperatures?"}])
    out = ag.ask("What COP will our heat pump have?")
    assert "verifier warning" not in out and ag.stats["claim_corrections"] == 0


# ---------------------------------------------------------------- heat pump / chiller options in the tools
def test_names_with_components_round_trip(mem):
    tb = ToolBox(mem)
    name = tb.canonical_name(2, 2500, heat_pump_mw=12, absorption_chiller_mw=6, electric_chiller_mw=4)
    assert name == "2x2500m_HP12_ABS6_EC4"
    assert tb.parse_name(name) == (2, 2500.0, 0.20, 650.0, 12.0, 6.0, 4.0)
    c = tb.compare_designs([name])
    assert c["designs"][0]["meets_all_constraints"] and c["designs"][0]["name"] == name


def test_sweep_limits_combinations(mem):
    r = ToolBox(mem).sweep_designs([2000, 2500, 3000, 3500], [1, 2, 3], heat_pump_mw_options=[0, 6, 12, 18])
    assert "max 36" in r["error"]
