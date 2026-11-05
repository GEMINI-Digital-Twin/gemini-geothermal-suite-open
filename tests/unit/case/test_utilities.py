"""``gm.case.Utilities``: the physics of the grids."""

import pytest

import gemini as gm
from tests.fixtures.errors import raises
from tests.unit.case.conftest import csv_text


def test_the_co2_intensity_of_the_grid_is_read_in_si(case):
    """300 g/kWh is 8.33e-8 kg/J."""
    assert case.utilities.electricity.co2_intensity == pytest.approx(300 / 3.6e9)


def test_the_connection_limits_and_the_gas_grid_are_optional_values(data, files):
    """Absent is None; given they are SI."""
    electricity = data["utilities"]["electricity"]
    assert gm.Case.from_dict(data, files=files).utilities.electricity.import_limit is None
    electricity["import_limit"] = {"value": 6, "unit": "MW"}
    data["utilities"]["gas"] = {
        "composition": {"CH4": {"value": 0.9}, "N2": {"value": 0.1}},
        "heating_value": {"value": 50, "unit": "kJ/kg"},
    }
    utilities = gm.Case.from_dict(data, files=files).utilities
    assert utilities.electricity.import_limit == 6e6
    assert (
        utilities.gas.composition == {"CH4": 0.9, "N2": 0.1} and utilities.gas.heating_value == 5e4
    )


def test_a_grid_gas_with_hydrocarbons_is_read(data, files):
    """The grid gas is natural gas: ethane and propane are species of its composition."""
    data["utilities"]["gas"] = {
        "composition": {"CH4": {"value": 0.8}, "C2H6": {"value": 0.1}, "C3H8": {"value": 0.1}}
    }
    gas = gm.Case.from_dict(data, files=files).utilities.gas
    assert gas.composition == {"CH4": 0.8, "C2H6": 0.1, "C3H8": 0.1}


def test_a_price_series_of_the_grid_is_a_series(data):
    """The intensity may follow the hours."""
    data["utilities"]["electricity"]["co2_intensity"] = {
        "file": "data/co2.csv",
        "column": "g",
        "unit": "g/kWh",
    }
    lines = "".join(f"2027-01-0{n}T00:00:00Z,{100 * n}\n" for n in range(1, 8))
    case = gm.Case.from_dict(data, files={**_demand(), "data/co2.csv": f"time,g\n{lines}".encode()})
    assert case.utilities.electricity.co2_intensity[1] == pytest.approx(200 / 3.6e9)
    with raises(gm.errors.ValidationError, "missing_value"):
        gm.Case.from_dict(data, files=_demand())


def _demand():
    """Return the demand file of the shared case."""
    return {"data/demand.csv": csv_text().encode()}


def test_the_grid_gas_composition_takes_a_mole_percent(data, files):
    """A composition given in mol% is read as fractions."""
    data["utilities"]["gas"] = {
        "composition": {"CH4": {"value": 90, "unit": "mol%"}, "N2": {"value": 0.1}},
    }
    gas = gm.Case.from_dict(data, files=files).utilities.gas
    assert gas.composition == pytest.approx({"CH4": 0.9, "N2": 0.1})
