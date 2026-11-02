"""A stateful plant is one scan: nested states, a loop inside the body and failed steps."""

import numpy as np
import pytest

import gemini as gm
from gemini.compiler.cache import GraphCache
from gemini.compiler.trace.states import leaf_unit, state_leaves
from gemini.modules.declarations import State
from gemini.modules.storage.aquiferstorage import CHARGE, DISCHARGE, IDLE, MODES
from tests.fixtures import si
from tests.fixtures.scan_run import same_rows, scanned, stepped
from tests.fixtures.storage_plant import lagged_plant
from tests.unit.compiler.test_loops import Circuit, Drifting, Relaxer
from tests.unit.modules.storage.test_aquiferstorage import COLD, EMPTY, WARM, storage

ROWS = 5
STEPS = np.full(ROWS, 900.0)
TUNING = dict(
    proportional_gain=2.0,
    integral_time=100.0,
    minimum_output=0.0,
    maximum_output=1.0,
    direction="reverse",
)
BACKENDS = ["numpy", "python"]


def _store():
    """Return an ice store and a controller in one plant: two stateful children, one connection."""
    plant = gm.Plant("store")
    plant.fluid = gm.streams.fluid.GLYCOL_30
    si.add(plant, "IceStorage", "ice", dict(water_mass=1000.0, thermal_conductance=2000.0))
    si.add(plant, "PIDController", "ctrl", TUNING)
    plant.connect("feed", "ice.fluid_in")
    plant.connect("ice.fluid_out", "return")
    return plant


def _store_run():
    columns = {
        "feed": dict(
            m_dot=np.array([2.0, 2.0, 1.0, 3.0, 2.0]),
            T=np.array([268.0, 270.0, 276.0, 268.0, 272.0]),
            p=np.full(ROWS, 3e5),
        )
    }
    inputs = {"ctrl.setpoint": 1.0, "ctrl.measurement": np.array([0.9, 0.7, 0.8, 1.2, 0.5])}
    state = {
        "ice": {"ice_fraction": 0.4, "temperature": 273.15},
        "ctrl": {"integral": 0.0, "previous_error": 0.0, "previous_step": 0.0},
    }
    return columns, inputs, state


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_plant_with_two_stateful_children_equals_its_steps(backend):
    """The nested state tree and every child result equal one ``Plant.step`` per row."""
    plant = _store()
    fluids = {"feed": plant.fluid}
    columns, inputs, state = _store_run()
    rows, last = stepped(plant, fluids, columns, inputs, state, STEPS)
    evaluation = scanned(plant, fluids, columns, inputs, state, STEPS, backend)
    assert evaluation.breaks == [] and not evaluation.failed.any()
    same_rows(evaluation, rows)
    assert evaluation.states["ice"] == pytest.approx(last["ice"], rel=1e-9)
    assert evaluation.states["ctrl"] == pytest.approx(last["ctrl"], rel=1e-9)
    assert set(evaluation.result.children) == {"ice", "ctrl"}


def test_the_number_of_states_is_in_the_key_of_the_graph():
    """A plant with one more stateful child is another graph with its own carries."""
    cache = GraphCache()
    plant = _store()
    fluids = {"feed": plant.fluid}
    graph = cache.graph(plant, fluids, stepped=True)
    assert [leaf for leaf, _ in graph.states] == [
        ("ice", "ice_fraction"),
        ("ice", "temperature"),
        ("ctrl", "integral"),
        ("ctrl", "previous_error"),
        ("ctrl", "previous_step"),
    ]
    other = gm.Plant("store")
    other.fluid = plant.fluid
    si.add(other, "IceStorage", "ice", dict(water_mass=1000.0, thermal_conductance=2000.0))
    other.connect("feed", "ice.fluid_in")
    other.connect("ice.fluid_out", "return")
    assert len(cache.graph(other, fluids, stepped=True).states) == 2 and cache.traces == 2


class Lagging(Relaxer):
    """A relaxer that moves towards a lagged target: the lag is a state that follows ``target``."""

    abstract = True

    def __init__(self):
        """Declare the lag."""
        super().__init__()

        # States
        self.lag = State(float)

    def forward(self, inputs, inlets, state):
        """Relax towards the lag, linearly."""
        inlet = inlets.fluid_in
        slope = inputs["slope"]
        temperature = slope * inlet.T + (1 - slope) * state["lag"]
        outlet = inlet._with_si(T=temperature, m_dot=inputs["flow"])
        return dict(drop=inlet.T - outlet.T), dict(fluid_out=outlet)

    def update(self, inputs, inlets, outlets, state, dt):
        """Move the lag a third of the way to the target."""
        return dict(lag=state["lag"] + (inputs["target"] - state["lag"]) / 3)


class DriftingLag(Drifting):
    """A drifting relaxer that also counts the drift in a state: it never settles unless 0."""

    abstract = True

    def __init__(self):
        """Declare the count."""
        super().__init__()

        # States
        self.count = State(float)

    def update(self, inputs, inlets, outlets, state, dt):
        """Add the drift to the count."""
        return dict(count=state["count"] + inputs["target"])


def _ring(cls, passes=50):
    ring = type("StatefulRing", (Circuit,), {"relaxer_class": cls, "abstract": True})
    plant = ring()
    plant.loop_passes = passes
    return plant


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_loop_inside_the_scan_converges_in_each_step_as_alone(backend):
    """The fixed point of a closed circuit runs inside every row, with the lag of the step."""
    plant = _ring(Lagging)
    inputs = {
        "relaxer.target": np.array([340.0, 300.0, 350.0, 320.0, 310.0]),
        "relaxer.slope": np.array([0.5, 0.5, 0.9, 0.5, 0.7]),
        "relaxer.flow": np.array([2.0, 2.0, 3.0, 0.0, 1.0]),
    }
    state = {"relaxer": {"lag": 330.0}}
    rows, last = stepped(plant, {}, {}, inputs, state, STEPS)
    evaluation = scanned(plant, {}, {}, inputs, state, STEPS, backend)
    assert evaluation.breaks == [] and not evaluation.failed.any()
    assert "fixed_point" in evaluation.graph.describe()
    same_rows(evaluation, rows)
    assert evaluation.states["relaxer"]["lag"] == pytest.approx(last["relaxer"]["lag"])


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_loop_that_does_not_close_fails_its_step_and_leaves_the_state(backend):
    """The row that drifts is ``loop_not_converged``; the state skips it and the run goes on."""
    plant = _ring(DriftingLag, passes=4)
    inputs = {"relaxer.target": np.array([0.0, 1.0, 0.0, 0.0, 2.0])}
    state = {"relaxer": {"count": 0.0}}
    rows, last = stepped(plant, {}, {}, inputs, state, STEPS)
    assert [kind for kind, _ in rows] == ["ok", "error", "ok", "ok", "error"]
    evaluation = scanned(plant, {}, {}, inputs, state, STEPS, backend)
    same_rows(evaluation, rows)
    assert evaluation.error(1).code == "loop_not_converged"
    assert evaluation.states == last == {"relaxer": {"count": 0.0}}


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_text_mode_is_fed_as_its_position_and_the_store_steps_as_alone(backend):
    """The aquifer well pair is traced: a column of modes gives the rows of its own steps."""
    module = storage()
    modes = ["charge", "charge", "idle", "discharge", "discharge", "idle", "idle"]
    columns = {
        "injection_in": dict(
            m_dot=np.array([30.0, 20.0, 0.0, 30.0, 10.0, 0.0, 5.0]),
            T=np.array([COLD.T, WARM.T, WARM.T, COLD.T, COLD.T, WARM.T, WARM.T]),
            p=np.full(7, 3e5),
        )
    }
    steps = np.full(7, 3600.0)
    fluids = {"injection_in": WARM.fluid}
    inputs = {"mode": np.array(modes)}
    rows, last = stepped(module, fluids, columns, inputs, EMPTY, steps)
    assert [kind for kind, _ in rows][-1] == "error"
    evaluation = scanned(module, fluids, columns, inputs, EMPTY, steps, backend)
    assert evaluation.breaks == []
    same_rows(evaluation, rows)
    assert evaluation.states == pytest.approx(last, rel=1e-9)


def test_the_options_of_the_mode_are_the_positions_the_module_selects_with():
    """``CHARGE``, ``DISCHARGE`` and ``IDLE`` are the places of the three texts in the options."""
    options = storage()._controls["mode"]._options()
    assert options == MODES == ("charge", "discharge", "idle")
    assert (options[CHARGE], options[DISCHARGE], options[IDLE]) == MODES


def test_a_state_connection_is_three_carries_of_the_plant_state():
    """A delayed stream is its ``m_dot``, ``T`` and ``p`` under ``@previous`` in the plant state."""
    plant = lagged_plant()
    leaves = state_leaves(plant)
    key = "tank.discharge_out"
    assert leaves == [
        *(("@previous", key, field) for field in ("m_dot", "T", "p")),
        ("tank", "temperature"),
    ]
    assert [leaf_unit(plant, leaf) for leaf in leaves[:3]] == ["kg/s", "K", "Pa"]
