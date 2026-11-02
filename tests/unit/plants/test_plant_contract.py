"""A plant's forward and update, written once: nested state, pure, and the plan built before."""

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.streams.ports import Ports
from tests.fixtures import si
from tests.fixtures.errors import raises
from tests.fixtures.purity import unchanged

FRESH = {"integral": 0.0, "previous_error": 0.0, "previous_step": 0.0}
TUNING = dict(
    proportional_gain=2.0,
    integral_time=100.0,
    minimum_output=0.0,
    maximum_output=1.0,
    direction="reverse",
)


def two_loops():
    """Return a plant of two PID controllers and nothing connected: two children with state."""
    plant = gm.Plant("loops")
    si.add(plant, "PIDController", "heating", TUNING)
    si.add(plant, "PIDController", "cooling", TUNING | {"direction": "direct"})
    plant.set_inputs(
        {
            "heating.setpoint": 1.0,
            "heating.measurement": 0.8,
            "cooling.setpoint": 1.0,
            "cooling.measurement": 1.3,
        }
    )
    return plant


def test_the_state_of_a_plant_is_the_nested_dict_of_its_children():
    """Each child gets its own entry, and the next state has the same shape."""
    plant = two_loops()
    state = {"heating": FRESH, "cooling": FRESH | {"integral": 0.1}}
    next_state, result = plant.step(state, 60, {})
    assert set(next_state) == {"heating", "cooling"}
    assert result.children["heating"].outputs.command == pytest.approx(0.4)
    assert result.children["cooling"].outputs.command == pytest.approx(0.1 + 2 * 0.3)
    assert next_state["heating"]["integral"] == pytest.approx(2 * 60 / 100 * 0.2)
    assert next_state["cooling"]["previous_error"] == pytest.approx(0.3)
    alone = plant.cooling.step(state["cooling"], 60, {})[0]
    assert next_state["cooling"] == alone
    assert result.state == state and result.children["heating"].state == FRESH


def test_forward_and_update_are_the_plants_own_pure_methods():
    """The forward gives outputs and outlets; update gives the same next state as step."""
    plant = two_loops()
    state = {"heating": FRESH, "cooling": FRESH}
    plant(state=state)
    with unchanged(plant):
        outputs, outlets = plant.forward({}, Ports({}), state)
        updated = plant.update({}, {}, {}, state, 60)
    assert outputs == {} and outlets == {}
    assert updated == plant.step(state, 60, {})[0]


def test_a_child_without_a_state_is_named():
    """A stateful child missing from the tree is a ``missing_value`` naming it."""
    plant = two_loops()
    with raises(ValidationError, "missing_value", match="cooling: state integral"):
        plant(state={"heating": FRESH})
    with raises(ValidationError, "missing_value", match="heating: state integral"):
        plant()


def test_the_plan_is_built_before_the_call_not_by_forward():
    """A forward on a plant that has no plan yet builds one for itself and writes none."""
    plant = two_loops()
    state = {"heating": FRESH, "cooling": FRESH}
    assert plant._plan is None
    plant.forward({}, Ports({}), state)
    assert plant._plan is None
    plant(state=state)
    assert plant._plan is not None
    plan = plant._plan
    plant(state=state)
    assert plant._plan is plan


def test_a_stateless_plant_has_the_empty_state():
    """A plant whose children have no state has the empty state."""
    plant = gm.Plant("quiet")
    si.add(plant, "Pipe", "pipe", {"roughness": 4.5e-5})
    assert not plant._has_state()
    assert plant._call_state(None) == {}
