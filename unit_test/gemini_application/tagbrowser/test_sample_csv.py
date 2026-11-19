"""Unit tests for the Data Upload sample CSV column helper."""

import unittest

from gemini_application.tagbrowser.sample_csv import (
    SAMPLE_CSV_TIMESTAMP,
    SAMPLE_CSV_VALUE_MAX,
    SAMPLE_CSV_VALUE_MIN,
    build_sample_csv,
    sample_csv_columns,
)


class _Unit:
    """Minimal unit stub with a measured tag map."""

    def __init__(self, measured, name="unit"):
        self.name = name
        self.tags = {"measured": measured}


class TestSampleCsvColumns(unittest.TestCase):
    """Column order, empty external names, and duplicate names."""

    def test_order_skip_empty_and_dedupe(self):
        """Keep first-seen external names and the last entry of each tag."""
        units = [
            _Unit(
                {
                    "annulus_pressure": ["EXT_A"],
                    "unmapped_pressure": [""],
                    "empty_tag": [],
                }
            ),
            _Unit(
                {
                    "shared_flow": ["EXT_A"],
                    "wellhead_pressure": ["OLD_NAME", "EXT_B"],
                    "blank_tag": ["   "],
                }
            ),
        ]

        columns = sample_csv_columns(units)

        self.assertEqual(columns, ["Timestamp", "EXT_A", "EXT_B"])

    def test_sample_contains_one_month_of_daily_rows(self):
        """The sample file has one daily row of random numbers for each tag."""
        csv_text = build_sample_csv(["Timestamp", "EXT_A", "EXT_B"])
        lines = csv_text.strip().split("\n")

        self.assertEqual(lines[0], "Timestamp;EXT_A;EXT_B")
        self.assertEqual(len(lines), 1 + 31)
        self.assertTrue(lines[1].startswith(SAMPLE_CSV_TIMESTAMP + ";"))
        self.assertTrue(lines[-1].startswith("2026-01-31 00:00:00;"))

        # -- each tag value is a random number in the example range ---------
        values = []
        for line in lines[1:]:
            for raw_value in line.split(";")[1:]:
                number = float(raw_value)
                self.assertGreaterEqual(number, SAMPLE_CSV_VALUE_MIN)
                self.assertLessEqual(number, SAMPLE_CSV_VALUE_MAX)
                values.append(number)
        self.assertGreater(len(set(values)), 1)
        self.assertNotIn("#", csv_text)
