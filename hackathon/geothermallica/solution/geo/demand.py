"""Daily heating and cooling demand of 2027 (MW) from the challenge CSV files, and their scaling to a peak."""
import pandas as pd

from geo.common import DATA

heat = pd.read_csv(DATA / "GEMINI_Heating_Demand_Daily_2027.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]
cold = pd.read_csv(DATA / "GEMINI_Cooling_Demand_Daily_2027.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]


def scaled(series, peak_MW=None):
    """The demand series scaled linearly so its maximum is peak_MW, MW per day; peak_MW None returns it unchanged."""
    return series if peak_MW is None else series * (peak_MW / series.max())
