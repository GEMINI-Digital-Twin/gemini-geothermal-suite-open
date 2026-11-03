"""The doublet heat replay on arrays equals the replay row by row, to the backend tolerance."""

import copy

import pandas as pd
import pytest

import gemini as gm
from tests.fixtures.designs import with_values
from tests.fixtures.parity import BACKENDS, assert_frames_match


def _replay(plant, dataset, backend):
    engine = gm.Engine(plant, backend)
    return engine, engine.replay(dataset)


def test_doublet_heat_replay_is_identical_on_both_backends(shared_plant, fast_frame):
    """Every column, dtype, skip count, error and summary entry agrees over one day.

    The numbers agree to the backend tolerance: NumPy's kernels and ``math`` differ in the last bit
    of ``log`` and ``pow`` on some CPUs. Dtypes and skips, which do not depend on it, are exact.
    """
    dataset = gm.Dataset.from_frame(fast_frame.iloc[:96], time_column="time")
    engine, traced = _replay(copy.deepcopy(shared_plant), dataset, "numpy")
    _, plain = _replay(copy.deepcopy(shared_plant), dataset, "python")
    assert_frames_match(traced.to_frame(), plain.to_frame())
    assert traced.to_frame().dtypes.tolist() == plain.to_frame().dtypes.tolist()
    assert traced.skip_counts == plain.skip_counts and traced.errors() == plain.errors()
    assert_frames_match(traced.to_frame(table="energy"), plain.to_frame(table="energy"))
    assert all(reasons == [] for reasons in engine.graph_breaks.values())


def port_free_plant():
    """Return a root plant with no plant port, which every root plant must be."""
    plant = gm.Plant("Closed")
    plant.add(
        "Valve", name="valve", params={"flow_coefficient": {"value": 60, "unit": "m3/h/bar^0.5"}}
    )
    plant.add(
        "HeatingGrid",
        name="users",
        params={
            "return_temperature": {"value": 60, "unit": "degC"},
            "return_pressure": {"value": 6, "unit": "bar"},
        },
    )
    plant.connect("users.return_out", "valve.fluid_in")
    plant.connect("valve.fluid_out", "users.supply_in")
    return with_values(plant)


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_failing_row_of_a_plant_without_ports_is_an_error(backend):
    """A root plant has no outlet for an error to reach: the row still fails, with either policy.

    A physical failure of a step is a result of a simulation, so the default policy finishes too.
    """
    index = pd.date_range("2027-01-01", periods=2, freq="D", tz="UTC", name="time")
    columns = {"users.flow": 10.0, "users.heat_demand": 0.0, "valve.opening": [1.0, 0.0]}
    frame = pd.DataFrame(columns, index=index)
    results = gm.simulate(port_free_plant(), plan=frame, on_error="record", backend=backend)
    assert [item["time"][:10] for item in results.errors()] == ["2027-01-02"]
    default = gm.simulate(port_free_plant(), plan=frame, backend=backend)
    assert default.errors() == results.errors()
