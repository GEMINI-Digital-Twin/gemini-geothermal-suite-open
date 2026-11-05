"""The discount rate and the analysis period: the economics of the case."""

import pytest

import gemini as gm
from gemini.evaluate._utils.discounting import discounting
from gemini.units import Quantity
from tests.fixtures.cases import make_case
from tests.fixtures.errors import raises


def case_of(**economics):
    """Return a case whose economics holds ``economics``."""
    return make_case(count=2, step=86400.0, economics=economics)


def test_the_case_gives_the_rate_and_the_period_in_years():
    """The analysis period is read in years."""
    case = case_of(discount_rate=0.05, analysis_period=Quantity(25, "yr"))
    assert discounting(case) == (0.05, pytest.approx(25))


def test_a_value_given_nowhere_is_a_missing_assumption():
    """The path in the case is named."""
    with raises(gm.errors.ValidationError, "missing_assumption") as caught:
        discounting(case_of(analysis_period=Quantity(10, "yr")))
    assert caught.value.path == "economics.discount_rate"


def test_a_negative_rate_is_refused_when_the_case_is_read():
    """The bound of the declaration stops it before ``discounting`` is asked."""
    with pytest.raises(gm.errors.ValidationError, match="economics.discount_rate"):
        case_of(discount_rate=-0.01, analysis_period=Quantity(10, "yr"))


def test_a_period_under_one_year_is_refused_with_its_path():
    """Half a year is not an analysis period; one year is."""
    with raises(gm.errors.ValidationError, "invalid_value") as caught:
        discounting(case_of(discount_rate=0.05, analysis_period=Quantity(0.5, "yr")))
    assert caught.value.path == "economics.analysis_period"
    assert discounting(case_of(discount_rate=0.0, analysis_period=Quantity(1, "yr"))) == (
        0.0,
        pytest.approx(1),
    )
