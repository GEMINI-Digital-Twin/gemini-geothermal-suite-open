"""Outage windows, the N-1 check row and the unplanned-outage cost: python -m pytest geo/test_outage.py"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geo import outage, year  # noqa: E402

DESIGN = dict(peak_heat_MW=30.0, depth_m=2500.0, esp_depth_m=1100.0)   # the challenge design: 2 doublets at a 56.5 C return


class TestOutage(unittest.TestCase):
    def test_windows_35_days_no_overlap(self):
        for n in (1, 2, 3):
            w = outage.windows(n)
            spans = sorted((pd.Timestamp(a), pd.Timestamp(b)) for a, b in w.values())
            self.assertEqual(len(spans), n)
            for a, b in spans:
                self.assertEqual((b - a).days + 1, outage.DAYS)
            for (_, b1), (a2, _) in zip(spans, spans[1:]):
                self.assertLess(b1, a2)

    def test_windows_in_low_demand(self):
        h = outage.demand()
        low = h.rolling(outage.DAYS).sum().quantile(0.25)   # a quarter of all 35-day windows are cheaper than this
        for a, b in outage.windows(3).values():
            self.assertLessEqual(h[a:b].sum(), low)

    def test_all_at_once_costs_more_backup(self):
        s = outage.summary(2, 56.5, **DESIGN)
        self.assertGreater(s["all_at_once_backup_GWh"], s["staggered_backup_GWh"])
        self.assertGreater(s["all_at_once_extra_gas_MEUR"], 0)

    def test_n_minus_1_row_and_summary(self):
        rows = year.checks(2, 56.5, 30.0, 10.0, depth_m=2500.0, esp_depth_m=1100.0)
        self.assertEqual(len(rows), 17)
        n1 = rows[-1]
        self.assertEqual(n1["name"], "one doublet out on the coldest day [C]")
        self.assertEqual(n1["status"], "pass")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai"))
        import AI02_tools as tools
        self.assertEqual(tools.checks(2, 56.5, 30.0, 10.0, 2500.0, 1100.0)["summary"], "17/17 pass (13 computed + 4 declared rows)")

    def test_unplanned_positive(self):
        u = outage.unplanned(2, 56.5, **DESIGN)
        self.assertGreater(u["gas_GWh"], 0)
        self.assertGreater(u["co2_kt"], 0)
        self.assertGreater(u["cost_MEUR"], 0)
        self.assertEqual(u["start"], "2027-01-25")   # the coldest week holds the 28 Jan peak


if __name__ == "__main__":
    unittest.main()
