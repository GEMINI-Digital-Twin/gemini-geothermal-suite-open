"""A case reads the daily demand of the hackathon with dates and a ``time_zone``."""

import pandas as pd
import pytest

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


def test_dates_in_a_zone_east_of_utc_start_the_hour_before():
    """In ``Europe/Oslo`` the day 2027-01-01 starts at 23:00 UTC the day before.

    The case runs in UTC from 2027-01-01, so the local days no longer cover its last hour.
    """
    with pytest.raises(gm.errors.ValidationError, match="covers 2026-12-31T23:00:00"):
        _dated("Europe/Oslo")
