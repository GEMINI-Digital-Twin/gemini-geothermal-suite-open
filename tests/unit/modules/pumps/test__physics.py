"""Where an ESP's head and power curves are below zero, read once per set of curves."""

from gemini.modules.pumps._physics import below_zero, negative_curves
from tests.fixtures.esp_design import ESP_PARAMS

HEAD = ESP_PARAMS["head_coefficients"]
POWER = ESP_PARAMS["power_coefficients"]


def test_curves_that_stay_above_zero_give_no_text_and_negated_ones_name_the_flows():
    """The pump's own curves are positive at low flow; their negation is negative from zero."""
    assert negative_curves(0.01, 12, HEAD, POWER, False) == ""
    text = negative_curves(0.01, 12, [-value for value in HEAD], POWER, False)
    assert text.startswith("; the curves give negative head at flows 0 to ")
    assert text.endswith("(0 to 0.01 m3/s)")


def test_the_runs_below_zero_are_their_first_and_last_flows():
    flows = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert below_zero(flows, [1, -1, -1, 1, -1]) == [(1.0, 2.0), (4.0, 4.0)]
