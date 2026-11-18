"""Unit tests for the CSV database driver."""

import os
import tempfile
import unittest

from gemini_framework.database.connector.csv_driver import CSVDriver


class TestCSVDriver(unittest.TestCase):
    """CSV parsing for a semicolon-separated upload file."""

    def test_connect_reads_timestamp_and_tag_column(self):
        """The first row is the header and each later row is one timestamp."""
        contents = "Timestamp;EXT_A\n2026-01-01 00:00:00;1.5\n"

        # -- write a temporary sample and read it back ----------------------
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = os.path.join(tmp_dir, "data.csv")
            with open(csv_path, "w", encoding="utf-8", newline="\n") as csv_file:
                csv_file.write(contents)

            driver = CSVDriver()
            driver.update_parameters({"url": csv_path})
            driver.connect()

        self.assertEqual(list(driver.df.columns), ["EXT_A"])
        self.assertEqual(driver.df.index.tolist(), ["2026-01-01T00:00:00Z"])
        self.assertEqual(driver.df["EXT_A"].tolist(), [1.5])
