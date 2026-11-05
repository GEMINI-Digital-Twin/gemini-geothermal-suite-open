"""Agent tests with a scripted stand-in for the LLM (no Ollama needed).

Each scenario reproduces a behaviour the judges asked to see, or a failure we
observed in the tool-calling test, and checks the guardrails react correctly.
"""

import json

import numpy as np
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
    ag = make(mem, [lambda m: {"content": "Expect a COP of 4.7."}] * 3)  # two correction rounds, then a warning
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
    share = ch["heating_geothermal_share_pct"]
    assert ch["assumptions_changed"]["heating_return_temperature_c"] == {"before": 55.0, "after": 45}
    assert share["after"] > share["before"] and share["direction"] == "increased"


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
    holder = []
    ag = make(mem, [lambda m: call("sweep_designs", depths_m=[2500, 3000], n_doublets_options=[1, 3]), answer,
                    lambda m: {"content": "1. **3x3000m:**\n   - CO2: " + str(holder[0].design_co2["3x3000m"])
                               + " kt/year"}])
    holder.append(ag)
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
    assert tb.parse_name(name) == (2, 2500.0, 0.20, 650.0, 12.0, 6.0, 4.0, False)
    assert tb.parse_name(tb.canonical_name(2, 3500, electric_chiller_mw=10, gas_reinjection=True))[-1] is True
    name = tb.canonical_name(2, 2500, heat_pump_mw=12, absorption_chiller_mw=6, electric_chiller_mw=10)
    c = tb.compare_designs([name])
    assert c["designs"][0]["meets_all_constraints"] and c["designs"][0]["name"] == name


def test_sweep_over_limit_runs_narrowed_grid(mem, monkeypatch):
    """Demo 8: the model resent a rejected 324-design sweep 12 times. Now the narrowed grid runs instead."""
    tb = ToolBox(mem)
    calls = []

    def fake_eval(self, n, z, **kw):
        calls.append((n, z, kw))
        name = self.canonical_name(n, z, **kw)
        return {"name": name, "violations": [], "warnings": [], "heating_limit_on_peak_day": "FLOW: x",
                "gemini_cross_check": "PASS",
                "kpi": {k: 1.0 for k in ("heating_geothermal_share_pct", "heating_natural_gas_GWh", "cooling_unmet_GWh",
                                         "electricity_total_GWh", "pump_electricity_GWh", "co2_kt_per_year", "capex_MEUR",
                                         "cost_EUR_per_MWh", "cost_with_EIB_co2_value_EUR_per_MWh")}}
    monkeypatch.setattr(ToolBox, "evaluate_design", fake_eval)
    monkeypatch.setattr(ToolBox, "_right_size", lambda self, name: None)
    r = tb.sweep_designs([2500, 3500], [1, 2, 3], [15, 20, 25], [5, 7.5, 10], [0, 2.5, 5], [True, False])
    assert r["narrowed_automatically"]["requested_combinations"] >= 324 and 0 < len(calls) <= 48
    ran = r["narrowed_automatically"]["ran_instead"]
    assert ran["n_doublets_options"] == [1, 2, 3] and ran["depths_m"] == [2500, 3500]
    assert ran["heat_pump_mw_options"] == [0.0]  # "no heat pump" kept, heat pump sizes thinned first
    assert 0.0 in ran["absorption_chiller_mw_options"] and "answer_summary" in r


# ---------------------------------------------------------------- regressions from demo 5 (31 Oct, cooling components)
def test_demo5_challenge_facts_need_no_tool_call(mem):
    ag = make(mem, [lambda m: {"content": "Heating must be supplied at 100 C and cooling at 20 C; the heating peak is 30 MW "
                                          "and each doublet is limited to 300 m3/h."}])
    out = ag.ask("Remind me of the supply temperatures and limits.")
    assert "verifier warning" not in out and ag.stats["claim_corrections"] == 0


def test_demo5_components_and_sizes_from_sweep_names_accepted(mem):
    def answer(m):
        name = last_tool_result(m)["lowest_co2_design_meeting_all_constraints"]["name"]
        return {"content": f"{name} uses a 10 MW electric chiller and meets all constraints."}
    ag = make(mem, [lambda m: call("sweep_designs", depths_m=[3000], n_doublets_options=[2],
                                   electric_chiller_mw_options=[0, 10]), answer])
    out = ag.ask("Find a design that meets all constraints.")
    assert "verifier warning" not in out and ag.stats["claim_corrections"] == 0
    assert "2x3000m_EC10" in ag.feasible


def test_demo5_lowest_among_feasible_designs_accepted(mem):
    ag = make(mem, [lambda m: call("sweep_designs", depths_m=[3000], n_doublets_options=[2],
                                   electric_chiller_mw_options=[0, 10]),
                    lambda m: {"content": "2x3000m_EC10 has the lowest CO2 of the designs that meet all constraints."}])
    out = ag.ask("Which design has the lowest CO2?")
    assert ag._lowest_co2(feasible_only=True) == "2x3000m_EC10" and "2x3000m" not in ag.feasible
    assert "verifier warning" not in out and ag.stats["claim_corrections"] == 0


def test_demo5_component_not_in_named_design_caught(mem):
    ag = make(mem, [lambda m: call("sweep_designs", depths_m=[3000], n_doublets_options=[2],
                                   absorption_chiller_mw_options=[0, 6], electric_chiller_mw_options=[10]),
                    lambda m: {"content": "2x3000m_EC10 uses an absorption chiller driven by the brine."},
                    lambda m: {"content": "2x3000m_ABS6_EC10 uses an absorption chiller driven by the brine."}])
    ag.ask("Which design uses absorption cooling?")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "absorption" in note and "2x3000m_EC10" in note


def test_demo5_unrequested_geometry_change_rejected(mem):
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=2, depth_m=3000, well_inner_diameter_m=0.15),
                    lambda m: {"content": "Rejected; I kept the default geometry."}])
    ag.ask("Evaluate 2 doublets at 3000 m.")
    assert ag.stats["rejected_tool_calls"] == 1
    assert "diameter" in [e for e in ag.events if e[0] == "tool"][0][3]


def test_demo5_requested_geometry_change_allowed(mem):
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=2, depth_m=3000, well_inner_diameter_m=0.15),
                    lambda m: {"content": "Done."}])
    ag.ask("Evaluate 2 doublets at 3000 m with a smaller well diameter of 0.15 m.")
    assert ag.stats["rejected_tool_calls"] == 0


def test_demo5_explanation_without_tool_call_caught(mem):
    ag = make(mem, [lambda m: {"content": "A third doublet does not help because the brine is too cold for the design."},
                    lambda m: call("compare_designs", names=["2x2500m", "3x2500m"]),
                    lambda m: {"content": "Both designs are TEMPERATURE-limited on the peak day."}])
    out = ag.ask("Why does a third doublet not help at 2500 m? Use the results to explain.")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "without calling any tool" in note and ag.stats["tool_calls"] == 1
    assert "verifier warning" not in out


def test_demo5_oversized_heat_pump_warned(mem):
    r = ToolBox(mem).evaluate_design(2, 3500, heat_pump_mw=25, electric_chiller_mw=10)
    assert any(w.startswith("P8_OVERSIZED") and "heat pump 25 MW" in w for w in r["warnings"])


# ---------------------------------------------------------------- regressions from demo 6 (31 Oct)
def test_demo6_cop_confused_with_lorenz_efficiency_caught(mem):
    ag = make(mem, [lambda m: {"content": "The COP for the heat pump in this design is assumed to be **0.5** based on the "
                                          "provided assumptions."},
                    lambda m: {"content": "I need to evaluate a design with a heat pump first; which design do you mean?"}])
    ag.ask("What COP will our heat pump have?")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "0.5 COP" in note


def test_demo6_cop_from_day_operation_is_evidence(mem):
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=2, depth_m=3500, heat_pump_mw=1, absorption_chiller_mw=7.5,
                                   electric_chiller_mw=5),
                    lambda m: call("get_day_operation", name="2x3500m_HP1_ABS7.5_EC5", date="2027-07-01"),
                    lambda m: {"content": f"On **2027-07-01** the heat pump COP is {last_tool_result(m)['heat_pump_COP']}."}])
    out = ag.ask("What COP does the heat pump reach on 1 July?")
    assert "verifier warning" not in out and ag.stats["claim_corrections"] == 0


def test_demo6_wrong_field_value_for_designs_caught(mem):
    ag = make(mem, [lambda m: call("compare_designs", names=["2x2500m", "3x2500m"]),
                    lambda m: {"content": "### Cooling\nBoth designs have no cooling unmet (cooling_unmet_GWh = 0.0)."},
                    lambda m: {"content": "### Cooling\nNeither design has a chiller (cooling_unmet_GWh = 23.74)."}])
    out = ag.ask("Why does a third doublet not help at 2500 m?")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "cooling_unmet_GWh = 0.0" in note and "23.74" in note
    assert "verifier warning" not in out


def test_demo6_wrong_peak_day_caught(mem):
    ag = make(mem, [lambda m: call("get_demand_summary"),
                    lambda m: {"content": "On the peak cooling day (2027-07-01) cooling is high."},
                    lambda m: {"content": "On the peak cooling day (2027-07-19) cooling is 10.0 MW."}])
    ag.ask("When is cooling highest?")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "2027-07-19" in note


def test_demo6_oversized_design_recommendation_caught(mem):
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=2, depth_m=3500, heat_pump_mw=20, absorption_chiller_mw=7.5,
                                   electric_chiller_mw=5),
                    lambda m: {"content": "2x3500m_HP20_ABS7.5_EC5 remains the best option."},
                    lambda m: {"content": "Its 20 MW heat pump is oversized, so I would not recommend it as it stands."}])
    ag.ask("Evaluate this design.")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "P8_OVERSIZED" in note and "right-sized" in note


def test_demo6_sweep_suggests_a_valid_smaller_call_and_right_sizes(mem):
    tb = ToolBox(mem)
    sc = tb._suggest_grid({"depths_m": [2500, 3500], "n_doublets_options": [1, 2, 3], "heat_pump_mw_options": [20, 25, 30],
                           "absorption_chiller_mw_options": [5, 7.5, 10], "electric_chiller_mw_options": [0, 2.5, 5],
                           "gas_reinjection_options": [False]})
    assert np.prod([len(v) for v in sc.values()]) <= 36 and sc["n_doublets_options"] == [1, 2, 3]
    r = tb.sweep_designs([3500], [2], [20], [0], [10])
    assert r["recommended_design"] != "2x3500m_HP20_EC10"  # "no heat pump" is always a candidate now
    hp_row = next(x for x in r["ranked_by_co2"] if x["name"] == "2x3500m_HP20_EC10")
    assert any(w.startswith("P8_OVERSIZED") for w in hp_row["warnings"])


def test_demo6_old_tool_results_are_compacted(mem):
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=2, depth_m=3000, electric_chiller_mw=10),
                    lambda m: {"content": "Done."}])
    ag.ask("Evaluate 2 doublets at 3000 m with a 10 MW electric chiller.")
    tool_msg = [m for m in ag.messages if m["role"] == "tool"][0]["content"]
    assert "_compacted" in tool_msg and len(tool_msg) < 400


def test_demand_summary_states_the_limits(mem):
    d = ToolBox(mem).get_demand_summary()
    assert d["limits"]["flow_m3h_per_doublet_max"] == 300 and d["supply_temperature_C"]["heating"] == 100


# ---------------------------------------------------------------- regressions from demo 7 (31 Oct)
def test_demo7_reversed_before_after_caught(mem):
    def answer_ok(m):
        ch = last_tool_result(m)["changes_vs_previous_evaluation_of_this_design"]["heating_geothermal_share_pct"]
        return {"content": f"The geothermal share {ch['direction']} from {ch['before']}% to {ch['after']}%."}

    def reversed_answer(m):  # demo 7: before and after swapped
        ch = last_tool_result(m)["changes_vs_previous_evaluation_of_this_design"]["heating_geothermal_share_pct"]
        return {"content": f"Heating geothermal share changed from {ch['after']}% to {ch['before']}%."}
    ag = make(mem, [lambda m: call("evaluate_design", n_doublets=3, depth_m=3500, heat_pump_mw=1, absorption_chiller_mw=5,
                                   electric_chiller_mw=4),
                    lambda m: {"content": "Done."},
                    lambda m: call("set_assumption", name="heating_return_temperature_c", value=45, reason="user",
                                   source="user"),
                    lambda m: call("evaluate_design", n_doublets=3, depth_m=3500, heat_pump_mw=1, absorption_chiller_mw=5,
                                   electric_chiller_mw=4),
                    reversed_answer, answer_ok])
    ag.ask("Evaluate 3 doublets at 3500 m with HP 1, ABS 5, EC 4.")
    out = ag.ask("Our network returns at 45 C. Re-evaluate.")
    note = [e[1] for e in ag.events if e[0] == "verifier"][0]
    assert "reverses before and after" in note
    assert "verifier warning" not in out and "geothermal share" in out


def test_demo7_idle_heat_pump_day_points_to_mean_cop(mem):
    tb = ToolBox(mem)
    tb.evaluate_design(3, 3500, heat_pump_mw=1, absorption_chiller_mw=5, electric_chiller_mw=4)
    r = tb.get_day_operation("3x3500m_HP1_ABS5_EC4", "2027-01-28")
    assert r["heat_pump_MW"] == 0 and "heat_pump_mean_COP" in r["note"]



# ---------------------------------------------------------------- regressions from demo 8 (4 Nov)
def test_demo8_repeated_failing_call_blocked(mem):
    bad = lambda m: call("evaluate_design", n_doublets=4, depth_m=3000)  # noqa: E731
    ag = make(mem, [bad, bad, lambda m: {"content": "Four doublets are not allowed; the limit is 1-3."}])
    ag.ask("Evaluate 4 doublets at 3000 m.")
    payloads = [e[3] for e in ag.events if e[0] == "tool"]
    assert "already made exactly this call" in payloads[1]


def test_demo8_shorthand_name_uses_evaluated_design(mem):
    from agentic_design.agent import guard
    known = ["2x2500m_HP15_ABS5_EC5_RI", "3x2500m_HP15_ABS5_EC5_RI"]
    assert guard.check_components("3x2500m uses an absorption chiller and a heat pump.", [], (), known) == []
    assert guard.check_components("3x2500m uses an absorption chiller.", [], (), ["3x2500m"]) != []



# ---------------------------------------------------------------- token saving (4 Nov)
def test_only_last_turn_kept_and_best_design_in_system_prompt(mem):
    ag = make(mem, [lambda m: call("sweep_designs", depths_m=[3000], n_doublets_options=[2],
                                   electric_chiller_mw_options=[10]),
                    lambda m: {"content": "Done."},
                    lambda m: {"content": "Second answer."},
                    lambda m: {"content": "Third answer."}])
    ag.ask("Find a design.")
    ag.ask("Question two.")
    ag.ask("Question three.")
    users = [m["content"] for m in ag.messages if m["role"] == "user"]
    assert users == ["Question three."] or users == ["Question two.", "Question three."][-1:]
    assert "Current recommended design" in ag.messages[0]["content"]



# ---------------------------------------------------------------- regressions from demo 10 (4 Nov)
def test_demo10_design_name_digits_are_not_cops():
    from agentic_design.agent import guard
    nums = guard.numbers_with_units("The heat pump in 2x3500m_HP1.5_EC10_RI has a COP of 7.27 on that day.")
    assert [(v, u) for v, _, _, u in nums] == [(7.27, "COP")]


def test_demo10_good_first_sweep_fits_and_matches_report(mem):
    r = ToolBox(mem).sweep_designs([3000, 3500], [1, 2, 3], [0], [0, 5], [5, 10], [False, True])
    assert "narrowed_automatically" not in r
    assert r["recommended_design"] == "2x3500m_ABS5_EC5_RI"
    assert r["answer_summary"].startswith("Recommended: 2x3500m_ABS5_EC5_RI")



# ---------------------------------------------------------------- regressions from demo 11 (4 Nov)
def test_demo11_sweep_payload_leads_with_summary():
    from agentic_design.agent.core import Agent
    rows = [{"name": f"d{i}", "violations": [] if i % 2 else ["C8_COOLING_UNMET"], "co2_kt_per_year": float(i),
             "cost_with_EIB_co2_value_EUR_per_MWh": 100.0 - i} for i in range(30)]
    out = Agent._for_llm("sweep_designs", {"ranked_by_co2": rows, "answer_summary": "Recommended: d29.",
                                           "recommended_design": "d29"})
    assert list(out)[0] == "answer_summary" and len(out["best_designs_meeting_all_constraints"]) == 8
    assert out["best_designs_meeting_all_constraints"][0]["name"] == "d29" and out["evaluated"] == 30


def test_demo11_heating_limit_says_demand_is_met(mem):
    r = ToolBox(mem).evaluate_design(2, 3500, absorption_chiller_mw=5, electric_chiller_mw=5, gas_reinjection=True)
    assert r["meets_all_constraints"] and "Demand is still met" in r["heating_limit_on_peak_day"]



# ---------------------------------------------------------------- regressions from demo 12 (4 Nov)
def test_demo12_figures_of_another_design_caught(mem):
    """Q2 quoted the 2-doublet design's electricity and investment under the 3-doublet design. Names with
    underscores were never matched by the per-design check, and EUR units were not checked at all."""
    from agentic_design.agent import guard
    ev = {"3x3500m_ABS5_EC5_RI": guard.new_evidence(), "2x3500m_ABS5_EC5_RI": guard.new_evidence()}
    guard.add_evidence(ev["3x3500m_ABS5_EC5_RI"], {"electricity_total_GWh": 5.23, "capex_MEUR": 74.4,
                                                    "cost_EUR_per_MWh": 72.0})
    guard.add_evidence(ev["2x3500m_ABS5_EC5_RI"], {"electricity_total_GWh": 7.42, "capex_MEUR": 55.6,
                                                    "cost_EUR_per_MWh": 62.9})
    answer = ("### 1. **3x3500m_ABS5_EC5_RI**\n- **Electricity Total**: 7.42 GWh\n- **Capital Cost**: 55.6 MEUR\n"
              "- **Cost**: 72.0 EUR/MWh\n### 2. **2x3500m_ABS5_EC5_RI**\n- **Electricity Total**: 7.42 GWh")
    bad = guard.check_design_numbers(answer, ev, guard.new_evidence())
    assert any("7.42 GWh" in b and "3x3500m" in b for b in bad) and any("55.6 MEUR" in b for b in bad)
    assert not any("72.0" in b for b in bad) and len(bad) == 2


def test_demo12_component_asked_in_an_earlier_question_does_not_excuse(mem):
    ag = make(mem, [lambda m: {"content": "Which design do you mean? None has a heat pump."},
                    lambda m: call("evaluate_design", n_doublets=2, depth_m=3500, absorption_chiller_mw=5,
                                   electric_chiller_mw=5, gas_reinjection=True),
                    lambda m: {"content": "The lower return temperature reduces the efficiency of the heat pump."},
                    lambda m: {"content": "CO2 rose because pump electricity rose."}])
    ag.ask("What COP will our heat pump have?")
    ag.ask("Re-evaluate 2 doublets at 3500 m with absorption 5 MW, electric chiller 5 MW and gas reinjection.")
    notes = [e[1] for e in ag.events if e[0] == "verifier"]
    assert notes and "heat pump" in notes[-1]


def test_demo12_change_cause_is_computed(mem):
    tb = ToolBox(mem)
    tb.evaluate_design(2, 3500, absorption_chiller_mw=5, electric_chiller_mw=5, gas_reinjection=True)
    tb.set_assumption("heating_return_temperature_c", 45, "user", "user")
    r = tb.evaluate_design(2, 3500, absorption_chiller_mw=5, electric_chiller_mw=5, gas_reinjection=True)
    cause = r["changes_vs_previous_evaluation_of_this_design"]["cause"]
    assert "pump electricity" in cause and "heat pump" not in cause


# ---------------------------------------------------------------- regressions from demo 13 (4 Nov)
def test_demo13_checks():
    from agentic_design.agent import guard
    ng = ["heating return temperature", "cooling network return temperature", "costs"]
    # assumption lines mention a heat pump without claiming one
    assert guard.check_components("- **Heat Pump Efficiency (η Lorenz)**: 0.5", [], ()) == []
    # "These values ... provided by the organisers" refers to the sentence before
    assert "heating return temperature" in guard.check_attribution("The heating return temperature is 55 C. These values are based on the assumptions "
                                   "provided by the organisers.", ng)
    # demand is fixed data
    assert guard.check_demand_claims("The lower return temperature increases the heating demand.")
    assert not guard.check_demand_claims("The heating demand does not change.")
    # comparison direction
    assert guard.check_comparisons("3x2500m has a slightly higher share (70.3%) compared to the 2x2500m design (70.4%).")
    assert not guard.check_comparisons("The cost is higher (68.8 EUR/MWh) than for the 2x2500m design (61.6 EUR/MWh).")
    # a hedge far away in the sentence no longer excuses a component
    s = ("This is still below the required 100 C, and the heating demand is met through the backup boiler and heat pump, "
         "which add 8.9 MW on that day.")
    assert guard.check_components(s, ["2x2500m: heating heat exchanger. NOT included: heat pump"], ()) == ["heat pump"]


def test_demo13_topup_text_names_real_sources(mem):
    r = ToolBox(mem).evaluate_design(2, 2500, electric_chiller_mw=10)
    t = r["heating_limit_on_peak_day"]
    assert "Demand is still met" in t and "heat pump" not in t.split("Demand is still met")[1]


def test_demo13_sweep_summary_reports_change_after_assumption(mem):
    tb = ToolBox(mem)
    tb.sweep_designs([3500], [2], [0], [5], [5], [True])
    tb.set_assumption("heating_return_temperature_c", 45, "user", "user")
    r = tb.sweep_designs([3500], [2], [0], [5], [5], [True])
    assert "after the assumption change" in r["answer_summary"] and "co2_kt_per_year" in r["answer_summary"]


# ---------------------------------------------------------------- regressions from demo 14 (4 Nov)
def test_demo14_checks():
    from agentic_design.agent import guard
    s = "If **cost is the top priority**, choose the **2x3500m_ABS5_EC5_RI** design."
    assert guard.check_cost_claims(s, "1x3000m_EC10")
    assert not guard.check_cost_claims("1x3000m_EC10 is the cheapest design.", "1x3000m_EC10")
    assert not guard.check_cost_claims("2x3500m_ABS5_EC5_RI has the lowest cost with CO2 valued at 450 EUR/t.",
                                       "1x3000m_EC10")
    assert guard.check_return_temperature("The network return temperature of 100 C used in the design is assumed.")


def test_demo14_best_design_must_be_the_recommended_one(mem):
    ag = make(mem, [lambda m: call("sweep_designs", depths_m=[3500], n_doublets_options=[2, 3],
                                   absorption_chiller_mw_options=[5], electric_chiller_mw_options=[5],
                                   gas_reinjection_options=[True]),
                    lambda m: {"content": "Done."},
                    lambda m: call("compare_designs", names=["3x3500m_ABS5_EC5_RI"]),
                    lambda m: {"content": "3x3500m_ABS5_EC5_RI remains the best."},
                    lambda m: call("compare_designs", names=["2x3500m_ABS5_EC5_RI"]),
                    lambda m: {"content": "2x3500m_ABS5_EC5_RI remains the recommended design."}])
    ag.ask("Find the best design.")
    out = ag.ask("Re-evaluate the best design with a 45 C return.")
    notes = [e[1] for e in ag.events if e[0] == "verifier"]
    assert notes and "2x3500m_ABS5_EC5_RI" in notes[-1] and "verifier warning" not in out
