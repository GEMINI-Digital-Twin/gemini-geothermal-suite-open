"""Unit tests for the Data Upload sample CSV column helper."""

import unittest

from gemini_interface.blueprint.app_tagbrowser.routes import (
    SAMPLE_CSV_TIMESTAMP,
    build_sample_csv,
    sample_csv_columns,
)


class _Unit:
    """Minimal unit stub with a measured tag map."""

    def __init__(self, measured):
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

    def test_sample_row_uses_semicolon_and_placeholder_zeros(self):
        """The sample file is a semicolon CSV with one placeholder data row."""
        csv_text = build_sample_csv(["Timestamp", "EXT_A", "EXT_B"])

        self.assertEqual(
            csv_text,
            "Timestamp;EXT_A;EXT_B\n" + SAMPLE_CSV_TIMESTAMP + ";0;0\n",
        )
