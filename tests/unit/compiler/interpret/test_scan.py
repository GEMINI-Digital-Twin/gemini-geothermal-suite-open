"""A stateful module is the body of a scan: the compiled rows equal the steps one by one."""

import numpy as np
import pytest

import gemini as gm
from gemini import ops
from gemini.compiler.cache import GraphCache
from gemini.compiler.trace.tracer import Tracer
from gemini.errors import PhysicsError
from gemini.modules import Module
from gemini.modules.control import PIDController
from gemini.modules.declarations import Control, Inlet, Outlet, Output, State
from gemini.modules.storage import IceStorage, ThermalStorage
from gemini.modules.subsurface import BoreholeField, ThermalDecline
from gemini.streams.flows import Stream
from gemini.streams.fluid import AIR, BRINE, GLYCOL_30
from tests.fixtures import purity, si
from tests.fixtures.designs import with_values
from tests.fixtures.scan_run import same_rows, scanned, stepped
from tests.unit.compiler.conftest import Tank

ROWS = 4
STEPS = np.full(ROWS, 600.0)
BACKENDS = ["numpy", "python"]


def _stream(mass_flow, temperature, pressure):
    return dict(
        m_dot=np.asarray(mass_flow, dtype=float),
        T=np.full(ROWS, temperature),
        p=np.full(ROWS, pressure),
    )


def _pid():
    module = si.set_params(
        PIDController(),
        "",
        dict(
            proportional_gain=2.0,
            integral_time=100.0,
            derivative_time=20.0,
            minimum_output=0.0,
            maximum_output=1.0,
            direction="reverse",
        ),
    )
    inputs = {"setpoint": 1.0, "measurement": np.array([0.9, 0.85, 1.1, 0.6])}
    state = {"integral": 0.0, "previous_error": 0.0, "previous_step": 0.0}
    return module, {}, {}, inputs, state


def _thermal_storage():
    module = si.set_params(
        with_values(ThermalStorage()),
        "",
        dict(
            service="hot",
            volume=2.0,
            heat_loss_conductance=10.0,
            reference_temperature=313.15,
            charge_effectiveness=0.8,
            discharge_effectiveness=0.9,
        ),
    )
    fluids = {"charge_in": BRINE, "discharge_in": BRINE, "air_in": AIR}
    columns = {
        "charge_in": _stream([1.0, 2.0, 3.0, 2.0], 340.0, 3e5),
        "discharge_in": _stream([2.0, 1.0, 0.5, 1.0], 300.0, 3e5),
        "air_in": _stream(np.zeros(ROWS), 290.0, 101325.0),
    }
    return module, fluids, columns, {}, {"temperature": 320.0}


def _ice_storage():
    module = si.set_params(IceStorage(), "", dict(water_mass=1000.0, thermal_conductance=2000.0))
    columns = {"fluid_in": _stream([2.0, 2.0, 1.0, 3.0], 268.0, 3e5)}
    return (
        module,
        {"fluid_in": GLYCOL_30},
        columns,
        {},
        {"ice_fraction": 0.4, "temperature": 273.15},
    )


def _borehole_field():
    module = si.set_params(BoreholeField(), "", purity.FIELD)
    columns = {"fluid_in": _stream([2.0, 3.0, 4.0, 3.0], 273.15, 3e5)}
    return module, {"fluid_in": BRINE}, columns, {}, {"ground_temperature_change": 0.0}


def _thermal_decline():
    module = si.set_params(ThermalDecline(), "", purity.DECLINE)
    columns = {"fluid_in": _stream([40.0, 50.0, 60.0, 50.0], 353.15, 2e7)}
    inputs = {"injection_temperature": np.array([300.0, 310.0, 320.0, 310.0])}
    return module, {"fluid_in": BRINE}, columns, inputs, {"injected_volume": 0.0}


CASES = {
    "PIDController": _pid,
    "ThermalStorage": _thermal_storage,
    "IceStorage": _ice_storage,
    "BoreholeField": _borehole_field,
    "ThermalDecline": _thermal_decline,
}


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("name", CASES)
def test_a_stateful_module_compiled_equals_its_steps(name, backend):
    """Outputs, outlets and the last state equal one ``Module.step`` per row, to 1e-9."""
    module, fluids, columns, inputs, state = CASES[name]()
    rows, last = stepped(module, fluids, columns, inputs, state, STEPS)
    evaluation = scanned(module, fluids, columns, inputs, state, STEPS, backend)
    assert evaluation.breaks == [] and not evaluation.failed.any()
    same_rows(evaluation, rows)
    assert evaluation.states == pytest.approx(last, rel=1e-9, abs=1e-9)
    assert evaluation.stepped


def test_the_graph_is_one_scan_and_holds_no_root_break():
    """The body carries the states and the step length is an input of the graph."""
    module = Tank()
    graph = GraphCache().graph(module, {"fluid_in": gm.WATER}, stepped=True)
    assert not graph.root_break and graph.stepped and graph.breaks == []
    assert [leaf for leaf, _ in graph.states] == [("level",)]
    assert graph.inputs["dt"].role == "dt" and graph.inputs["state.level"].role == "state"
    assert [node.op for node in graph.nodes if node.kind == "scan"].count("scan") == 1
    assert "scan(" in graph.describe() and "carry" in graph.describe()


def test_a_stateful_module_that_is_not_stepped_is_a_root_break():
    """Without a step there is no state to start from, so the module runs for real."""
    graph = Tracer().trace(Tank(), {"fluid_in": gm.WATER})
    assert graph.root_break and "not stepped" in graph.breaks[0][1]


def test_the_state_values_are_inputs_so_one_trace_serves_every_start():
    """Two runs from other states and step lengths reuse the graph and give their own numbers."""
    cache = GraphCache()
    module = Tank()
    columns = {"fluid_in": _stream([1.0, 2.0, 3.0, 4.0], 300.0, 1e5)}
    fluids = {"fluid_in": gm.WATER}
    first = scanned(module, fluids, columns, {}, {"level": 0.0}, STEPS, cache=cache)
    second = scanned(module, fluids, columns, {}, {"level": 100.0}, STEPS / 2, cache=cache)
    assert cache.traces == 1
    assert first.result.outputs["content"].tolist() == [1.0, 3.0, 6.0, 10.0]
    assert second.result.outputs["content"].tolist() == [101.0, 103.0, 106.0, 110.0]
    assert first.states == {"level": 10.0} and second.states == {"level": 110.0}


class Cistern(Module):
    """A tank that is drawn down by a control: the draw is refused above 5, the level is >= 0."""

    def __init__(self):
        """Declare a bounded state, a draw, an inlet and an outlet."""
        super().__init__()
        self.fluid = BRINE

        # States
        self.level = State(float, ge=0)

        # Inlets
        self.fluid_in = Inlet(Stream)

        # Controls
        self.draw = Control(float)

        # Outputs
        self.left = Output(float)

        # Outlets
        self.fluid_out = Outlet(Stream)

    def forward(self, inputs, inlets, state):
        """Report the level after the draw; refuse a draw above 5."""
        ops.check(
            inputs["draw"] <= 5,
            PhysicsError,
            "{path}: draw = {draw}",
            path=self.path,
            draw=inputs["draw"],
        )
        return dict(left=state["level"] - inputs["draw"]), dict(fluid_out=inlets.fluid_in)

    def update(self, inputs, inlets, outlets, state, dt):
        """Lower the level by the draw."""
        return dict(level=state["level"] - inputs["draw"])


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_failed_step_is_nan_does_not_advance_and_the_run_goes_on(backend):
    """A refused draw and a level below its bound fail their rows as a step does; the rest runs."""
    module = Cistern()
    columns = {"fluid_in": _stream(np.ones(ROWS), 300.0, 1e5)}
    fluids = {"fluid_in": BRINE}
    inputs = {"draw": np.array([1.0, 9.0, 8.0, 2.0])}
    rows, last = stepped(module, fluids, columns, inputs, {"level": 10.0}, STEPS)
    assert [kind for kind, _ in rows] == ["ok", "error", "error", "ok"]
    evaluation = scanned(module, fluids, columns, inputs, {"level": 10.0}, STEPS, backend)
    assert evaluation.failed.tolist() == [False, True, True, False]
    same_rows(evaluation, rows)
    assert np.isnan(evaluation.result.outputs["left"][[1, 2]]).all()
    assert evaluation.states == last == {"level": 7.0}


def test_a_state_below_its_bound_is_the_error_of_the_plain_step():
    """The error is that of ``Declaration.validate`` of the state, as the plain step raises it."""
    module = Cistern()
    columns = {"fluid_in": _stream(np.ones(ROWS), 300.0, 1e5)}
    inputs = {"draw": np.array([4.0, 4.0, 4.0, 4.0])}
    rows, _ = stepped(module, {"fluid_in": BRINE}, columns, inputs, {"level": 10.0}, STEPS)
    evaluation = scanned(module, {"fluid_in": BRINE}, columns, inputs, {"level": 10.0}, STEPS)
    assert evaluation.failed.tolist() == [False, False, True, True]
    assert "level" in str(evaluation.error(2))
    same_rows(evaluation, rows)


def test_a_state_missing_from_the_start_is_named():
    """The run is refused naming the state, as a plain call is."""
    with pytest.raises(gm.errors.ValidationError, match="state level has no value") as caught:
        columns = {"fluid_in": _stream(np.ones(ROWS), 300.0, 1e5)}
        scanned(Tank(), {"fluid_in": gm.WATER}, columns, {}, {}, STEPS)
    assert caught.value.code == "missing_value"
