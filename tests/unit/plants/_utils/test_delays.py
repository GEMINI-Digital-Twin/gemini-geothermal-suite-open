"""State connections: the value a source outlet had at the step before, kept in the plant state."""

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.modules.storage import ThermalStorage
from gemini.plants._utils import delays
from tests.fixtures.errors import raises
from tests.fixtures.storage_plant import (
    INITIAL,
    LaggedBuffer,
    buffer_frame,
    buffer_plant,
    lagged_frame,
    lagged_plant,
)

START = {"position": None, "module_states": {"": INITIAL}}


def test_only_a_connection_of_type_state_is_a_delay():
    """A plant with a state connection has delays and is stateful; a plain one has neither."""
    assert delays.has_delays(LaggedBuffer())
    assert LaggedBuffer().stateful
    assert not delays.has_delays(gm.plants.get("Doublet"))


def test_a_delay_is_in_the_state_and_starts_at_rest():
    """The first step reads no flow; the next reads what the outlet gave."""
    frame = lagged_frame(3)
    results = gm.Engine(lagged_plant())._simulate(gm.Dataset.from_frame(frame), None, START)
    kept = results.end_state["module_states"][""][delays.PREVIOUS]["tank.discharge_out"]
    assert set(kept) == {"m_dot", "T", "p"}
    flow = results.to_frame()["tank.charge_in.mass_flow"]
    assert flow.iloc[0] == 0.0
    assert flow.iloc[1] == pytest.approx(frame["discharge_in.m_dot"].iloc[0])


def test_a_source_without_a_first_guess_is_named():
    """A module that cannot guess its outlet temperature gives the connection no first value."""
    plant = lagged_plant()
    plant.tank.__class__ = ThermalStorage
    engine = gm.Engine(plant)
    with raises(ValidationError, "invalid_design", match="tank.discharge_out"):
        engine._simulate(gm.Dataset.from_frame(lagged_frame(3)), None, START)


def test_a_plant_without_delays_keeps_none_in_its_state():
    """The state of a plain buffer holds the tank only."""
    results = gm.Engine(buffer_plant())._simulate(
        gm.Dataset.from_frame(buffer_frame(3)), None, START
    )
    assert delays.PREVIOUS not in results.end_state["module_states"][""]


def test_a_state_connection_is_in_the_structure_form_and_comes_back():
    """The plant file holds it as a connection of type ``state``: no key of its own."""
    plant = gm.Plant("State")
    plant.add("Pipe", "one")
    plant.add("Pipe", "two")
    plant.connect("one.fluid_out", "two.fluid_in")
    plant.connect("two.fluid_out", "one.fluid_in", type="state")
    for name in ("one", "two"):
        plant.connect("air", f"{name}.air_in")
        plant.connect(f"{name}.loss_out", "loss")
    data = plant.to_dict(structure=True)
    assert {"source": "two.fluid_out", "target": "one.fluid_in", "type": "state"} in data[
        "connections"
    ]
    again = gm.Plant.from_dict(data)
    assert delays.has_delays(again)
