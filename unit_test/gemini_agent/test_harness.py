"""Harness guards for small open-weight models (no LLM needed: scripted fake chat model).

Each guard comes from a failure seen in the evidence runs with qwen3:1.7b:
ask_user repeated 5x, the same failing call repeated 9x, empty replies mid-procedure,
list arguments sent as dicts, and tool exceptions crashing a run.
"""

import json
from pathlib import Path

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from gemini_agent.runner import AgentRunner
from gemini_agent.tools import Session, build_tools


class ScriptedModel(GenericFakeChatModel):
    """Replays a fixed list of AI messages and accepts bind_tools."""

    def bind_tools(self, tools, **kwargs):
        return self


def _call(name, args, i=0):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"c{name}{i}"}])


def _runner(tmp_path, msgs, mode="interactive"):
    return AgentRunner(
        model="scripted",
        profile="lean",
        mode=mode,
        run_root=tmp_path,
        llm=ScriptedModel(messages=iter(msgs)),
    )


def test_ask_user_ends_the_turn_in_interactive_mode(tmp_path):
    q = "Is cost or CO2 more important?"
    r = _runner(
        tmp_path,
        [
            _call("ask_user", {"question": q, "default_if_no_answer": "balanced"}),
            _call("ask_user", {"question": q, "default_if_no_answer": "balanced"}, 1),
        ],
    )
    turn = r.ask("Design a system for our district.")
    assert turn["tool_calls"] == ["ask_user"] and turn["llm_calls"] == 1
    assert q in turn["answer"]


def test_empty_reply_is_nudged_once_then_answer_is_kept(tmp_path):
    r = _runner(tmp_path, [AIMessage(""), AIMessage("The design needs two doublets.")], mode="auto")
    turn = r.ask("Design a system.")
    assert turn["nudges"] == 1 and "two doublets" in turn["answer"]


def test_repeat_guard_errors_as_data_and_list_coercion(tmp_path):
    s = Session(run_dir=tmp_path / "s", mode="auto")
    t = {x.name: x for x in build_tools(s)}
    first = t["reservoir_at_depth"].invoke({"depth_m": 3000})
    assert "fact_id" in first
    assert "identical" in t["reservoir_at_depth"].invoke({"depth_m": 3000})
    assert "error" in json.loads(
        t["run_model"].invoke({"model_type": "no_such_model", "inputs": {}})
    )
    args = t["search_designs"].args_schema.model_validate(
        {"depths_m": {"2500": 1}, "doublets": "2, 3"}
    )
    assert args.depths_m == [2500.0] and args.doublets == [2, 3]


def test_unit_check_ignores_label_numbers_and_percent_fractions_but_catches_bare_eur():
    from gemini_agent.ledger import FactLedger, provenance_check

    led = FactLedger(seed={"gas": {"co2_mol_frac": 0.2}})
    led.record(
        "evaluate_design",
        {},
        {
            "label": "DH 100/45 C",
            "pump_dp_bar": 45.0,
            "capex_meur": 49.04,
            "probability_demand_fully_met": 0.483,
        },
    )
    ok = provenance_check("Return 45 °C; demand met in 48.3 % of samples.", led)
    assert ok["unit_mismatches"] == []
    led.record("evaluate_design", {}, {"cooling_supply_gwh": {"absorption": 23.74}})
    assert provenance_check("Absorption supplies 23.74 MW.", led)["unit_mismatches"]
    bad = provenance_check("CAPEX is 49.04 EUR.", led)
    assert bad["unit_mismatches"] and bad["unit_mismatches"][0]["unit_written"] == "eur"


def test_search_designs_keeps_the_standard_grid(tmp_path, monkeypatch):
    import gemini_agent.tools as tools_mod

    seen = {}

    def fake_search(
        svc,
        objective="min_lcoe",
        depths=(2200, 2500, 2800, 3100, 3400),
        doublets=(1, 2, 3),
        heat_pumps=(0.0, 5.0, 10.0, 15.0),
        top_k=3,
        progress=None,
    ):
        seen.update(depths=depths, doublets=doublets, heat_pumps=heat_pumps)
        raise RuntimeError("stop here")

    monkeypatch.setattr(tools_mod, "search", fake_search)
    s = Session(run_dir=tmp_path / "s", mode="auto")
    t = {x.name: x for x in build_tools(s)}
    t["search_designs"].invoke({"depths_m": {"2500": 1}, "doublets": [1], "heat_pumps_mw": [1]})
    assert seen["depths"] == (2200, 2500, 2800, 3100, 3400) and seen["doublets"] == (1, 2, 3)
    assert 1 in seen["heat_pumps"] and 15.0 in seen["heat_pumps"]


def test_scalar_wrapped_in_object_is_unwrapped(tmp_path):
    s = Session(run_dir=tmp_path / "s", mode="auto")
    t = {x.name: x for x in build_tools(s)}
    a = t["fetch_weather"].args_schema.model_validate(
        {"latitude": {"value": 52.01}, "reference_year": {"year": 2023}}
    )
    assert a.latitude == 52.01 and a.reference_year == 2023
    assert t["run_model"].args_schema.model_validate(
        {"model_type": "x", "inputs": {"a": 1}}
    ).inputs == {"a": 1}


def test_no_second_question_in_the_turn_that_answers_the_first(tmp_path):
    q = "Is cost or CO2 more important?"
    r = _runner(
        tmp_path,
        [
            _call("ask_user", {"question": q, "default_if_no_answer": "balanced"}),
            _call(
                "ask_user", {"question": "Which weather year?", "default_if_no_answer": "2023"}, 1
            ),
            AIMessage("Proceeding with 2023 weather and a balanced objective."),
        ],
    )
    assert q in r.ask("Design a system.")["answer"]
    turn = r.ask("Low CO2 at reasonable cost. Go ahead.")
    assert turn["pending_question"] is None and "Proceeding" in turn["answer"]


def _two_depth_ledger():
    from gemini_agent.ledger import FactLedger

    led = FactLedger()
    led.record(
        "search_designs",
        {},
        {
            "top": [
                {
                    "design_id": "a3100",
                    "label": "2x doublet @ 3100 m, ElCh 10 MW, gas reinjected",
                    "lcoe_eur_per_mwh": 44.32,
                    "co2_t": 3120.0,
                    "geothermal_share_pct": 99.18,
                },
                {
                    "design_id": "b3100",
                    "label": "2x doublet @ 3100 m, ElCh 10 MW, gas burned",
                    "lcoe_eur_per_mwh": 43.18,
                    "co2_t": 6190.0,
                    "geothermal_share_pct": 94.18,
                },
                {
                    "design_id": "c2500",
                    "label": "2x doublet @ 2500 m, HP 10 MW, ElCh 10 MW, gas reinjected",
                    "lcoe_eur_per_mwh": 47.9,
                    "co2_t": 4010.0,
                    "geothermal_share_pct": 97.5,
                },
            ]
        },
    )
    return led


def test_claim_check_catches_mislabelled_design_and_reversed_comparison():
    from gemini_agent.ledger import provenance_check

    s5 = (
        "- **Designs at 3100 m:**\n  - Geothermal share 99.18%\n  - LCOE: €44.32/MWh\n  - CO2: "
        "3,120 t/year\n\n"
        "- **Designs at 2500 m with a heat pump:**\n  - Geothermal share 94.18%\n  - LCOE: "
        "€43.18/MWh\n"
        "  - CO2: 6,190 t/year\n\n"
        "Drilling to 3100 meters provides a higher geothermal share and lower LCOE compared to "
        "2500 meters."
    )
    out = provenance_check(s5, _two_depth_ledger())
    kinds = [c["type"] for c in out["claim_issues"]]
    assert not out["passed"] and kinds.count("attribute") == 2 and kinds.count("comparison") == 1
    assert "44.32 vs 43.18" in next(
        c["detail"] for c in out["claim_issues"] if c["type"] == "comparison"
    )


def test_claim_check_accepts_correct_comparisons():
    from gemini_agent.ledger import provenance_check

    ok = (
        "- At 3100 m: LCOE 44.32 EUR/MWh, 3,120 t CO2, geothermal share 99.18 %.\n"
        "- At 2500 m with a heat pump: LCOE 47.9 EUR/MWh, 4,010 t CO2, geothermal share 97.5 %.\n"
        "3100 m is cheaper and has lower emissions than 2500 m.\n"
        "Compared to 3100 m, the 2500 m design has a lower geothermal share."
    )
    assert provenance_check(ok, _two_depth_ledger())["claim_issues"] == []
    # no numbers quoted: the comparison falls back to the cheapest recorded design at each depth
    assert provenance_check("2500 m has lower LCOE than 3100 m.", _two_depth_ledger())[
        "claim_issues"
    ]


def test_runner_revision_request_lists_each_issue():
    from gemini_agent.runner import _revision_request

    msg = _revision_request(
        {
            "unsupported": [],
            "unit_mismatches": [
                {"number": 43.18, "unit_written": "€/kwh", "fact_fields": ["lcoe_eur_per_mwh"]}
            ],
            "claim_issues": [{"claim": "3100 m is cheaper", "detail": "values are 44.32 vs 43.18"}],
        }
    )
    assert "43.18" in msg and "44.32 vs 43.18" in msg and "Do not call tools" in msg


def test_request_screen_and_request_match():
    from gemini_agent.physics.site import Brief
    from gemini_agent.request_check import request_mismatches, screen_request

    c = Brief.load().constraints
    assert "300" in screen_request("Run each doublet at 500 m3/h so we need fewer wells.", c)[0]
    assert screen_request("Evaluate 2 doublets at 3100 m, 300 m3/h each.", c) == []
    s5 = "Evaluate 2 doublets at 3100 m with a 10 MW electric chiller and an 18 MW gas backup boiler, gas reinjected."  # noqa: E501
    asked = {
        "well_depth_m": 3100.0,
        "n_doublets": 2,
        "absorption_chiller_mw": 0.0,
        "electric_chiller_mw": 10.0,
        "backup_boiler_mw": 18.0,
        "gas_handling": "keep_in_solution_reinject",
    }
    swapped = dict(asked, absorption_chiller_mw=10.0, electric_chiller_mw=18.0)
    assert request_mismatches(s5, [asked]) == []
    bad = request_mismatches(s5, [swapped])
    assert bad and "electric_chiller_mw=10" in bad[0]["detail"]
    assert (
        request_mismatches(
            "Why not use 2500 m wells with a heat pump instead of 3100 m?", [swapped]
        )
        == []
    )


def test_evaluate_design_ledger_args_hold_only_the_spec(tmp_path):
    from gemini_agent.tools import Session, build_tools

    s = Session(mode="auto", run_dir=tmp_path)
    t = {x.name: x for x in build_tools(s)}
    t["evaluate_design"].invoke({"well_depth_m": 3100.0})
    assert "s" not in s.ledger.facts[-1].args and s.ledger.facts[-1].args["well_depth_m"] == 3100.0


def test_claim_check_catches_denied_equipment_of_cited_design():
    from gemini_agent.ledger import FactLedger, provenance_check

    led = FactLedger()
    led.record(
        "evaluate_design",
        {},
        {
            "design_id": "b87d2a2dcc",
            "lcoe_eur_per_mwh": 45.1,
            "label": "2x doublet @ 3100 m (<= 300 m3/h), ElCh 20 MW, electric boiler 17.5 MW, "
            "DH 100/45 C",
        },
    )
    bad = provenance_check(
        "Design ID: b87d2a2dcc. No backup boiler (heating fully met by geothermal).", led
    )
    assert [c["type"] for c in bad["claim_issues"]] == ["attribute"]
    assert provenance_check("Design b87d2a2dcc needs no heat pump.", led)["claim_issues"] == []


def test_request_match_checks_the_presented_design_and_binding_return_temperature():
    from gemini_agent.request_check import parse_request, request_mismatches

    msg = "Prioritise low CO2 at reasonable cost. District heating return is 50 C. Go ahead with the design."  # noqa: E501
    assert parse_request(msg) == {"dh_return_temperature_c": 50.0}
    shown = [{"well_depth_m": 3100.0, "dh_return_temperature_c": 45.0}]
    bad = request_mismatches(msg, [], shown)
    assert (
        bad and "dh_return_temperature_c=50" in bad[0]["detail"] and "presented" in bad[0]["detail"]
    )
    assert request_mismatches(msg, [], [{"dh_return_temperature_c": 50.0}]) == []


def test_claim_check_reads_a_colon_intro_with_its_list_and_ignores_quoted_labels():
    from gemini_agent.ledger import provenance_check

    ans = (
        "The search for designs at 2500 meters with a heat pump shows that the best feasible "
        "design is:\n\n"
        '- **Design ID:** `a3100`\n- **Label:** "2x doublet @ 3100 m, ElCh 10 MW, gas reinjected"\n'
        "- **LCOE:** €44.32/MWh\n- **CO2 Emissions:** 3,120 t/year\n- **Geothermal Share of "
        "Heat:** 99.18%\n"
    )
    kinds = [c["type"] for c in provenance_check(ans, _two_depth_ledger())["claim_issues"]]
    assert kinds.count("attribute") == 2  # wrong depth and no heat pump


def test_what_if_evaluation_reports_changed_fields(tmp_path):
    from gemini_agent.tools import Session, build_tools

    s = Session(mode="auto", run_dir=tmp_path)
    t = {x.name: x for x in build_tools(s)}
    base = {"well_depth_m": 3100.0, "electric_chiller_mw": 10.0, "backup_boiler_mw": 18.0}
    t["evaluate_design"].invoke(base)
    out = json.loads(
        t["evaluate_design"].invoke(
            dict(base, well_depth_m=2500.0, heat_pump_mw=10.0, electric_chiller_mw=0.0)
        )
    )
    assert out["changed_vs_previous"]["electric_chiller_mw"] == [10.0, 0.0]
    assert "note" in out and not out["feasible"]


def test_overridden_tool_argument_is_not_a_fact():
    from gemini_agent.ledger import FactLedger, provenance_check

    led = FactLedger()
    led.record(
        "uncertainty_analysis",
        {"design_id": "x", "samples": 1000},
        {"samples": 60, "co2_t": {"P50": 3288.0}},
    )
    assert provenance_check("Uncertainty analysis (1,000 samples): CO2 P50 3,288 t.", led)[
        "unsupported"
    ] == [1000.0]
    assert provenance_check("Uncertainty analysis (60 samples): CO2 P50 3,288 t.", led)["passed"]


def test_small_counts_are_not_rescaled_into_thousands():
    from gemini_agent.ledger import FactLedger, provenance_check

    led = FactLedger()
    led.record(
        "uncertainty_analysis",
        {"samples": 1000},
        {"samples": 60, "probability_demand_fully_met": 1.0},
    )
    assert 1000.0 in provenance_check("Monte Carlo with 1,000 samples.", led)["unsupported"]
    led.record("evaluate_design", {}, {"cooling_supply_gwh": 23.74})
    assert provenance_check("Cooling: 23,740 MWh.", led)["passed"]


def test_infinite_values_in_a_fact_do_not_make_every_number_traceable():
    from gemini_agent.ledger import FactLedger, provenance_check

    led = FactLedger()
    led.record("search_designs", {}, {"lcoe_eur_per_mwh": 44.32, "payback_years": float("inf")})
    assert provenance_check("LCOE 44.32 EUR/MWh and 77.7 MW.", led)["unsupported"] == [77.7]


class FakeRouter:
    """Router stand-in: fixed decisions, the real reply policy."""

    model, temperature, threshold = "fake", 1.0, 0.8

    def __init__(self, *decisions):
        self.decisions = list(decisions)

    def classify(self, message, design_exists, previous=None):
        label, conf = self.decisions.pop(0)
        return {
            "label": label,
            "confidence": conf,
            "prompt_tokens": 120,
            "completion_tokens": 1,
            "latency_s": 0.1,
        }

    def reply(self, decision, mode, design_exists, answering):
        from gemini_agent.router import Router

        return Router.reply(self, decision, mode, design_exists, answering)


def test_router_answers_confident_off_topic_without_the_agent(tmp_path):
    r = _runner(tmp_path, [])  # the scripted model has no replies: any agent call would fail
    r.router = FakeRouter(("off_topic", 0.97))
    turn = r.ask("Who won the football match?")
    assert turn["llm_calls"] == 1 and turn["prompt_tokens"] == 120 and "outside" in turn["answer"]
    assert [e["agent"] for e in r.trace.events if e["type"] == "llm"] == ["router"]


def test_router_hands_unsure_turns_to_the_agent_and_its_question_reaches_agent_memory(tmp_path):
    r = _runner(tmp_path, [AIMessage("Designing now with a low-CO2 priority.")])
    r.router = FakeRouter(("incomplete", 0.95), ("design", 0.6))
    q = r.ask("Make us something for our district.")
    assert q["pending_question"] and "lowest cost" in q["answer"]
    t = r.ask("Low CO2 please.")  # below threshold -> full agent, which sees the earlier exchange
    assert (
        "low-CO2" in t["answer"] and t["router"]["label"] == "design" and not t["router"]["reply"]
    )
    msgs = r.agent.get_state(r.thread).values["messages"]
    assert any("Make us something" in str(m.content) for m in msgs)


def test_router_letter_parsing_and_temperature():
    from gemini_agent.router import _softmax, letter_logprobs

    lp = letter_logprobs(
        [
            {"token": "C", "logprob": 0.0},
            {"token": " D", "logprob": -21.0},
            {"token": "(C", "logprob": -26.0},
        ]
    )
    assert lp["C"] == 0.0 and lp["D"] == -21.0 and lp["A"] == -26.0
    assert _softmax(lp, 1.0)["C"] > 0.999
    assert _softmax(lp, 10.0)["C"] < 0.95  # a fitted temperature softens an overconfident model


def test_verify_design_runs_all_checks_in_one_call_and_records_each_fact(tmp_path):
    from gemini_agent.tools import Session, build_tools

    s = Session(mode="auto", run_dir=tmp_path)
    t = {x.name: x for x in build_tools(s)}
    did = json.loads(
        t["evaluate_design"].invoke(
            {"well_depth_m": 3100.0, "electric_chiller_mw": 11.0, "backup_boiler_mw": 18.0}
        )
    )["design_id"]
    out = json.loads(t["verify_design"].invoke({"design_id": did}))
    assert set(out["stress"]) == {"doublet_trip_on_peak_day", "demand_plus_10"}
    # both stress scenarios report a real pass/fail (demand growth reports "feasible", the trip "survives")  # noqa: E501
    assert all(isinstance(v["survives"], bool) for v in out["stress"].values())
    assert out["all_passed"] == (not out["failed"])
    assert out["gemini_solver"]["consistent"] and out["package"]["path"]
    tools_recorded = [f.tool for f in s.ledger.facts]
    for name in (
        "stress_test_design",
        "uncertainty_analysis",
        "sensitivity_analysis",
        "export_gemini_project",
        "save_design_package",
    ):
        assert name in tools_recorded


def test_chat_steps_dropdown_explains_each_step_and_the_verifier():
    from gemini_agent.ui.steps import annotate_turn, step_messages

    evs = [
        {
            "type": "llm",
            "agent": "agent",
            "prompt_tokens": 3900,
            "completion_tokens": 17,
            "latency_s": 9.8,
            "tool_calls": [{"name": "get_brief", "args": {}}],
        },
        {
            "type": "tool_end",
            "tool": "get_brief",
            "latency_s": 0.0,
            "output": '{"fact_id":"F1","site":"x"}',
        },
        {
            "type": "llm",
            "agent": "agent",
            "prompt_tokens": 4400,
            "completion_tokens": 90,
            "latency_s": 40,
            "tool_calls": [],
        },
    ]
    kids = step_messages(evs, "p1")
    assert (
        "Read the design brief" in kids[0]["metadata"]["title"]
        and "gd-ok" in kids[0]["metadata"]["title"]
    )
    assert "F1" in kids[0]["content"]
    assert kids[0]["metadata"]["status"] == "done"
    assert all(k["metadata"]["parent_id"] == "p1" for k in kids)
    turn = {
        "revised_from": {
            "provenance": {
                "claim_issues": [{"detail": "wrong depth"}],
                "unsupported": [],
                "unit_mismatches": [],
            }
        },
        "provenance": {"numbers_checked": 7, "passed": True},
    }
    out = annotate_turn(kids, turn, "p1")
    assert (
        "rejected by the verifier" in out[1]["metadata"]["title"]
        and "wrong depth" in out[1]["content"]
    )
    assert "Verifier · 7 numbers" in out[-1]["metadata"]["title"]


def test_replay_label_round_trip_and_turn_split():
    from gemini_agent.physics.design import DesignSpec
    from gemini_agent.ui.replay import spec_from_label, split_turns

    for spec in (
        DesignSpec(
            well_depth_m=3100,
            n_doublets=2,
            electric_chiller_mw=11,
            backup_boiler_mw=17.5,
            dh_return_temperature_c=50,
            gas_handling="keep_in_solution_reinject",
        ),
        DesignSpec(
            well_depth_m=2500,
            n_doublets=3,
            heat_pump_mw=10,
            absorption_chiller_mw=5,
            backup_boiler_mw=12,
            backup_fuel="electric",
        ),
    ):
        assert spec_from_label(spec.label()).label() == spec.label()
    llm = {"type": "llm"}
    tool = {"type": "tool_end"}
    turns = [{"llm_calls": 2}, {"llm_calls": 1}]
    assert [len(c) for c in split_turns([llm, tool, llm, llm, tool], turns)] == [3, 2]


def test_capacity_margin_scales_only_the_failing_part(tmp_path):
    from gemini_agent.tools import Session, build_tools

    s = Session(mode="auto", run_dir=tmp_path)
    t = {x.name: x for x in build_tools(s)}
    did = json.loads(
        t["evaluate_design"].invoke(
            {
                "well_depth_m": 3100.0,
                "electric_chiller_mw": 10.0,
                "backup_boiler_mw": 17.5,
                "dh_return_temperature_c": 45.0,
            }
        )
    )["design_id"]
    v = json.loads(t["verify_design"].invoke({"design_id": did}))
    assert v["failed"] == ["demand_plus_10"] and 'part="cooling"' in v["next"]
    out = json.loads(
        t["add_capacity_margin"].invoke({"design_id": did, "margin_pct": 15, "part": "cooling"})
    )
    assert "ElCh 11.5 MW" in out["label"] and "boiler 17.5 MW" in out["label"]


def test_custom_inputs_change_the_physics_and_are_validated(tmp_path):
    import pytest

    from gemini_agent.physics.design import DesignSpec
    from gemini_agent.service import custom_service, default_inputs

    d = default_inputs()
    assert d["geothermal_gradient_c_per_km"] == 30.0 and d["electricity_kg_per_kwh"] == 0.3
    spec = DesignSpec(
        well_depth_m=3100, n_doublets=2, electric_chiller_mw=11, backup_boiler_mw=17.5
    )
    base = custom_service().evaluate(spec)
    hot = custom_service({"geothermal_gradient_c_per_km": 33.0}).evaluate(spec)
    assert hot.kpis["geothermal_share_of_heat_pct"] >= base.kpis["geothermal_share_of_heat_pct"]
    clean = custom_service({"electricity_kg_per_kwh": 0.1}).evaluate(spec)
    assert clean.kpis["co2_t"] < base.kpis["co2_t"]
    half = tmp_path / "heat.csv"
    rows = ["date,heating_demand_MWth"] + [f"2027-01-{1 + i % 28:02d},10.0" for i in range(365)]
    half.write_text("\n".join(rows))
    with pytest.raises(ValueError):  # dates differ from the default cooling file
        custom_service(heating_csv=half)
    with pytest.raises(ValueError):
        custom_service({"max_flow_m3h_per_doublet": 400})


def test_inputs_panel_apply_reports_only_changes():
    from gemini_agent.service import EDITABLE_INPUTS, default_inputs
    from gemini_agent.ui.app import DEFAULT_COOL, DEFAULT_HEAT, apply_inputs

    d = default_inputs()
    state, chat, runner = apply_inputs(str(DEFAULT_HEAT), str(DEFAULT_COOL), *d.values())
    assert state["custom"] is False and runner is None and "Default" in chat[0]["content"]
    vals = dict(d, geothermal_gradient_c_per_km=33.0)
    state, chat, _ = apply_inputs(str(DEFAULT_HEAT), None, *(vals[k] for k in EDITABLE_INPUTS))
    assert (
        state["custom"]
        and state["values"] == {"geothermal_gradient_c_per_km": 33.0}
        and "33" in chat[0]["content"]
    )


def test_agent_tools_use_the_custom_inputs(tmp_path):
    from gemini_agent.service import custom_service
    from gemini_agent.tools import Session, build_tools

    s = Session(
        mode="auto", run_dir=tmp_path, svc=custom_service({"geothermal_gradient_c_per_km": 33.0})
    )
    t = {x.name: x for x in build_tools(s)}
    assert json.loads(t["reservoir_at_depth"].invoke({"depth_m": 2500}))["temperature_c"] == 94.5


def test_verifier_rejects_a_superseded_or_unverified_recommendation(tmp_path):
    r = _runner(tmp_path, [], mode="auto")
    from gemini_agent.tools import build_tools

    tools = {x.name: x for x in build_tools(r.session)}
    facts0 = len(r.session.ledger.facts)
    tools["search_designs"].invoke(
        {"objective": "balanced", "depths_m": [3100], "doublets": [2], "heat_pumps_mw": [0]}
    )
    best = r.session.current_design
    new = json.loads(
        tools["add_capacity_margin"].invoke(
            {"design_id": best, "margin_pct": 10, "part": "cooling"}
        )
    )
    issues = r._design_status(f"Design {best}: the search optimum.", facts0)
    assert [i["type"] for i in issues] == ["design", "design"] and new["design_id"] in issues[0][
        "detail"
    ]
    tools["verify_design"].invoke({"design_id": new["design_id"]})
    assert r._design_status(f"Design {new['design_id']}: verified.", facts0) == []


def test_verifier_rejections_become_persistent_lessons(tmp_path):
    from gemini_agent.lessons import MAX_LESSONS, lessons_for, record_lessons

    prov = {
        "claim_issues": [{"type": "request", "detail": "x"}, {"type": "comparison", "detail": "y"}],
        "unit_mismatches": [{"number": 1, "unit_written": "kwh", "fact_fields": ["f"]}],
        "unsupported": [],
    }
    lessons = lessons_for(prov)
    assert len(lessons) == 3 and lessons[0].startswith("When the user specifies a design")
    mem = tmp_path / "AGENTS.md"
    mem.write_text("# memory\n\n- (seed) Numbers must come from tools.\n")
    assert record_lessons(mem, lessons, "s1") == lessons
    assert record_lessons(mem, lessons, "s2") == []  # deduplicated
    assert mem.read_text().count("verifier rejection") == 3 and "(seed)" in mem.read_text()
    for i in range(MAX_LESSONS + 5):  # capped: oldest lessons go, the seed stays
        record_lessons(mem, [f"rule number {i}"], "s3")
    text = mem.read_text()
    assert text.count("verifier rejection") == MAX_LESSONS and "(seed)" in text
    assert "rule number 0" not in text


def test_runner_writes_a_lesson_when_a_draft_is_rejected(tmp_path):
    from gemini_agent.lessons import RULES

    wrong = {
        "well_depth_m": 3100,
        "n_doublets": 2,
        "electric_chiller_mw": 18,
        "backup_boiler_mw": 18,
        "gas_handling": "keep_in_solution_reinject",
    }
    r = _runner(
        tmp_path,
        [
            _call("evaluate_design", wrong),
            AIMessage("Done: 18 MW chillers."),
            AIMessage("Done again."),
        ],
        mode="auto",
    )
    turn = r.ask(
        "Evaluate 2 doublets at 3100 m with a 10 MW electric chiller and an 18 MW gas backup "
        "boiler, gas reinjected."
    )
    assert turn["revised_from"] and turn["memory_lessons"] == [RULES["request"]]
    mem = (tmp_path / "workspace" / "memory" / "AGENTS.md").read_text()
    assert "verifier rejection" in mem and "exactly that design" in mem
    # a second session in the same workspace starts with the lesson in its prompt
    r2 = _runner(tmp_path, [AIMessage("ok")], mode="auto")
    assert (
        "exactly that design"
        in json.loads((r2.run_dir / "meta.json").read_text())["memory_at_start"]
    )


def test_explicit_design_requests_get_an_evaluate_hint_and_vague_ones_do_not():
    from gemini_agent.request_check import design_hint

    h = design_hint(
        "Evaluate 2 doublets at 3100 m with a 10 MW electric chiller and an 18 MW gas "
        "backup boiler, gas reinjected."
    )
    assert h and "electric_chiller_mw=10" in h and "n_doublets=2" in h and "Do not ask" in h
    assert design_hint("Design a heating and cooling system for our district.") is None
    assert (
        design_hint("Why not use 2500 m wells with a heat pump instead of drilling to 3100 m?")
        is None
    )
    assert design_hint("District heating return is 50 C. Go ahead with the design.") is None


def test_objective_and_missing_priority_hints():
    from gemini_agent.request_check import missing_priority_hint, objective_hint

    assert "balanced" in objective_hint(
        "Prioritise low CO2 at reasonable cost. District heating return is 50 C."
    )
    assert "balanced" in objective_hint("Design the system. Balance cost and CO2.")
    assert "min_co2" in objective_hint("Give me the lowest CO2 design, whatever it costs.")
    assert "min_lcoe" in objective_hint("Find the cheapest system that meets demand.")
    assert objective_hint("What if a doublet trips on the coldest day?") is None
    vague = "Design a heating and cooling system for our district."
    assert missing_priority_hint(vague, False, "interactive")
    assert missing_priority_hint(vague, False, "auto") is None
    assert missing_priority_hint(vague, True, "interactive") is None
    assert (
        missing_priority_hint(
            "Design the system for the supplied demand. Balance cost and CO2.", False, "interactive"
        )
        is None
    )
    assert (
        missing_priority_hint("What will the weather be in Delft tomorrow?", False, "interactive")
        is None
    )


def test_number_regex_ranges_and_fact_citations():
    from gemini_agent.ledger import NUM_RE, FactLedger, provenance_check

    assert NUM_RE.findall("the limit is 50-300 m3/h") == ["50", "300"]
    assert NUM_RE.findall("-0.5 K and 2026-11-05") == ["-0.5", "2026", "11", "05"]
    led = FactLedger()
    led.record("well_performance", {"depth_m": 3100}, {"max_thermal_power_mw": 12.5})
    p = provenance_check("12.5 MW [F1] and 8.2 MW [F7]", led)
    kinds = [c["type"] for c in p["claim_issues"]]
    assert kinds == ["citation"] and "F7" in p["claim_issues"][0]["claim"]
    assert p["unsupported"] == [8.2] and not p["passed"]


def test_requested_design_and_missing_model_hint():
    from gemini_agent.physics.design import DesignSpec
    from gemini_agent.request_check import missing_model_hint, requested_design

    class Ev:
        def __init__(self, **kw):
            self.spec = DesignSpec(**kw)

    common = dict(well_depth_m=3100, n_doublets=1, backup_boiler_mw=31.5)
    asked = Ev(electric_chiller_mw=10, gas_handling="keep_in_solution_reinject", **common)
    bigger = Ev(
        electric_chiller_mw=12,
        gas_handling="keep_in_solution_reinject",
        dh_return_temperature_c=45,
        **common,
    )
    evs = {"aaaaaaaaaa": asked, "bbbbbbbbbb": bigger}
    s6 = (
        "Evaluate 1 doublet at 3100 m with a 10 MW electric chiller and a 31.5 MW gas backup "
        "boiler, gas reinjected."
    )
    assert requested_design(s6, evs, "bbbbbbbbbb")["design_id"] == "aaaaaaaaaa"
    r = requested_design("District heating return is 50 C. Go ahead.", {"bbbbbbbbbb": bigger})
    assert r["design_id"] is None
    assert r["args"]["dh_return_temperature_c"] == 50 and r["args"]["electric_chiller_mw"] == 12
    assert requested_design("What if a doublet trips?", evs) is None
    assert requested_design(s6, {}) is None
    q = "Could we store that summer surplus underground and use it in winter?"
    assert "Missing model" in missing_model_hint(q, ["heat_pump", "boiler"])
    assert "ht_ates_screening" in missing_model_hint(q, ["heat_pump", "ht_ates_screening"])
    assert missing_model_hint("Why not 2500 m wells with a heat pump?", ["heat_pump"]) is None


def test_revision_request_steers_to_the_requested_design():
    from gemini_agent.runner import _revision_request

    prov = {
        "unsupported": [],
        "unit_mismatches": [],
        "claim_issues": [{"type": "request", "claim": "Evaluate ...", "detail": "10 vs 12"}],
    }
    msg = _revision_request(prov, {"design_id": "aaaaaaaaaa", "label": "1x doublet", "args": None})
    assert "'Design ID: aaaaaaaaaa'" in msg and "Do not call tools" in msg
    msg = _revision_request(
        prov, {"design_id": None, "label": None, "args": {"well_depth_m": 3100}}
    )
    assert 'evaluate_design with exactly {"well_depth_m": 3100}' in msg


def test_default_site_weather_is_loaded_and_logged(tmp_path):
    r = _runner(tmp_path, [])
    assert r.session.svc.weather is not None and "ERA5" in r.session.svc.weather.source
    assert "site" in r.session.assumptions_used[0]["question"]
    assert "ERA5" in json.loads((r.run_dir / "meta.json").read_text())["weather"]


def test_comparison_hint_names_the_alternative():
    from gemini_agent.request_check import comparison_hint

    cur = {
        "well_depth_m": 3100.0,
        "n_doublets": 2,
        "heat_pump_mw": 0.0,
        "absorption_chiller_mw": 0.0,
        "electric_chiller_mw": 10.0,
        "backup_boiler_mw": 18.0,
        "gas_handling": "keep_in_solution_reinject",
    }
    h = comparison_hint(
        "Why not use 2500 m wells with a heat pump instead of drilling to 3100 m?", cur
    )
    assert "well_depth_m=2500" in h and "heat_pump_mw" in h and "compare_designs" in h
    assert "n_doublets=3" in comparison_hint("What about 3 doublets instead of 2?", cur)
    assert "absorption_chiller_mw" in comparison_hint(
        "Would an absorption chiller be cheaper?", cur
    )
    assert comparison_hint("What happens if one doublet trips on the coldest day?", cur) is None
    assert comparison_hint("Why not use 2500 m wells?", None) is None
    assert comparison_hint("Why not 3100 m?", cur) is None  # no change vs the current design


def test_unit_check_sees_per_year_suffix_and_forge_accepts_sloppy_json():
    from gemini_agent.forge import parse_spec
    from gemini_agent.ledger import FactLedger, unit_check

    led = FactLedger()
    led.record("evaluate_design", {}, {"cooling_supply_gwh": {"electric": 23.74}})
    assert unit_check("Cooling supply: 23.74 MWh/year", led)[0]["unit_written"] == "mwh"
    assert unit_check("Cooling supply: 23.74 GWh per year", led) == []
    spec = {"name": "x", "inputs": {"a": {"unit": "GWh"}}}
    assert parse_spec(spec) == spec
    assert parse_spec('{\\n  "name": "x", "inputs": {"a": {"unit": "GWh"}}\\n}') == spec
    assert parse_spec("```json\n" + json.dumps(spec) + "\n```") == spec
    assert parse_spec(str(spec)) == spec  # Python literal with single quotes


def test_unit_check_catches_scale_slips_on_brief_numbers_only():
    from gemini_agent.ledger import FactLedger, unit_check

    led = FactLedger()
    led.seed = {"demand": {"cooling_gwh": 23.743}, "prices": {"gas_eur_per_mwh": 45.0}}
    led.record(
        "evaluate_design",
        {},
        {"cooling_supply_gwh": {"electric": 23.74}, "dh_return_temperature_c": 45.0},
    )
    assert unit_check("Cooling capacity: 23.74 MWh (15% margin)", led)[0]["unit_written"] == "mwh"
    assert unit_check("gas at 45 EUR/MWh", led) == []  # a brief number, a different quantity
    assert unit_check("return 45 °C and 23.74 GWh of cooling", led) == []


def test_attribute_check_needs_a_clear_margin_over_the_named_design():
    from gemini_agent.ledger import FactLedger, claim_check

    led = FactLedger()
    led.record(
        "evaluate_design",
        {},
        {
            "design_id": "aaaaaaaaaa",
            "label": "2x doublet @ 3100 m, ElCh 11.5 MW",
            "lcoe_eur_per_mwh": 44.0,
            "co2_t_per_year": 2983.0,
            "geothermal_share_of_heat_pct": 99.18,
            "capex_meur": 49.17,
        },
    )
    led.record(
        "evaluate_design",
        {},
        {
            "design_id": "bbbbbbbbbb",
            "label": "3x doublet @ 3400 m, ElCh 10 MW",
            "lcoe_eur_per_mwh": 58.39,
            "co2_t_per_year": 2675.0,
            "geothermal_share_of_heat_pct": 99.5,
            "capex_meur": 61.0,
        },
    )
    led.record(
        "uncertainty_analysis",
        {"design_id": "aaaaaaaaaa"},
        {"co2_t": {"P10": 2685.0, "P90": 5376.0}, "lcoe_eur_per_mwh": {"P10": 41.0, "P90": 54.0}},
    )
    fine = (
        "Decisions:\n- 3100 m depth balances heat supply (99.2% geothermal share) [F1].\n"
        "- Uncertainty P10/P90 covers 41-54 EUR/MWh and 2685-5376 t CO2 [F3]."
    )
    assert claim_check(fine, led) == []
    wrong = "The 3100 m design: LCOE 58.39 EUR/MWh, 2675 t CO2, CAPEX 61.0 MEUR [F2]."
    assert [c["type"] for c in claim_check(wrong, led)] == ["attribute"]


def test_generate_model_tool_accepts_a_dict_spec():
    from gemini_agent.tools import Session, build_tools

    tool = next(
        t
        for t in build_tools(Session(run_dir=Path("runs/_test_forge")))
        if t.name == "generate_model"
    )
    out = json.loads(tool.invoke({"spec_json": {"name": "x_bad_spec"}}))
    assert out.get("ok") is False and out.get("stage") in (
        "parse",
        "validate",
    )  # schema accepted the dict


def test_exact_request_rejects_unrequested_deviations():
    from gemini_agent.request_check import parse_request, request_mismatches, requested_design

    s6 = (
        "Evaluate 1 doublet at 3100 m with a 10 MW electric chiller and a 31.5 MW gas backup "
        "boiler, gas reinjected."
    )
    req = parse_request(s6)
    assert req["backup_fuel"] == "gas"
    assert parse_request("a 5 MW electric backup boiler")["backup_fuel"] == "electric"
    base = dict(
        well_depth_m=3100.0,
        n_doublets=1,
        electric_chiller_mw=10.0,
        backup_boiler_mw=31.5,
        gas_handling="keep_in_solution_reinject",
        backup_fuel="gas",
        max_flow_m3h=300.0,
        dh_return_temperature_c=50.0,
        heat_pump_mw=0.0,
        absorption_chiller_mw=0.0,
    )
    assert request_mismatches(s6, [base]) == []
    fuel = request_mismatches(s6, [{**base, "backup_fuel": "electric"}])  # a stated field
    assert "backup_fuel=gas" in fuel[0]["detail"] and "electric" in fuel[0]["detail"]
    slipped = {**base, "max_flow_m3h": 100.0}  # a field the user never mentioned
    issue = request_mismatches(s6, [slipped])
    assert issue and "max_flow_m3h=100" in issue[0]["detail"] and "default" in issue[0]["detail"]
    dev40 = request_mismatches(s6, [{**base, "dh_return_temperature_c": 40.0}])
    assert "dh_return_temperature_c=40" in dev40[0]["detail"]

    class Ev:
        def __init__(self, **kw):
            from gemini_agent.physics.design import DesignSpec

            self.spec = DesignSpec(**kw)

    r = requested_design(s6, {"aaaaaaaaaa": Ev(**slipped)})
    assert r["design_id"] is None and r["args"]["max_flow_m3h"] == 300.0
    assert r["args"]["backup_fuel"] == "gas"
    assert requested_design(s6, {"bbbbbbbbbb": Ev(**base)})["design_id"] == "bbbbbbbbbb"


def test_percentile_quoted_as_design_value_is_flagged():
    from gemini_agent.ledger import FactLedger, provenance_check

    led = FactLedger()
    led.record(
        "evaluate_design",
        {},
        {"design_id": "aaaaaaaaaa", "lcoe_eur_per_mwh": 44.09, "co2_t_per_year": 2983.0},
    )
    led.record("sensitivity_analysis", {}, {"rows": [{"lcoe_high": 46.3}]})  # a near miss
    led.record(
        "uncertainty_analysis",
        {"design_id": "aaaaaaaaaa"},
        {"lcoe_eur_per_mwh": {"P10": 41.51, "P50": 46.23, "P90": 54.04}, "co2_t": {"P50": 3391.0}},
    )
    bad = provenance_check(
        "Design aaaaaaaaaa\nLCOE: 46.23 EUR/MWh [F3]\nCO2: 3,391 t/year [F3]", led
    )
    kinds = [c["type"] for c in bad["claim_issues"]]
    assert kinds == ["percentile", "percentile"] and "P50" in bad["claim_issues"][0]["detail"]
    ok = provenance_check(
        "LCOE 44.09 EUR/MWh [F1]; Monte Carlo P50 46.23, P10-P90 41.5 to 54.0 EUR/MWh [F3]", led
    )
    assert ok["claim_issues"] == []


def test_revision_steering_tells_the_model_what_to_copy():
    from gemini_agent.runner import _revision_request

    prov = {
        "unsupported": [],
        "unit_mismatches": [],
        "claim_issues": [{"type": "request", "claim": "Evaluate ...", "detail": "10 vs 12"}],
    }
    msg = _revision_request(
        prov,
        {
            "design_id": "aaaaaaaaaa",
            "label": "1x doublet @ 3100 m, ElCh 10 MW",
            "args": None,
            "fact": {
                "fid": "F7",
                "lcoe": 43.99,
                "co2": 9279.0,
                "share": 71.7,
                "plus10": ("F9", False),
            },
            "avoid": ["bbbbbbbbbb"],
        },
    )
    assert "'Design ID: aaaaaaaaaa'" in msg and "[F7]" in msg and "9,279" in msg
    assert "FAILS [F9]" in msg and "Do not present bbbbbbbbbb" in msg


def test_requested_design_prefers_a_verified_match():
    from gemini_agent.physics.design import DesignSpec
    from gemini_agent.request_check import requested_design
    from gemini_agent.runner import _revision_request

    class Ev:
        def __init__(self, **kw):
            self.spec = DesignSpec(**kw)

    cand = Ev(well_depth_m=3100, electric_chiller_mw=10, backup_boiler_mw=17.5)  # DH 50 default
    good = Ev(well_depth_m=3100, electric_chiller_mw=11.5, backup_boiler_mw=17.5)
    evs = {"cccccccccc": cand, "dddddddddd": good}
    text = "Prioritise low CO2 at reasonable cost. District heating return is 50 C."
    r = requested_design(text, evs, None, {"dddddddddd"})
    assert r["design_id"] == "dddddddddd" and r["verified"] is True
    r = requested_design(text, evs, None, set())
    assert r["design_id"] == "cccccccccc" and r["verified"] is False
    prov = {
        "unsupported": [],
        "unit_mismatches": [],
        "claim_issues": [{"type": "request", "claim": text, "detail": "45 vs 50"}],
    }
    msg = _revision_request(prov, r)
    assert "never verified" in msg and "verify_design" in msg and "Design ID: cccccccccc" not in msg
