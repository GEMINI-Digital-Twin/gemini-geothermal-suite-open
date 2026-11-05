"""Unit tests for gemini_simulator.solver.Solver."""

import pytest

from gemini_model.model_abstract import DynamicModel, StaticModel
from gemini_simulator.solver import Solver


class AddOne(StaticModel):
    """Static test component: output = input + 1."""

    def __init__(self):
        """Initialize empty parameters/output dicts."""
        self.parameters = {}
        self.output = {}

    def calculate_output(self, u, x=None):
        """Set output value to input value plus one."""
        self.output["value"] = u["value"] + 1


class Accumulator(DynamicModel):
    """Dynamic test component: sums its input over time into internal state."""

    def __init__(self):
        """Initialize empty parameters/output dicts."""
        self.parameters = {}
        self.output = {}

    def initialize_state(self, x):
        """Return the initial state with a running total of zero."""
        return {"total": 0.0}

    def update_state(self, u, x):
        """Return the next state, adding this step's input to the total."""
        return {"total": x["total"] + u["value"]}

    def calculate_output(self, u, x):
        """Set output total to the current state's running total."""
        self.output["total"] = x["total"]


def test_single_connection_steady_state():
    """A single connection should propagate values through the solver."""
    solver = Solver({"a": AddOne(), "b": AddOne()})
    solver.set_boundary_input("a", "value", 1)
    solver.connect("a", "b", "value", "value")

    solver.run()

    assert solver.get_output("a", "value") == 2
    assert solver.get_output("b", "value") == 3


def test_grouped_connections_to_same_successor_need_no_preseed():
    """Grouped connections to the same successor should need no pre-seed."""
    from gemini_model.adder.adder import Adder

    solver = Solver({"a": AddOne(), "b": AddOne(), "adder": Adder()})
    solver.set_boundary_input("a", "value", 1)
    solver.set_boundary_input("b", "value", 10)
    # Consecutive connections into the same successor are grouped: the
    # Adder is only evaluated once both input_0 and input_1 are wired,
    # so no placeholder pre-seed is needed.
    solver.connect("a", "adder", "value", "input_0")
    solver.connect("b", "adder", "value", "input_1")

    solver.run()

    assert solver.get_output("adder", "output") == 2 + 11


def test_unknown_component_raises():
    """Connecting an unknown component should raise a KeyError."""
    solver = Solver({"a": AddOne()})
    with pytest.raises(KeyError):
        solver.connect("a", "missing", "value", "value")


def test_dynamic_component_accumulates_state_over_timesteps():
    """A dynamic component's state should accumulate across timesteps."""
    solver = Solver({"a": AddOne(), "acc": Accumulator()})
    solver.set_boundary_input("a", "value", 1)
    solver.connect("a", "acc", "value", "value")

    solver.run(time_vector=[0, 1, 2])

    # each timestep a.value=2 is fed into acc; state accumulates *before* being
    # read, so calculate_output at each step reports the running total prior
    # to that step's contribution
    totals = [snapshot["total"] for snapshot in solver.history["acc"]["output"]]
    assert totals == [0.0, 2.0, 4.0]


def test_history_records_every_timestep():
    """The solver's history should record every simulated timestep."""
    solver = Solver({"a": AddOne(), "b": AddOne()})
    solver.set_boundary_input("a", "value", 1)
    solver.connect("a", "b", "value", "value")

    solver.run(time_vector=[0, 1, 2])

    assert len(solver.history["a"]["output"]) == 3
    assert len(solver.history["b"]["output"]) == 3


def test_boundary_input_on_unknown_component_raises():
    """Setting a boundary input on an unknown component should raise KeyError."""
    solver = Solver({"a": AddOne()})
    with pytest.raises(KeyError):
        solver.set_boundary_input("missing", "value", 1)
