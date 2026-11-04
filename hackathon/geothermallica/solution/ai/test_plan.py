"""The code plan's trace, repair move, optimiser front and checker rules (i) and (j), without Ollama: python -m pytest ai/test_plan.py"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import AI03_agent as agent  # noqa: E402
import AI03_plan as planner  # noqa: E402
import AI04_check as checker  # noqa: E402

BRIEF_F = ("District with 30 MW peak heating and 10 MW peak cooling, supply 100 C and 20 C, reservoir at 2500 m, ESP at 800 m. "
           "How many doublets, what return, boiler needed?")
PLANS = {}


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
        self.assertEqual(o["best_on_priority"], o["best_lcoh"])   # brief A states no priority: cheapest heat is the default

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
                "chosen_design": {"n": row["n"], "t_return_c": row["t_return_c"], "esp_depth_m": row["esp_depth_m"]},
                "trade_off": f"LCoH {row['lcoh_EUR_MWh']} EUR/MWh, CO2 {row['co2_total_kt']} kt, {row['versus']} [C]"}
        self.assertEqual(checker.check_choice(good, o, stated=False), [])
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

    def test_brief_f_repair(self):
        out = plan(BRIEF_F)
        moves = [s for s in trace(out)["steps"] if s.get("move")]
        self.assertTrue(any(s["key"] == "esp_depth_m" and s["from"] == 800 and s["to"] == 1100 for s in moves))
        checks = [r for r in out if r["name"] == "checks"]
        self.assertEqual(checks[0]["args"]["esp_depth_m"], 800)
        self.assertGreater(checks[0]["result"]["n_fail"], 0)
        self.assertEqual(checks[-1]["args"]["esp_depth_m"], 1100)
        self.assertEqual(checks[-1]["result"]["n_fail"], 0)
        later = [r for r in out if r["name"] in ("heating_year", "economics", "layout_compare", "gas_point", "lifetime_point")]
        self.assertTrue(later and all(r["args"].get("esp_depth_m") == 1100 for r in later))

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
