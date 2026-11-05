"""``gm.case.Site``: ground, reservoir, fluid, air and the two laws with depth."""

import pytest

import gemini as gm
from tests.fixtures.errors import raises


def test_the_temperature_follows_the_gradient_from_the_surface(case):
    """12 degC + 30 K/km * 2.5 km = 87 degC."""
    assert case.site.temperature_at(2500.0) == pytest.approx(360.15)


def test_a_measured_reservoir_temperature_is_shifted_by_the_gradient(data, files):
    """From the reference depth, not the surface."""
    data["site"]["reservoir"]["temperature"] = {"value": 90, "unit": "degC"}
    site = gm.Case.from_dict(data, files=files).site
    assert site.temperature_at(2600.0) == pytest.approx(363.15 + 3.0)


def test_the_pressure_is_hydrostatic_from_the_reference(case):
    """250 barg is 251.01325 bar absolute at 2500 m."""
    reference = case.site.reservoir.pressure
    assert case.site.pressure_at(2500.0) == pytest.approx(reference)
    assert case.site.pressure_at(2600.0) == pytest.approx(
        reference + 1030 * 9.80665 * 100, rel=1e-4
    )


def test_a_missing_value_of_the_law_names_its_path(data, files):
    """No gradient, no temperature."""
    del data["site"]["ground"]["gradient"]
    site = gm.Case.from_dict(data, files=files).site
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        site.temperature_at(2000.0)
    assert caught.value.path == "site.ground.gradient"


def test_the_dissolved_gas_adds_up_to_one_and_names_known_species(data, files):
    """A dict of mole fractions; 0.8 + 0.3 is refused, and so is an unknown species."""
    assert gm.Case.from_dict(data, files=files).site.fluid.dissolved_gas == {"CH4": 0.8, "CO2": 0.2}
    data["site"]["fluid"]["dissolved_gas"]["CO2"] = {"value": 0.3}
    with raises(gm.errors.ValidationError, "out_of_bounds"):
        gm.Case.from_dict(data, files=files)
    data["site"]["fluid"]["dissolved_gas"] = {"O2": {"value": 1.0}}
    with raises(gm.errors.ValidationError, "unknown_name"):
        gm.Case.from_dict(data, files=files)


def test_the_old_name_of_the_gas_is_refused_with_the_new_one(data, files):
    """`gas` is `dissolved_gas`."""
    data["site"]["fluid"]["gas"] = {"CH4": 1.0}
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        gm.Case.from_dict(data, files=files)
    assert "dissolved_gas" in str(caught.value)


def test_the_optional_values_are_read_in_si(data, files):
    """Sand, air pressure and humidity as a constant."""
    data["site"]["fluid"]["sand_concentration"] = {"value": 20, "unit": "mg/l"}
    data["site"]["air"]["pressure"] = {"value": 101325, "unit": "Pa"}
    data["site"]["air"]["relative_humidity"] = {"value": 0.6}
    site = gm.Case.from_dict(data, files=files).site
    assert site.fluid.sand_concentration == pytest.approx(0.02)
    assert site.air.pressure == 101325 and site.air.relative_humidity == 0.6
    assert site.reservoir.thickness == 100.0 and site.ground.gradient == pytest.approx(0.03)


def test_a_humidity_above_one_is_out_of_bounds(data, files):
    """A share is within 0 and 1."""
    data["site"]["air"]["relative_humidity"] = {"value": 1.5}
    with raises(gm.errors.ValidationError, "out_of_bounds"):
        gm.Case.from_dict(data, files=files)


def test_the_reservoir_pressure_in_barg_is_stored_absolute_in_pascal(case):
    """250 barg is 250 bar plus one atmosphere, 25 101 325 Pa, at the reference depth."""
    assert case.site.reservoir.pressure == pytest.approx(25_101_325)
    assert case.site.pressure_at(case.site.reservoir.reference_depth) == pytest.approx(25_101_325)


def test_the_gradient_is_taken_as_given_whatever_its_sign(data, files):
    """A zero or negative gradient is not refused; the temperature follows it linearly."""
    for gradient in (0, -10):
        data["site"]["ground"]["gradient"] = {"value": gradient, "unit": "K/km"}
        site = gm.Case.from_dict(data, files=files).site
        assert site.temperature_at(2000.0) == pytest.approx(285.15 + gradient * 2.0)


def test_the_dissolved_gas_takes_a_unit_of_a_fraction_or_none(data, files):
    """20 mol% is 0.2; a fraction may say ``-``; a bare number keeps meaning a fraction."""
    data["site"]["fluid"]["dissolved_gas"] = {
        "CH4": {"value": 70, "unit": "mol%"},
        "CO2": {"value": 0.2, "unit": "-"},
        "N2": {"value": 0.1},
    }
    case = gm.Case.from_dict(data, files=files)
    assert case.site.fluid.dissolved_gas == pytest.approx({"CH4": 0.7, "CO2": 0.2, "N2": 0.1})
    written = case.to_dict()["site"]["fluid"]["dissolved_gas"]
    assert written == data["site"]["fluid"]["dissolved_gas"]
    assert gm.Case.from_dict(case.to_dict(), files=files) == case and case.check() == []


def test_the_dissolved_gas_refuses_a_unit_of_another_dimension(data, files):
    """A unit that is no fraction is a ``unit`` issue naming the units of a fraction."""
    data["site"]["fluid"]["dissolved_gas"]["CH4"] = {"value": 0.8, "unit": "m"}
    with pytest.raises(gm.errors.ValidationError) as caught:
        gm.Case.from_dict(data, files=files)
    (issue,) = caught.value.issues
    assert (issue.path, issue.kind) == ("site.fluid.dissolved_gas.CH4.unit", "unit")
    assert "mol%" in issue.accepted
    data["site"]["fluid"]["dissolved_gas"]["CH4"] = {"value": 80, "unit": "mol%"}
    data["site"]["fluid"]["dissolved_gas"]["CO2"] = {"value": 120, "unit": "mol%"}
    with raises(gm.errors.ValidationError, "out_of_bounds"):
        gm.Case.from_dict(data, files=files)


def test_the_schema_of_the_dissolved_gas_offers_an_optional_unit():
    """The unit of a fraction may be given and need not be."""
    fluid = gm.Case.schema()["properties"]["site"]["properties"]["fluid"]["properties"]
    leaf = fluid["dissolved_gas"]["properties"]["CH4"]
    assert leaf["required"] == ["value"] and "mol%" in leaf["properties"]["unit"]["enum"]
    assert fluid["dissolved_gas"]["x-fraction"] is True


def test_a_humidity_series_without_a_unit_is_read_as_fractions(data, files):
    """As in 0.5.0, a series of the relative humidity needs no unit: its values are 0 to 1."""
    rows = ["time,rh"] + [f"2027-01-{day:02d}T00:00:00Z,0.{day}" for day in range(1, 8)]
    files = dict(files) | {"rh.csv": ("\n".join(rows) + "\n").encode()}
    data["site"]["air"]["relative_humidity"] = {"file": "rh.csv", "column": "rh"}
    humidity = gm.Case.from_dict(data, files=files).site.air.relative_humidity
    assert list(humidity) == pytest.approx([day / 10 for day in range(1, 8)])
