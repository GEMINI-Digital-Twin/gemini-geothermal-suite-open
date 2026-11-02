"""Many runs side by side: their executor requests are answered together, each run its own."""

import numpy as np

import gemini as gm
from gemini.compiler.interpret.batch import batch_results
from gemini.engine.executor import driven
from gemini.engine.lockstep import Lane, lockstep
from gemini.units import Quantity
from tests.fixtures.storage_plant import INITIAL, buffer_frame, buffer_plant


def _lane(plant, frame):
    engine = gm.Engine(plant)
    start = {"position": None, "module_states": {"": INITIAL}}
    return Lane(engine._simulate_steps(gm.Dataset.from_frame(frame), None, start)), engine


def _spy(monkeypatch):
    """Return the list of the sizes of the batches the graph executor evaluates."""
    sizes = []
    real = batch_results

    def counting(graph, module, feeds, rows):
        sizes.append(len(feeds))
        return real(graph, module, feeds, rows)

    monkeypatch.setattr("gemini.compiler.executor.batch_results", counting)
    return sizes


def test_trials_of_a_scan_carry_their_own_states_and_failed_steps(monkeypatch):
    """Three tanks of other volumes on other flows, one with a reverse flow, run as one scan."""
    sizes = _spy(monkeypatch)
    frames = []
    for scale, volume in ((1.0, 2.0), (1.4, 3.0), (0.6, 1.5)):
        frame = buffer_frame(8)
        frame["charge_in.m_dot"] = frame["charge_in.m_dot"] * scale
        frames.append((frame, volume))
    frames[1][0].loc[frames[1][0].index[3], "charge_in.m_dot"] = -1.0
    plants = []
    for _, volume in frames:
        plant = buffer_plant()
        plant.tank.volume = Quantity(volume, "m3")
        plants.append(plant)
    lanes = [_lane(plant, frame)[0] for plant, (frame, _) in zip(plants, frames)]
    together = lockstep(lanes)
    assert sizes == [3]
    for (frame, volume), found in zip(frames, together):
        plant = buffer_plant()
        plant.tank.volume = Quantity(volume, "m3")
        alone, _ = _lane(plant, frame)
        reference = driven(alone.steps)
        first, second = found.to_frame(), reference.to_frame()
        numbers = first.select_dtypes("float").columns
        np.testing.assert_allclose(first[numbers], second[numbers], rtol=1e-12, equal_nan=True)
        assert found.errors() == reference.errors()
        assert found.end_state == reference.end_state
    assert len(together[1].errors()) == 1 and together[0].errors() == []


def test_a_module_that_cannot_be_batched_runs_alone_with_its_own_plant():
    """A request of an executor that is not ``batchable`` is run by the driver, one at a time."""
    frame = buffer_frame(4)
    plants = [buffer_plant(), buffer_plant()]
    engines = [gm.Engine(plant, compile=False) for plant in plants]
    start = {"position": None, "module_states": {"": INITIAL}}
    lanes = [Lane(e._simulate_steps(gm.Dataset.from_frame(frame), None, start)) for e in engines]
    first, second = lockstep(lanes)
    numbers = first.to_frame().select_dtypes("float").columns
    np.testing.assert_array_equal(first.to_frame()[numbers], second.to_frame()[numbers])
