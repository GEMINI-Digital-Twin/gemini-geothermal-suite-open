"""Single entry point used by the agent tools, the CLI and the web cockpit.

``evaluate(spec)`` = simulate the year (GEMINI-based physics) + economics +
constraint verification, cached by design hash, so every front-end sees the
same numbers for the same design.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from gemini_agent.physics.constraints import check_design
from gemini_agent.physics.design import DesignSpec, load_economics
from gemini_agent.physics.economics import economics
from gemini_agent.physics.plant import AnnualResult, simulate_year
from gemini_agent.physics.site import Brief, Demand


@dataclass
class Evaluation:
    """Everything known about one evaluated design."""

    spec: DesignSpec
    result: AnnualResult
    kpis: dict
    economics: dict
    checks: dict

    def summary(self) -> dict:
        """Compact, LLM-friendly summary (no time series)."""
        k, e = self.kpis, self.economics
        return {
            "design_id": self.spec.key(),
            "label": self.spec.label(),
            "feasible": self.checks["passed"],
            "violations": [v["check"] for v in self.checks["violations"]],
            "geothermal_share_of_heat_pct": k["geothermal_share_of_heat_pct"],
            "heat_supply_gwh": {
                "hex": k["heat_hex_gwh"],
                "heat_pump": k["heat_hp_gwh"],
                "boiler": k["heat_boiler_gwh"],
            },
            "cooling_supply_gwh": {
                "absorption": k["cool_absorption_gwh"],
                "electric": k["cool_electric_gwh"],
            },
            "unmet_mwh": {"heat": k["unmet_heat_mwh"], "cool": k["unmet_cool_mwh"]},
            "electricity_gwh": k["electricity_gwh"],
            "grid_gas_gwh": k["grid_gas_gwh"],
            "co2_t_per_year": k["co2_t"],
            "hp_spf": k["hp_spf"],
            "max_brine_dt_k": k["max_brine_dt_k"],
            "doublet_operating_days": k["doublet_operating_days"],
            "capex_meur": e["capex_total_meur"],
            "lcoe_eur_per_mwh": e["lcoe_eur_per_mwh"],
            "co2_intensity_kg_per_mwh": e["co2_intensity_kg_per_mwh"],
        }

    def pareto_row(self) -> dict:
        """Row for the trade-off chart / comparison table."""
        return {
            "key": self.spec.key(),
            "label": self.spec.label(),
            "passed": self.checks["passed"],
            "co2_t": self.kpis["co2_t"],
            "lcoe": self.economics["lcoe_eur_per_mwh"],
            "capex": self.economics["capex_total_meur"],
            "geo_pct": self.kpis["geothermal_share_of_heat_pct"],
        }


class DesignService:
    """Holds the brief, demand and economics; evaluates and remembers designs."""

    def __init__(self, brief: Brief | None = None, demand: Demand | None = None, weather=None):
        self.brief = brief or Brief.load()
        self.demand = demand or self.brief.load_demand()
        self.econ = load_economics()
        self.weather = (
            weather  # gemini_agent.physics.weather.Weather or None (constant 27 C tower water)
        )
        self._lock = threading.Lock()
        self.history: dict[str, Evaluation] = {}

    def evaluate(self, spec: DesignSpec | dict, outage: dict | None = None) -> Evaluation:
        """Simulate + cost + verify a design (cached by design hash)."""
        spec = spec if isinstance(spec, DesignSpec) else DesignSpec(**spec)
        key = (
            spec.key()
            + (str(sorted(outage.items())) if outage else "")
            + (f"|wx:{self.weather.key()}" if self.weather is not None else "")
        )
        with self._lock:
            if key in self.history:
                return self.history[key]
        res = simulate_year(
            self.brief, spec, self.demand, self.econ, outage=outage, weather=self.weather
        )
        ev = Evaluation(
            spec, res, res.kpis(), economics(res, self.econ), check_design(res, self.brief)
        )
        with self._lock:
            self.history[key] = ev
        return ev


@lru_cache(maxsize=1)
def default_service() -> DesignService:
    """Process-wide service for the GeoHackathon 2026 brief."""
    return DesignService()


# Inputs a user may change in the cockpit: name -> (brief section or "econ", key, label, unit)
EDITABLE_INPUTS = {
    "geothermal_gradient_c_per_km": (
        "reservoir",
        "geothermal_gradient_c_per_km",
        "Geothermal gradient",
        "°C/km",
    ),
    "permeability_md": ("reservoir", "permeability_md", "Permeability", "mD"),
    "max_flow_m3h_per_doublet": (
        "constraints",
        "max_flow_m3h_per_doublet",
        "Max flow per doublet",
        "m³/h",
    ),
    "max_brine_cooling_k": (
        "constraints",
        "max_brine_cooling_k",
        "Max brine temperature drop",
        "°C",
    ),
    "electricity_eur_per_mwh": ("econ", "electricity_eur_per_mwh", "Electricity price", "€/MWh"),
    "natural_gas_eur_per_mwh": ("econ", "natural_gas_eur_per_mwh", "Gas price", "€/MWh"),
    "electricity_kg_per_kwh": ("econ", "electricity_kg_per_kwh", "Grid CO₂ factor", "kg/kWh"),
}


def default_inputs() -> dict:
    """The brief's (and our documented assumptions') values of the editable inputs."""
    brief, econ = Brief.load(), load_economics()["values"]
    return {
        k: float(econ[key] if sec == "econ" else brief.raw[sec][key])
        for k, (sec, key, _, _) in EDITABLE_INPUTS.items()
    }


def custom_service(inputs: dict | None = None, heating_csv=None, cooling_csv=None) -> DesignService:
    """A service for changed inputs: other demand files and/or edited parameters (validated)."""
    import copy

    from gemini_agent.physics.site import _read_csv

    base = Brief.load()
    raw = copy.deepcopy(base.raw)
    inputs = inputs or {}
    for k, v in inputs.items():
        sec, key, label, _ = EDITABLE_INPUTS[k]
        if v is None or float(v) <= 0:
            raise ValueError(f"{label} must be a positive number")
        if sec != "econ":
            raw[sec][key] = float(v)
    if raw["constraints"]["max_flow_m3h_per_doublet"] > 300:
        raise ValueError("Max flow per doublet cannot exceed 300 m³/h (the design model's range)")
    brief = Brief(raw=raw)
    demand = brief.load_demand()
    if heating_csv or cooling_csv:
        d_h, heat = (
            _read_csv(Path(heating_csv)) if heating_csv else (demand.dates, demand.heating_mw)
        )
        d_c, cool = (
            _read_csv(Path(cooling_csv)) if cooling_csv else (demand.dates, demand.cooling_mw)
        )
        if len(heat) != 365 or len(cool) != 365:
            raise ValueError(
                f"Demand files need 365 daily rows (got {len(heat)} heating, {len(cool)} cooling)"
            )
        if d_h != d_c:
            raise ValueError("Heating and cooling files must have the same dates")
        if min(heat) < 0 or min(cool) < 0:
            raise ValueError("Demand values must not be negative")
        demand = type(demand)(d_h, heat, cool, demand.heating_supply_c, demand.cooling_supply_c)
    svc = DesignService(brief, demand)
    for k, v in inputs.items():
        sec, key, _, _ = EDITABLE_INPUTS[k]
        if sec == "econ":
            svc.econ["values"][key] = float(v)
    return svc


def default_weather(brief: Brief | None = None):
    """The documented default site weather (the brief names no site): Open-Meteo ERA5 for the
    default coordinates and reference year in the brief's assumptions, cached as CSV."""
    from gemini_agent.physics.weather import fetch_weather

    b = brief or Brief.load()
    return fetch_weather(
        "default proxy site (Delft, NL)",
        b.assumption("default_site_latitude"),
        b.assumption("default_site_longitude"),
        int(b.assumption("default_weather_year")),
    )
