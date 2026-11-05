"""A stateful plant scans in time: a hand-stepped tank, state connections and failed steps."""

import numpy as np
import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.plants.plant import Plant
from gemini.streams.fluid import BRINE
from tests.fixtures import si
from tests.fixtures.errors import raises
from tests.fixtures.storage_plant import (
    INITIAL,
    PARAMS,
    FaultyTank,
    buffer_frame,
    buffer_plant,
    buffer_reference,
    lagged_frame,
    lagged_plant,
)
from tests.unit.engine.test_check import physics, with_state

START = {"position": None, "module_states": {"": INITIAL}}


def _fluid(plant):
    for module in plant.modules():
        module._set_own_fluid(BRINE)
    return plant


def _run(plant, frame, **options):
    engine = gm.Engine(plant, **options)
    return engine._simulate(gm.Dataset.from_frame(frame), None, START), engine


@pytest.mark.parametrize("compile", [False, True])
def test_a_storage_plant_equals_the_hand_stepped_tank(compile):
    """The tank temperature, the outlets and the end state follow the exact solution."""
    frame = buffer_frame(24)
    results, engine = _run(buffer_plant(), frame, compile=compile)
    reference = buffer_reference(frame)
    table = results.to_frame()
    assert results.errors() == []
    np.testing.assert_allclose(table["tank.tank_temperature"], reference["temperature"], rtol=1e-12)
    np.testing.assert_allclose(
        table["tank.charge_in.temperature"], frame["charge_in.T"].to_numpy(), rtol=1e-12
    )
    final = results.end_state["module_states"][""]["tank"]["temperature"]
    assert final == pytest.approx(reference["final"], rel=1e-12)


def _leaves(tree, prefix=""):
    """Return the numbers of a nested state tree by dotted key."""
    found = {}
    for key, value in tree.items():
        path = f"{prefix}/{key}"
        found |= _leaves(value, path) if isinstance(value, dict) else {path: value}
    return found


@pytest.mark.parametrize("make", [(buffer_plant, buffer_frame), (lagged_plant, lagged_frame)])
def test_a_compiled_stateful_run_equals_the_eager_run_in_every_value(make):
    """The compiled scan has no graph break and gives the table and end state of the eager scan."""
    plant, frame = make[0], make[1](24)
    eager, _ = _run(plant(), frame, compile=False)
    compiled, engine = _run(plant(), frame, compile=True)
    assert engine.graph_breaks == {"": []}
    first, second = eager.to_frame(), compiled.to_frame()
    assert list(first.columns) == list(second.columns)
    numbers = first.select_dtypes("float").columns
    np.testing.assert_allclose(second[numbers], first[numbers], rtol=1e-9, atol=1e-12)
    assert _leaves(compiled.end_state["module_states"]) == pytest.approx(
        _leaves(eager.end_state["module_states"]), rel=1e-9
    )


def test_the_choice_of_a_scan_comes_from_the_declared_states():
    """A plant with a state steps in time; one without is evaluated on arrays, with no flag."""
    assert buffer_plant()._has_state()
    assert not gm.plants.get("Doublet")._has_state()


def test_a_state_connection_feeds_an_inlet_with_the_step_before():
    """The charge circuit is the discharge outlet of the previous step; the first has no flow."""
    results, _ = _run(lagged_plant(), lagged_frame(), compile=False)
    reference = buffer_reference(buffer_frame(24), lagged=True)
    table = results.to_frame()
    assert results.errors() == []
    np.testing.assert_allclose(table["tank.tank_temperature"], reference["temperature"], rtol=1e-12)
    np.testing.assert_allclose(
        table["tank.charge_in.temperature"][1:], reference["discharge_out"][:-1], rtol=1e-12
    )
    assert table["tank.charge_in.mass_flow"].iloc[0] == 0.0
    state = results.end_state["module_states"][""]
    assert state["@previous"]["tank.discharge_out"]["T"] == pytest.approx(
        reference["discharge_out"][-1], rel=1e-12
    )


def test_a_failed_step_leaves_the_state_as_it_was():
    """A step with a reverse flow is a failed row of NaN; the tank goes on from where it was."""
    frame = buffer_frame(12)
    frame.iloc[5, frame.columns.get_loc("charge_in.m_dot")] = -1.0
    results, _ = _run(buffer_plant(), frame)
    reference = buffer_reference(frame)
    assert [row["code"] for row in results.errors()] == ["out_of_range"]
    assert results.errors()[0]["time"] == frame.index[5].isoformat()
    temperature = results.to_frame()["tank.tank_temperature"].to_numpy()
    assert np.isnan(temperature[5]) and np.isnan(reference["temperature"][5])
    np.testing.assert_allclose(temperature, reference["temperature"], rtol=1e-12, equal_nan=True)
    assert results.end_state["module_states"][""]["tank"]["temperature"] == pytest.approx(
        reference["final"], rel=1e-12
    )


def test_a_stateful_run_in_pieces_equals_one_run():
    """The end state of a first piece starts the second: two scans give the numbers of one."""
    frame = buffer_frame(24)
    whole, _ = _run(buffer_plant(), frame)
    first, _ = _run(buffer_plant(), frame.iloc[:10])
    second = gm.Engine(buffer_plant())._simulate(
        gm.Dataset.from_frame(frame.iloc[10:]), None, first.end_state | {"position": None}
    )
    joined = np.concatenate(
        [first.to_frame()["tank.tank_temperature"], second.to_frame()["tank.tank_temperature"]]
    )
    np.testing.assert_array_equal(joined, whole.to_frame()["tank.tank_temperature"])


def test_gm_simulate_starts_a_storage_plant_from_the_initial_state_of_the_case():
    """The case states where the tank starts; the run is the hand-stepped one, with no state=."""
    case = with_state(physics(), {"tank": {"temperature": {"value": 320.0, "unit": "K"}}})
    frame = buffer_frame(12)
    results = gm.simulate(buffer_plant(), case, plan=gm.Dataset.from_frame(frame))
    reference = buffer_reference(frame)
    np.testing.assert_allclose(
        results.to_frame()["tank.tank_temperature"], reference["temperature"], rtol=1e-12
    )


def test_a_storage_plant_without_a_start_state_names_it():
    """No case and no state: the run raises ``missing_value`` naming the case path."""
    engine = gm.Engine(buffer_plant(), on_error="record")
    with raises(ValidationError, "missing_value", match="case.initial_state"):
        engine.simulate(gm.Dataset.from_frame(buffer_frame(3)))


def test_a_bug_in_a_step_stops_the_scan_with_the_state_before_it():
    """Under ``raise`` the ticks before the failing one are kept and so is the state after them."""
    plant = Plant("Faulty")
    plant.tank = FaultyTank()
    for port in ("charge_in", "discharge_in", "air_in"):
        plant.connect(port, f"tank.{port}")
    for port in ("charge_out", "discharge_out", "loss_out"):
        plant.connect(f"tank.{port}", port)
    plant = si.set_params(_fluid(plant), "tank", PARAMS)
    frame = buffer_frame(12)
    frame.iloc[6, frame.columns.get_loc("charge_in.m_dot")] = 7.0
    engine = gm.Engine(plant)
    with pytest.raises(RuntimeError, match="bug in the tank"):
        engine._simulate(gm.Dataset.from_frame(frame), None, START)
    assert len(engine.results) == 6 and engine.position == frame.index[5]
    assert engine.module_states[""]["tank"]["temperature"] == pytest.approx(
        buffer_reference(frame)["temperature"][6], rel=1e-12
    )


@pytest.mark.parametrize("compile", [False, True])
def test_a_stateful_plant_takes_the_tank_fluid_from_its_streams(compile):
    """A tank with no fluid of its own works on the fluid its inlet streams carry."""
    plant = buffer_plant()
    tank = plant.get_submodule("tank")
    object.__setattr__(tank, "_fluid", None)
    frame = buffer_frame(12)
    results, _ = _run(plant, frame, compile=compile)
    assert results.errors() == []
    np.testing.assert_allclose(
        results.to_frame()["tank.tank_temperature"],
        buffer_reference(frame)["temperature"],
        rtol=1e-12,
    )
