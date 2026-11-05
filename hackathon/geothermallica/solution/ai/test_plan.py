"""The code plan's trace, the repair loop (with a fake model), optimiser front and checker rules (i) and (j), without Ollama:
python -m pytest ai/test_plan.py"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import AI03_agent as agent  # noqa: E402
import AI03_moves as moves  # noqa: E402
import AI03_plan as planner  # noqa: E402
import AI04_check as checker  # noqa: E402

BRIEF_F = ("District with 30 MW peak heating and 10 MW peak cooling, supply 100 C and 20 C, reservoir at 2500 m, ESP at 800 m. "
           "How many doublets, what return, boiler needed?")
PLANS = {}


def fake_chat(replies):
    """A stand-in for AI01_log.chat: returns the next scripted reply with an empty token record."""
    def chat(messages, **options):
        text = next(replies)
        return ({"role": "assistant", "content": text, "tool_calls": []},
                {"messages": messages, "response": text, "prompt_eval_count": 0, "eval_count": 0, "total_duration": 0})
    return chat


def plan(brief):
    if brief not in PLANS:
        PLANS[brief] = planner.plan(brief)
    return PLANS[brief]


def trace(out):
    return next(r["result"] for r in out if r["name"] == "design_iterations")


def opt(out):
    return next(r["result"] for r in out if r["name"] == "optimise_point")


def answer(it, reasoning):
    return {"n_doublets": it["n_doublets"], "t_return_c": it["t_return_c"], "reasoning": reasoning}


class TestPlan(unittest.TestCase):
    def test_brief_a_trace(self):
        it = trace(plan(agent.BRIEF))
        self.assertEqual(it["tried"], 18)
        self.assertEqual(it["chosen"], "2 doublets at 56.5 C")   # the optimiser's cheapest feasible return, below the 60 C sweep step
        self.assertEqual(it["moves"], 0)
        self.assertEqual([s["verdict"] for s in it["steps"]].count("chosen"), 1)
        self.assertEqual(it["optimised"], len([s for s in it["steps"] if s.get("front")]))

    def test_front_nondominated_and_feasible(self):
        o = opt(plan(agent.BRIEF))
        front = o["front"]
        self.assertTrue(front)
        for a in front:
            self.assertTrue(a["feasible"])
            for b in front:
                if a is not b:
                    self.assertFalse(b["lcoh_EUR_MWh"] <= a["lcoh_EUR_MWh"] and b["co2_total_kt"] < a["co2_total_kt"], (a, b))
                    self.assertFalse(b["lcoh_EUR_MWh"] < a["lcoh_EUR_MWh"] and b["co2_total_kt"] <= a["co2_total_kt"], (a, b))
        self.assertEqual(o["best_lcoh"]["lcoh_EUR_MWh"], min(p["lcoh_EUR_MWh"] for p in front))
        self.assertTrue(o["best_lcoh"]["feasible"])
        bp, bl = o["best_on_priority"], o["best_lcoh"]   # brief A states no priority: cheapest heat, then the gas rule
        self.assertEqual((bp["n"], bp["t_return_c"], bp["esp_depth_m"]), (bl["n"], bl["t_return_c"], bl["esp_depth_m"]))
        self.assertEqual((bl["gas_handling"], bp["gas_handling"]), ("engine", "reinject"))
        self.assertIn("below the 1 % rule", o["gas_choice"])

    def test_priority_parse(self):
        self.assertEqual(checker.brief_priority(agent.BRIEF), "lcoh")
        self.assertEqual(checker.brief_priority("District, 30 MW peak heating, lowest CO2 please"), "co2")
        self.assertEqual(checker.brief_priority("The cheapest heat for a 20 MW peak heating town"), "lcoh")
        self.assertFalse(checker.brief_stated_priority(agent.BRIEF))
        self.assertTrue(checker.brief_stated_priority("cheapest heat for 20 MW"))

    def test_rule_j(self):
        out = plan(agent.BRIEF)
        o, it = opt(out), trace(out)
        row = o["best_on_priority"]
        good = {"n_doublets": row["n"], "t_return_c": row["t_return_c"],
                "chosen_design": {"n": row["n"], "t_return_c": row["t_return_c"], "esp_depth_m": row["esp_depth_m"],
                                  "gas_handling": row["gas_handling"]},
                "trade_off": f"LCoH {row['lcoh_EUR_MWh']} EUR/MWh, CO2 {row['co2_total_kt']} kt with the "
                             f"{planner.GAS_WORDS[row['gas_handling']]}, {row['versus']} [C]"}
        self.assertEqual(checker.check_choice(good, o, stated=False), [])
        nogas = copy.deepcopy(good)
        nogas["trade_off"] = f"LCoH {row['lcoh_EUR_MWh']} EUR/MWh, CO2 {row['co2_total_kt']} kt, {row['versus']} [C]"
        self.assertTrue(any("gas option" in p for p in checker.check_choice(nogas, o, False)))
        off = copy.deepcopy(good)
        off["chosen_design"]["t_return_c"] = 60.0   # not a front row
        self.assertTrue(any(p.startswith("(j)") and "not a row" in p for p in checker.check_choice(off, o, False)))
        wrong = copy.deepcopy(good)
        wrong["trade_off"] = f"At 99.9 EUR/MWh and {row['co2_total_kt']} kt CO2 [C]."
        self.assertTrue(any("does not quote" in p for p in checker.check_choice(wrong, o, False)))
        self.assertTrue(any("missing" in p for p in checker.check_choice({"trade_off": "x [C]"}, o, False)))
        # the answer may follow another front row: rule (i) accepts it when the trace holds that row
        other = next((p for p in o["front"] if p is not row and p != row), None)
        if other:
            ans = {"n_doublets": other["n"], "t_return_c": other["t_return_c"], "reasoning": [f"Tried {it['tried']} candidates [C]."]}
            self.assertFalse(any("design_iterations chose" in p for p in checker.check_iterations(it, ans, ans["reasoning"], out)))

    def test_brief_f_model_move(self):
        """The model picks the ESP move with its own value (900 m is not enough, then 1100 m): by model, two moves."""
        replies = iter(['{"move": "free gas at ESP intake", "value": 900, "why": "intake 44.7 bar is below the 62.5 bar bubble point"}',
                        '{"move": "free gas at ESP intake", "value": 1100, "why": "900 m still fails, so 1100 m"}'])
        exchanges, records = [], []
        out = planner.plan(BRIEF_F, chat=fake_chat(replies), records=records, exchanges=exchanges)
        it = trace(out)
        moves = [s for s in it["steps"] if s.get("move")]
        self.assertEqual([(s["by"], s["from"], s["to"], s["verdict"]) for s in moves],
                         [("model", 800, 900, "still failing"), ("model", 900, 1100, "repaired")])
        self.assertEqual(moves[0]["why"], "intake 44.7 bar is below the 62.5 bar bubble point")
        self.assertEqual((it["moves"], it["model_moves"], it["code_moves"], it["stopped"]), (2, 2, 0, False))
        self.assertEqual(len(records), 2)
        self.assertEqual([m["role"] for m in exchanges], ["user", "assistant"] * 2)
        self.assertIn("allowed 850 to 1250 m", exchanges[0]["content"])
        checks = [r for r in out if r["name"] == "checks"]
        self.assertEqual(checks[0]["args"]["esp_depth_m"], 800)
        self.assertGreater(checks[0]["result"]["n_fail"], 0)
        self.assertEqual(checks[-1]["args"]["esp_depth_m"], 1100)
        self.assertEqual(checks[-1]["result"]["n_fail"], 0)
        later = [r for r in out if r["name"] in ("heating_year", "economics", "layout_compare", "gas_point", "lifetime_point")]
        self.assertTrue(later and all(r["args"].get("esp_depth_m") == 1100 for r in later))
        good = answer(it, [f"Tried {it['tried']} candidates [C].", "Model's move left a violation, ESP 800 to 900 m, checks 16/17 [C].",
                           "Model's move repaired a violation, ESP 900 to 1100 m, checks 17/17 [C]."])
        self.assertEqual(checker.check_iterations(it, good, good["reasoning"], out), [])
        bad = answer(it, [f"Tried {it['tried']} candidates [C]."])
        self.assertTrue(any("the model made the move" in p for p in checker.check_iterations(it, bad, bad["reasoning"], out)))
        msg = planner.plan_message(BRIEF_F, out)
        self.assertIn("Model's move left a violation: free gas at ESP intake, 45.2 bar against limit 62.5 bar, so the ESP moved from 800 to 900 m, "
                      "checks now 16/17 [C].", msg)
        self.assertIn("Model's move repaired a violation: free gas at ESP intake", msg)
        self.assertIn("staggered over days", msg)   # the outage choice and the N-1 row reach the model
        self.assertIn("one doublet out on the coldest day leaves 31.0 MW (pass)", msg)
        outage = next(line for line in msg.splitlines() if line.startswith("Outages"))
        self.assertLessEqual(len(outage.split(": ", 1)[1].split()), 30)
        self.assertTrue(any(line.startswith("- Both doublets out at once") for line in msg.splitlines()))
        self.assertTrue(all(len(line.split(": ", 1)[1].split()) <= 30 for line in msg.splitlines() if line.startswith("Violation")))

    def test_brief_f_code_fallback(self):
        """Two replies that are no valid move (prose, then a value outside the range): the code takes the suggested move."""
        replies = iter(["I would move the ESP deeper.", '{"move": "free gas at ESP intake", "value": 2000, "why": "deeper"}'])
        out = planner.plan(BRIEF_F, chat=fake_chat(replies))
        it = trace(out)
        kinds = [(s["verdict"], s["by"]) for s in it["steps"] if s.get("by")]
        self.assertEqual(kinds, [("invalid reply", "model"), ("invalid reply", "model"), ("repaired", "code")])
        move = next(s for s in it["steps"] if s.get("move"))
        self.assertEqual((move["from"], move["to"]), (800, 1100))
        reasons = [s["reason"] for s in it["steps"] if s["verdict"] == "invalid reply"]
        self.assertIn("not a JSON object", reasons[0])
        self.assertIn("outside the allowed 850 to 1250 m", reasons[1])
        self.assertEqual((it["moves"], it["model_moves"], it["code_moves"]), (1, 0, 1))
        self.assertEqual(next(r for r in reversed(out) if r["name"] == "checks")["result"]["n_fail"], 0)

    def test_brief_f_stop(self):
        """A stop is honoured: no move, the design keeps failing, the trace and the checker say so."""
        out = planner.plan(BRIEF_F, chat=fake_chat(iter(['{"move": "stop", "why": "leave it"}'])))
        it = trace(out)
        self.assertEqual((it["moves"], it["stopped"]), (0, True))
        self.assertEqual([s["verdict"] for s in it["steps"] if s.get("by")], ["stopped"])
        before = [r for r in out[:next(i for i, r in enumerate(out) if r["name"] == "optimise_point")] if r["name"] == "checks"]
        self.assertGreater(before[-1]["result"]["n_fail"], 0)   # the design the model stopped on still fails
        self.assertEqual(next(s for s in it["steps"] if s["verdict"] == "stopped")["checks_after"],
                         f"{before[-1]['result']['n_pass']}/{before[-1]['result']['n_rows']}")
        good = answer(it, [f"Tried {it['tried']} candidates [C]."])
        self.assertEqual(checker.check_iterations(it, good, good["reasoning"], out), [])   # 'stopped' explains a failing design
        self.assertIn("The model stopped the repair at checks", planner.plan_message(BRIEF_F, out))

    def test_gas_choice_line(self):
        """The 1 % rule picks reinjection for brief A; the plan says it, the engine is the rejected alternative, the checker
        holds the answer to the rule's option and to the economics priced with it."""
        out = plan(agent.BRIEF)
        it = trace(out)
        n, t = it["n_doublets"], it["t_return_c"]
        gc = planner.gas_record(out)
        self.assertEqual((gc["gas_handling"], gc["rule_choice"], it["gas_handling"]), ("reinject", "reinject", "reinject"))
        self.assertLess(gc["lcoh_penalty_pct"], gc["lcoh_penalty_max_pct"])
        ri, en = planner.economics_of(out, n, t, "reinject"), planner.economics_of(out, n, t, "engine")
        self.assertGreater(ri["associated_gas_compression_GWh"], 0)
        self.assertLess(ri["co2_total_kt"], en["co2_total_kt"])
        msg = planner.plan_message(agent.BRIEF, out)
        self.assertIn("Gas choice: reinject the associated gas: CO2 9.43 -> 5.49 kt for +0.13 EUR/MWh (+0.2 %), below the 1 % "
                      "rule, permit assumed [C, A].", msg)
        self.assertIn(f"with {n} doublets {ri['lcoh_EUR_MWh']} EUR/MWh", msg)   # the design's LCoH is the reinjection one
        line = next(x[2:] for x in msg.splitlines() if x.startswith("- Burning the associated gas in the gas engine"))
        self.assertIn(f"-> {en['co2_total_kt']} kt", line)
        self.assertFalse(any(x.startswith("- Reinjecting") for x in msg.splitlines()))
        alts = [x[2:] for x in msg.splitlines() if x.startswith("- ")]
        self.assertLessEqual(len(alts), 7)
        self.assertEqual(checker.check_alternatives(alts, {r["name"] for r in out}), [])
        row = opt(out)["best_on_priority"]
        ans = {**answer(it, [f"Tried {it['tried']} candidates [C].", gc["sentence"]]), "rejected_alternatives": alts,
               "lcoh_EUR_MWh": ri["lcoh_EUR_MWh"], "co2_total_kt": ri["co2_total_kt"],
               "chosen_design": {"n": row["n"], "t_return_c": row["t_return_c"], "esp_depth_m": row["esp_depth_m"], "gas_handling": "reinject"}}
        self.assertEqual(checker.check_gas_choice(ans, alts, out), [])
        self.assertFalse([p for p in checker.check(ans, "", out, agent.BRIEF) if p.startswith(("(c)", "(h)"))
                          or "lcoh_EUR_MWh=" in p or "co2_total_kt=" in p])
        engine_numbers = {**ans, "lcoh_EUR_MWh": en["lcoh_EUR_MWh"]}   # the design's LCoH with the wrong gas option
        self.assertTrue(any("lcoh_EUR_MWh=" in p for p in checker.check(engine_numbers, "", out, agent.BRIEF)))
        wrong = {**ans, "chosen_design": {**ans["chosen_design"], "gas_handling": "engine"}}
        self.assertTrue(any("gas rule chose" in p for p in checker.check_gas_choice(wrong, alts, out)))
        bad = [a.replace(str(en["co2_total_kt"]), "7.77") if a == line else a for a in alts]
        self.assertTrue(any("7.77 " in p for p in checker.check_gas_choice(ans, bad, out)))
        self.assertTrue(checker.check_gas_choice(ans, [a for a in alts if a != line], out))   # priced but not named

    def test_parse(self):
        options = moves.menu({"n_doublets": 2, "t_return_c": 56.25, "esp_depth_m": 800}, {},
                             {"14 free gas at ESP intake [D]": "min intake 44.7 bar (limit >= 62.5 bar) -> FAIL", "summary": ""}, 3)
        self.assertEqual([(o["key"], o["now"], o["new"], o["cap"]) for o in options], [("esp_depth_m", 800, 1100, 1250)])
        self.assertEqual(moves.parse('{"move": "esp_depth_m", "value": null, "why": "w"}', options)[1], 1100)
        self.assertEqual(moves.parse('{"move": "free gas at ESP intake", "value": 1230, "why": "w"}', options)[1], 1250)   # rounded to 50 m
        self.assertIsNone(moves.parse('{"move": "free gas at ESP intake", "value": 800, "why": "w"}', options)[0])
        self.assertIsNone(moves.parse('{"move": "spacing_m", "value": 1000, "why": "w"}', options)[0])
        self.assertEqual(moves.parse("no json here", options)[0], None)

    def test_rule_i_wrong_tried(self):
        out = copy.deepcopy(plan(agent.BRIEF))
        it = trace(out)
        good = answer(it, [f"Tried {it['tried']} candidate designs, rejected {it['rejected']} [C]."])
        self.assertEqual([p for p in checker.check_iterations(it, good, good["reasoning"], out)], [])
        it["tried"] = 17
        bad = checker.check_iterations(it, good, good["reasoning"], out)
        self.assertTrue(any(p.startswith("(i)") and "tried=17" in p for p in bad), bad)

    def test_rule_i_verdict_recomputed(self):
        out = copy.deepcopy(plan(agent.BRIEF))
        it = trace(out)
        it["steps"][0]["reason"] = "meets the rule"   # 1 doublet at 40 C is 35 % short at the peak
        p = checker.check_iterations(it, answer(it, ["Tried 18 candidates [C]."]), ["Tried 18 candidates [C]."], out)
        self.assertTrue(any("1 doublet at 40 C" in x for x in p), p)

    def test_brief_esp_parse(self):
        self.assertEqual(checker.brief_esp(BRIEF_F), 800.0)
        self.assertIsNone(checker.brief_esp(agent.BRIEF))
        self.assertIsNone(checker.brief_esp("heat pump, reservoir 2500 m"))


if __name__ == "__main__":
    unittest.main()


class SplitJoined(unittest.TestCase):
    def test_joined_reasoning_is_split(self):
        import AI03_agent as agent
        one = "; ".join(f"item {i} with {i} MW [C]" for i in range(10))
        j = agent.split_joined({"reasoning": [one, "short item 2 MW [C]"]})
        self.assertEqual(len(j["reasoning"]), 11)
        self.assertEqual(j["code_split"], 1)

    def test_single_tag_string_is_not_split(self):
        import AI03_agent as agent
        s = "GEMINI's solver re-ran 3 days: a; b; c; d " + "word " * 30 + "[C]"
        self.assertEqual(len(agent.split_joined({"reasoning": [s]})["reasoning"]), 1)


class Tidy(unittest.TestCase):
    def test_verdict_moved_and_engine_added(self):
        import AI03_agent as agent
        e = {"co2_total_kt": 9.429, "lcoh_EUR_MWh": 61.8, "gas_handling": "engine"}
        r = {"co2_total_kt": 5.492, "lcoh_EUR_MWh": 61.93, "associated_gas_compression_GWh": 0.08, "gas_handling": "reinject"}
        results = [{"name": "economics", "args": {"n_doublets": 2, "t_return_c": 56.5, "gas_handling": "engine"}, "result": e},
                   {"name": "economics", "args": {"n_doublets": 2, "t_return_c": 56.5, "gas_handling": "reinject"}, "result": r},
                   {"name": "gas_choice", "args": {}, "result": {"gas_handling": "reinject"}}]
        j = {"n_doublets": 2, "t_return_c": 56.5, "reasoning": ["GEMINI's solver re-ran 3 days: ESP head within 0.2 bar [C]", "2 doublets [C]"],
             "rejected_alternatives": ["1 doublet leaves 3 GWh unmet [C]"]}
        j = agent.tidy(j, results)
        self.assertTrue(j["gemini_verification"].startswith("GEMINI's solver"))
        self.assertEqual(len(j["reasoning"]), 1)
        self.assertIn("gas engine instead of reinjecting", j["rejected_alternatives"][-1])
        self.assertTrue(j["rejected_alternatives"][-1].endswith("; code]."))
