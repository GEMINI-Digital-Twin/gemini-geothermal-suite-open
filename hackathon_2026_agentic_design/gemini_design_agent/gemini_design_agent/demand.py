"""Load and summarise the supplied annual heating / cooling demand profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class DemandProfile:
    dates: pd.DatetimeIndex
    heating_mw: np.ndarray   # daily-average thermal power demand (MWth)
    cooling_mw: np.ndarray   # daily-average cooling power demand (MWcool)

    @property
    def n_days(self) -> int:
        return len(self.dates)

    @property
    def heating_gwh(self) -> float:
        return float(self.heating_mw.sum() * 24.0 / 1000.0)

    @property
    def cooling_gwh(self) -> float:
        return float(self.cooling_mw.sum() * 24.0 / 1000.0)

    def summary(self) -> dict:
        ih = int(np.argmax(self.heating_mw))
        ic = int(np.argmax(self.cooling_mw))
        hs = np.sort(self.heating_mw)[::-1]
        return {
            "days": self.n_days,
            "heating_peak_mw": float(self.heating_mw.max()),
            "heating_peak_date": str(self.dates[ih].date()),
            "heating_min_mw": float(self.heating_mw.min()),
            "heating_mean_mw": float(self.heating_mw.mean()),
            "heating_gwh": self.heating_gwh,
            "cooling_peak_mw": float(self.cooling_mw.max()),
            "cooling_peak_date": str(self.dates[ic].date()),
            "cooling_mean_mw": float(self.cooling_mw.mean()),
            "cooling_gwh": self.cooling_gwh,
            "cooling_days": int((self.cooling_mw > 0).sum()),
            "heating_duration_mw": {
                "top_1_day": float(hs[0]),
                "top_30_days": float(hs[29]),
                "top_60_days": float(hs[59]),
                "top_90_days": float(hs[89]),
                "top_180_days": float(hs[179]),
            },
        }

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"date": self.dates, "heating_mw": self.heating_mw, "cooling_mw": self.cooling_mw}
        )


def load_demand(heating_csv: str | Path, cooling_csv: str | Path) -> DemandProfile:
    h = pd.read_csv(heating_csv, parse_dates=["date"])
    c = pd.read_csv(cooling_csv, parse_dates=["date"])
    if not h["date"].equals(c["date"]):
        raise ValueError("heating and cooling CSVs must share the same date column")
    hcol = [x for x in h.columns if x != "date"][0]
    ccol = [x for x in c.columns if x != "date"][0]
    return DemandProfile(
        dates=pd.DatetimeIndex(h["date"]),
        heating_mw=h[hcol].to_numpy(dtype=float),
        cooling_mw=c[ccol].to_numpy(dtype=float),
    )
