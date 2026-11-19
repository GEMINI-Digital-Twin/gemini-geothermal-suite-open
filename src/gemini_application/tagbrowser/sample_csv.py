"""Build a sample CSV for Data Upload from measured external tag names."""

import csv
import io
import random
from datetime import datetime, timedelta

# One calendar month of daily placeholder rows, starting on this day
SAMPLE_CSV_START = datetime(2026, 1, 1)
SAMPLE_CSV_DAYS = 31
SAMPLE_CSV_TIMESTAMP = SAMPLE_CSV_START.strftime("%Y-%m-%d %H:%M:%S")
SAMPLE_CSV_VALUE_MIN = 1.0
SAMPLE_CSV_VALUE_MAX = 100.0


def sample_csv_columns(units):
    """Return Timestamp plus unique non-empty measured external tag names.

    Column order follows unit order, then tag order. The external tag name is
    the last entry of each measured tag, matching CSV import.
    """
    # -- collect external tag names in unit order ---------------------------
    columns = ["Timestamp"]
    seen = set()
    for unit in units:
        measured = unit.tags.get("measured", {})
        for value in measured.values():
            if not value:
                continue
            external_tagname = str(value[-1]).strip()
            if external_tagname == "" or external_tagname in seen:
                continue
            seen.add(external_tagname)
            columns.append(external_tagname)

    return columns


def build_sample_csv(columns):
    """Build a semicolon-separated sample CSV with one month of daily rows."""
    # -- write the header ---------------------------------------------------
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(columns)

    # -- write one random example row per day -------------------------------
    for day in range(SAMPLE_CSV_DAYS):
        stamp = (SAMPLE_CSV_START + timedelta(days=day)).strftime("%Y-%m-%d %H:%M:%S")
        values = [_sample_csv_random_value() for _ in range(len(columns) - 1)]
        writer.writerow([stamp] + values)

    return buffer.getvalue()


def _sample_csv_random_value():
    """Return one example measurement between 1 and 100."""
    return f"{random.uniform(SAMPLE_CSV_VALUE_MIN, SAMPLE_CSV_VALUE_MAX):.2f}"
