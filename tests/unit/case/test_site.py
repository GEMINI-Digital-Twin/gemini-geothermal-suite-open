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
