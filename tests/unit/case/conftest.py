"""A small full case, as a dictionary and as in-memory files, shared by the case tests."""

import copy

import numpy as np
import pytest

import gemini as gm

DAYS = 7


def csv_text(days=DAYS, start="2027-01-01", unit_scale=1.0):
    """Return the text of a demand CSV of ``days`` days: heat in MW and cold in MW."""
    rows = ["time,heat_MW,cold_MW"]
    for number, (heat, cold) in enumerate(zip(np.linspace(1, 4, days), np.linspace(0.5, 2, days))):
        day = f"{int(start[8:]) + number:02d}"
        rows.append(
            f"{start[:8]}{day}T00:00:00Z,{float(heat) * unit_scale!r},{float(cold) * unit_scale!r}"
        )
    return "\n".join(rows) + "\n"


def site():
    """Return the site section."""
    return {
        "ground": {
            "surface_temperature": {"value": 12, "unit": "degC"},
            "gradient": {
                "value": 30,
                "unit": "K/km",
                "uncertainty": {"kind": "normal", "std": 2, "min": 25, "max": 35},
            },
        },
        "reservoir": {
            "reference_depth": {"value": 2500, "unit": "m"},
            "thickness": {"value": 100, "unit": "m"},
            "permeability": {"value": 200, "unit": "mD"},
            "pressure": {"value": 250, "unit": "barg"},
        },
        "fluid": {
            "density": {"value": 1030, "unit": "kg/m3"},
            "viscosity": {"value": 0.4, "unit": "mPa.s"},
            "gas_liquid_ratio": {"value": 0.8, "unit": "Nm3/m3"},
            "dissolved_gas": {"CH4": {"value": 0.8}, "CO2": {"value": 0.2}},
        },
        "air": {"temperature": {"value": 10, "unit": "degC"}},
    }


def demand():
    """Return the demand section."""
    series = {"file": "data/demand.csv", "unit": "MW"}
    return {
        "heating": {
            "power": series | {"column": "heat_MW"},
            "supply_temperature": {"value": 100, "unit": "degC"},
            "return_temperature": {"value": 60, "unit": "degC"},
        },
        "cooling": {
            "power": series | {"column": "cold_MW"},
            "supply_temperature": {"value": 20, "unit": "degC"},
            "return_temperature": {"value": 25, "unit": "degC"},
        },
    }


def requirements():
    """Return the requirements section."""
    flow = {"on": "doublet", "quantity": "production_flow", "unit": "m3/h", "when": "running"}
    return [
        {"name": "flow_range", **flow, "over": "each", "min": 50, "max": 300},
        {"name": "running_time", **flow, "unit": "d", "over": "duration", "max": 5},
        {
            "name": "pump_efficiency",
            "on": "doublet",
            "quantity": "pump_efficiency",
            "min": 0.7,
            "max": 0.7,
        },
    ]


def economics():
    """Return the economics section."""
    return {
        "format": 1,
        "kind": "economics",
        "name": "prices",
        "currency": {"value": "EUR"},
        "price_year": {"value": 2015},
        "discount_rate": {"value": 0.05},
        "analysis_period": {"value": 25, "unit": "yr"},
        "capex": {
            "drilling": {"value": 1239, "unit": "EUR/m"},
            "heat_pump": {"value": 0.67, "unit": "EUR/W"},
            "degasser": {"value": 1000000, "unit": "EUR"},
        },
        "opex": {"fixed": {"heat_pump": {"value": 2, "unit": "%/yr"}}},
        "energy": {"electricity": {"value": 100, "unit": "EUR/MWh"}},
        "carbon": {"price": {"value": 80, "unit": "EUR/t"}},
        "revenue": {
            "heat": {"value": 60, "unit": "EUR/MWh"},
            "subsidy": {
                "amount": {"value": 1, "unit": "MEUR/yr"},
                "duration": {"value": 10, "unit": "yr"},
            },
        },
        "accounting": {
            "allocation": {"heat_cost_share": {"value": 0.8}},
            "gwp": {"standard": {"value": "IPCC AR6"}, "CH4": {"value": 29.8}},
        },
    }


@pytest.fixture
def data():
    """Return the dictionary of a full case, as ``case.json`` writes it."""
    return {
        "format": 1,
        "kind": "case",
        "name": "week",
        "about": {"site": "test"},
        "time": {"start": "2027-01-01", "end": "2027-01-08", "step": {"value": 1, "unit": "d"}},
        "site": site(),
        "demand": demand(),
        "utilities": {"electricity": {"co2_intensity": {"value": 300, "unit": "g/kWh"}}},
        "economics": economics(),
        "requirements": requirements(),
        "choices": {
            "doublets": {"min": 1, "max": 3},
            "depth": {"min": {"value": 2000, "unit": "m"}, "max": {"value": 3500, "unit": "m"}},
        },
    }


@pytest.fixture
def files():
    """Return the CSV files of the full case, in memory."""
    return {"data/demand.csv": csv_text().encode()}


@pytest.fixture
def case(data, files):
    """Return the full case."""
    return gm.Case.from_dict(copy.deepcopy(data), files=files)


def codes(error):
    """Return the ``(path, code)`` of every issue of a ``ValidationError``."""
    return [(item["path"], item["code"]) for item in error.problems]
