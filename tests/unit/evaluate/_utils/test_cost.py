"""The annuity and the lifetime cost."""

import pytest

from gemini.evaluate._utils import cost


def test_annuity_is_the_discounted_year_count():
    """Ten years at 5 % are 7.7217 discounted years; at 0 % they are ten."""
    assert cost.annuity(0.05, 10) == pytest.approx(7.721734929, rel=1e-9)
    assert cost.annuity(0.0, 10) == 10.0


def test_annuity_of_a_part_of_a_year_is_the_closed_form():
    """A period of 2.5 years is read by the closed form, not by a sum of whole years."""
    closed = (1 - 1.05**-2.5) / 0.05
    assert cost.annuity(0.05, 2.5) == pytest.approx(closed, rel=1e-12)
    assert cost.annuity(0.0, 2.5) == 2.5
    assert cost.annuity(0.05, 2) == pytest.approx(1 / 1.05 + 1 / 1.05**2, rel=1e-12)
