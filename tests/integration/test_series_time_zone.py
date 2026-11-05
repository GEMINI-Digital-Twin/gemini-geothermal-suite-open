"""A case reads the daily demand of the hackathon with dates and a ``time_zone``."""

import pandas as pd

import gemini as gm
from tests.fixtures.paths import EXAMPLES

SAMPLE = EXAMPLES / "hackathon_2026"


def _dated(zone):
    """Return the sample case with its demand as dates without an offset, read in ``zone``."""
    case = gm.Case.from_json(SAMPLE / "case.json")
    table = pd.read_csv(SAMPLE / "data/demand.csv")
    table["time"] = table["time"].str[:10]
    data = case.to_dict()
    for service in ("heating", "cooling"):
        data["demand"][service]["power"] |= {"file": "dated.csv", "time_zone": zone}
    files = {**case.files(), "dated.csv": table.to_csv(index=False).encode()}
    return case, gm.Case.from_dict(data, files=files)


def test_dates_in_utc_give_the_demand_of_the_sample():
    """``time_zone: UTC`` on dates is the same demand as the sample's times with ``Z``."""
    case, dated = _dated("UTC")
    expected = case.demand.frame
    pd.testing.assert_frame_equal(dated.demand.frame, expected, check_exact=True)
    assert dated.to_dict()["demand"]["heating"]["power"]["time_zone"] == "UTC"


def test_daily_dates_in_a_zone_east_of_utc_are_matched_by_their_local_date():
    """In ``Europe/Oslo`` each row of a daily series is one local calendar date (gemini 0.6.5).

    Since request 37 (QA-039) a daily series read in a zone is matched to the case's days by
    date, not by UTC instants, so a zone with summer time (days of 23 or 25 hours) still gives
    each day its own row: the dated demand is the sample's, day by day.
    """
    case, dated = _dated("Europe/Oslo")
    expected = case.demand.frame
    pd.testing.assert_frame_equal(dated.demand.frame, expected, check_exact=False)
