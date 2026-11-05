"""External data: daily weather -> cooling-water temperature for chillers.

Source: Open-Meteo historical archive (ERA5 reanalysis; free, no API key),
https://open-meteo.com/en/docs/historical-weather-api . The brief gives no
location, so the agent must ask for one (or use a documented default).
The 2027 demand year is synthetic; weather of a reference year is mapped by
day of year (assumption reported by the tool).

Cooling-tower outlet (= chiller cooling-water inlet) temperature:
    T_cw = max(T_cw_min, T_wetbulb,max + approach)
with a typical tower approach of 4 K and a 12 C minimum (tower fan control).
"""

from __future__ import annotations

import csv
import json
import urllib.request
from dataclasses import dataclass

from gemini_agent.physics.site import REPO_ROOT

CACHE = REPO_ROOT / "dataset" / "geohackathon2026" / "weather"
API = "https://archive-api.open-meteo.com/v1/archive"


@dataclass
class Weather:
    """Daily weather mapped onto the 365 demand days."""

    location: str
    latitude: float
    longitude: float
    reference_year: int
    t_mean_c: list[float]
    t_wetbulb_max_c: list[float]
    source: str

    def cooling_water_c(self, approach_k: float = 4.0, minimum_c: float = 12.0) -> list[float]:
        """Cooling-tower outlet temperature per day."""
        return [max(minimum_c, wb + approach_k) for wb in self.t_wetbulb_max_c]

    def key(self) -> str:
        """Cache key component."""
        return f"{self.location}:{self.latitude:.2f}:{self.longitude:.2f}:{self.reference_year}"

    def summary(self) -> dict:
        """Compact statistics for the agent."""
        cw = self.cooling_water_c()
        return {
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "reference_year": self.reference_year,
            "source": self.source,
            "t_mean_c_min_max": [round(min(self.t_mean_c), 1), round(max(self.t_mean_c), 1)],
            "wetbulb_max_c_peak": round(max(self.t_wetbulb_max_c), 1),
            "cooling_water_c_min_mean_max": [
                round(min(cw), 1),
                round(sum(cw) / len(cw), 1),
                round(max(cw), 1),
            ],
            "assumptions": "tower approach 4 K, minimum 12 C; reference-year weather mapped by "
            "day of year",
        }


def fetch_weather(
    location: str,
    latitude: float,
    longitude: float,
    year: int = 2023,
    n_days: int = 365,
    use_cache: bool = True,
) -> Weather:
    """Daily weather from Open-Meteo (cached as CSV for offline reproducibility)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    fn = CACHE / f"openmeteo_{latitude:.2f}_{longitude:.2f}_{year}.csv"
    if not (use_cache and fn.exists()):
        url = (
            f"{API}?latitude={latitude}&longitude={longitude}&start_date={year}-01-01&end_date={year}-12-31"  # noqa: E501
            "&daily=temperature_2m_mean,wet_bulb_temperature_2m_max&timezone=auto"
        )
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.load(r)["daily"]
        with open(fn, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "temperature_2m_mean", "wet_bulb_temperature_2m_max"])
            for row in zip(d["time"], d["temperature_2m_mean"], d["wet_bulb_temperature_2m_max"]):
                w.writerow(row)
    rows = list(csv.DictReader(open(fn, encoding="utf-8")))
    rows = [r for r in rows if r["date"][5:] != "02-29"][:n_days]  # leap-day guard

    def num(x, fallback):
        try:
            return float(x)
        except (TypeError, ValueError):
            return fallback

    tm = [num(r["temperature_2m_mean"], 10.0) for r in rows]
    wb = [num(r["wet_bulb_temperature_2m_max"], t) for r, t in zip(rows, tm)]
    return Weather(
        location, latitude, longitude, year, tm, wb, f"Open-Meteo ERA5 archive ({fn.name})"
    )
