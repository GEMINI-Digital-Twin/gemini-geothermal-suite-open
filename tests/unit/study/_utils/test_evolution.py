"""The hypervolume, the front filter and the summary text of ``gm.study.evolve``."""

import numpy as np
import pytest

from gemini.study._utils import evolution


def test_the_non_dominated_rows_are_kept():
    """(1, 3), (2, 2) and (3, 1) trade off; (3, 3) is beaten by (2, 2)."""
    points = [[1, 3], [2, 2], [3, 3], [3, 1]]
    assert evolution.non_dominated(points) == [0, 1, 3]


def test_the_hypervolume_of_two_objectives_by_hand():
    """Two points at (0, 1) and (1, 0) with the reference 1.1: 0.11 + 0.11 + 0.01 less overlap."""
    area = evolution.hypervolume([[0.0, 1.0], [1.0, 0.0]])
    assert area == pytest.approx(1.1 * 0.1 + 0.1 * 1.0)


def test_one_objective_is_the_length_to_the_reference():
    """The best of one objective at 0.25 leaves 0.85 to 1.1."""
    assert evolution.hypervolume([[0.5], [0.25]]) == pytest.approx(0.85)


def test_points_beyond_the_reference_add_nothing_and_three_axes_have_none():
    """A point past 1.1 counts for nothing; three objectives are not measured."""
    assert evolution.hypervolume([[1.2, 0.0]]) == 0.0
    assert evolution.hypervolume(np.zeros((0, 2))) == 0.0
    assert evolution.hypervolume([[0.0, 0.0, 0.0]]) is None


def test_scaling_maps_the_front_to_the_unit_square():
    """Between the ideal and the nadir of the front; an objective of one value is 0."""
    ideal, nadir = evolution.bounds([[10, 6], [20, 5], [30, 7]])
    assert list(evolution.scale([[15, 5.5]], ideal, nadir)[0]) == [0.5, 0.5]
    assert list(evolution.scale([[15, 5]], np.array([10, 5]), np.array([20, 5]))[0]) == [0.5, 0]


def test_a_label_says_on_off_and_the_group():
    """True and False read as on and off; a choice shows its group."""
    assert evolution.label({"pump": True, "boiler": False, "cooling": "absorption"}) == (
        "pump=on, boiler=off, cooling=absorption"
    )
    assert evolution.label({}) == "(no structure choice)"


def test_a_reason_reads_as_its_message():
    """A verdict reason is a dict: its message is shown."""
    assert evolution.reason_text({"message": "cold short", "kind": "requirement"}) == "cold short"
    assert evolution.reason_text("failed") == "failed"


def test_the_summary_names_the_budget_the_front_and_each_structure():
    """A plain result reads as lines an agent can quote."""
    design = {
        "structure": {"pump": True},
        "metrics": {"lcts": {"value": 40.0, "unit": "EUR/MWh"}},
        "feasible": False,
        "reason": {"message": "cold short"},
    }
    result = {
        "objectives": ["lcts"],
        "budget": {
            "evaluations": 8,
            "search": 8,
            "polish": 0,
            "generations": 2,
            "stopped": "budget",
            "invalid": 1,
        },
        "front": [design],
        "best": design,
        "structures": [
            {"structure": {"pump": True}, "evaluations": 8, "feasible": 0, "best": design}
        ],
        "rejected": [{"structure": {"pump": False}, "reasons": ["x.power_in: unconnected"]}],
    }
    text = evolution.explained(result)
    assert "Simulations: 8" in text and "pump=on: lcts 40 EUR/MWh (infeasible: cold short)" in text
    assert "refused pump=off: x.power_in: unconnected" in text
