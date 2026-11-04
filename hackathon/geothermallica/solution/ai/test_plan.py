"""The code plan's design_iterations trace and repair move, and checker rule (i), without Ollama: python -m pytest ai/test_plan.py"""
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


def answer(it, reasoning):
    return {"n_doublets": it["n_doublets"], "t_return_c": it["t_return_c"], "reasoning": reasoning}


class TestPlan(unittest.TestCase):
    def test_brief_a_trace(self):
        it = trace(plan(agent.BRIEF))
        self.assertEqual(it["tried"], 18)
        self.assertEqual(it["chosen"], "2 doublets at 60 C")
        self.assertEqual(it["moves"], 0)
        self.assertEqual([s["verdict"] for s in it["steps"]].count("chosen"), 1)

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
