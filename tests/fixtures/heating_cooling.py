"""The heating and cooling plants of the sample case and days of their demand.

The days are round numbers every plant covers.
"""

import pandas as pd

import gemini as gm
from tests.fixtures.sample_cases import sample_case

HEAT = 12e6
"""Heating demand of the days [W]."""
COLD = 5e6
"""Cooling demand of the days [W]."""


def days_case(heat, cold=None, start="2027-07-01", requirements=None):
    """Return the days of ``heat`` [W] (and ``cold``) under the sample case, without its duration.

    The site, limits and prices are the sample case's; its 330 d duration requirement is left out,
    because the days are fewer. Without ``cold`` the case has no cooling service. ``requirements``
    (a list of dicts) replaces the sample's, for a plant that has no doublet to judge.
    """
    case = sample_case()
    index = pd.date_range(start, periods=len(heat), freq="D", tz="UTC", name="time")
    columns = {"heating_demand": heat} | ({} if cold is None else {"cooling_demand": cold})
    table = pd.DataFrame(columns, index=index).reset_index()
    table["time"] = table["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = case.to_dict()
    data["time"] = {
        "start": index[0].isoformat(),
        "end": (index[-1] + index.freq).isoformat(),
        "step": {"value": 1, "unit": "d"},
    }
    demand = {}
    for name in ("heating", "cooling"):
        if f"{name}_demand" in columns:
            power = {"file": "days.csv", "column": f"{name}_demand", "unit": "W"}
            demand[name] = data["demand"][name] | {"power": power}
    data["demand"] = demand
    kept = [item for item in data["requirements"] if item.get("over") != "duration"]
    data["requirements"] = kept if requirements is None else requirements
    return gm.Case.from_dict(
        data, files={**case.files(), "days.csv": table.to_csv(index=False).encode()}
    )


def two_days_case():
    """Return the two days under the sample case."""
    return days_case([HEAT] * 2, [COLD] * 2)
