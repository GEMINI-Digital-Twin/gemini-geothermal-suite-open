"""The doublet heat plant built two ways runs bit-identically, on every backend.

The builder and the plant dict give the same plant, so their replays are equal to the last bit
(``check_exact``), and the run is the one the committed engine reference pins in
``test_engine.py``.
"""

import copy

import pandas as pd
import pytest

import gemini as gm
from gemini.modules.bindings import DatedParams
from gemini.plants._utils import form, plant_inputs
from gemini.streams.fluid import Fluid
from tests.fixtures.parity import BACKENDS, on_each_backend, run_engine
from tests.fixtures.sample_cases import example_plant

ROWS = 24


def _add_modules(plant, modules, prefix=""):
    for name, entry in modules.items():
        key = f"{prefix}.{name}" if prefix else name
        plant.add(entry["type"], key)
        _add_modules(plant, entry.get("modules", {}), key)


def _fill_sections(plant, spec):
    for path, value in spec.get("fluids", {}).items():
        plant.get_submodule(path)._set_own_fluid(value)
    for path, value in spec.get("boundary", {}).items():
        plant.get_submodule(path).boundary = copy.deepcopy(value)
    for path, bound in example_plant("DoubletHeatPlant").bindings.items():
        plant.bindings[path] = copy.deepcopy(bound)
    found = {}
    form._walk(spec["params"], "", found, [])
    declared = plant.inputs()
    ported = lambda path: plant_inputs._port_field(plant, path) is not None  # noqa: E731
    values = {form.flat_name(path): form.flat_value(node) for path, node in found.items()}
    values = {path: value for path, value in values.items() if value is not form.MISSING}
    plant.set_params(
        "", {path: v for path, v in values.items() if path not in declared and not ported(path)}
    )
    inputs = {path: v for path, v in values.items() if path in declared or ported(path)}
    plant.set_inputs(
        {
            path: Fluid.model_validate(v) if path.endswith(".fluid") else v
            for path, v in inputs.items()
        }
    )
    for path, history in form._history(found).items():
        plant.get_submodule(path)._param_history = [DatedParams.model_validate(i) for i in history]


def built_by_hand(spec):
    """Build the doublet heat plant with ``add``, ``connect`` and the setters only."""
    plant = gm.Plant(spec["name"])
    _add_modules(plant, spec["modules"])
    for connection in spec["connections"]:
        plant.connect(connection["source"], connection["target"])
    for name, end in spec["inlets"].items():
        for item in end if isinstance(end, list) else [end]:
            plant.connect(name, item)
    for name, end in spec["outlets"].items():
        for item in end if isinstance(end, list) else [end]:
            plant.connect(item, name)
    _fill_sections(plant, spec)
    return plant


@pytest.fixture(scope="module")
def spec():
    """Return the plant file of the example with its structure and no class, a plant of no class."""
    data = example_plant("DoubletHeatPlant").to_dict(structure=True)
    return {key: value for key, value in data.items() if key != "type"}


@pytest.fixture(scope="module")
def window(fast_frame):
    """Return the first rows of the short window as a dataset."""
    return gm.Dataset.from_frame(fast_frame.iloc[:ROWS], time_column="time")


def read_with_bindings(spec):
    """Return the plant of the file, with the bindings to the measured columns it does not hold."""
    plant = gm.Plant.from_dict(copy.deepcopy(spec))
    for path, bound in example_plant("DoubletHeatPlant").bindings.items():
        plant.bindings[path] = copy.deepcopy(bound)
    return plant


BUILDERS = {"builder": built_by_hand, "spec": read_with_bindings}


@pytest.fixture(scope="module")
def runs(spec, window):
    """Return the replay and simulate frames of each way of building the plant, per backend."""
    clock = gm.engine.Clock.days(2024, 6, 7)
    first = window.read(window.start, window.start)
    assumed = gm.Dataset.from_frame(pd.DataFrame([first.iloc[0].to_dict()] * 24, index=list(clock)))

    def run(backend):
        return {
            way: (
                run_engine(build(spec), window),
                run_engine(build(spec), assumed, "simulate", clock),
            )
            for way, build in BUILDERS.items()
        }

    return on_each_backend(run)


def test_the_two_ways_give_the_same_plant(spec):
    """Builder, spec and file write the same sections; only the spec states the outputs."""
    by_hand = built_by_hand(spec).to_dict()
    assert gm.Plant.from_dict(copy.deepcopy(spec)).to_dict() == spec
    assert by_hand.pop("outputs", None) is None
    assert by_hand == {key: value for key, value in spec.items() if key != "outputs"}


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("kind", [0, 1], ids=["replay", "simulate"])
def test_the_two_ways_run_bit_identically(runs, backend, kind):
    """Spec and file are the same frame; the builder's columns equal the spec's, bit for bit."""
    frames = {way: pair[kind].frame for way, pair in runs[backend].items()}
    assert len(frames["spec"]) == ROWS
    common = [column for column in frames["builder"].columns if column in frames["spec"].columns]
    assert len(common) == len(frames["builder"].columns)
    pd.testing.assert_frame_equal(frames["builder"], frames["spec"][common], check_exact=True)


CLASS_BASED_ROOT = {
    "thermal_power": 3314218.4332571737,
    "electricity": 206436.37109026566,
    "cop": 16.054430795085086,
    "heat_loss": 1727799.1814901084,
}
"""The root outputs of simulate tick 3, written by the handwritten ``DoubletHeatPlant`` class."""


@pytest.mark.parametrize("way", ["builder", "spec"])
def test_root_outputs_equal_the_handwritten_class_to_the_last_bit(runs, way):
    """The root has no output; what the class summed is the same on the leaves."""
    run = runs[BACKENDS[0]][way][1]
    assert run.steps[3]["trees"][""]["outputs"] == {}
    row = run.frame.iloc[3]
    assert row["heat_exchanger.duty"] == pytest.approx(CLASS_BASED_ROOT["thermal_power"], rel=1e-12)
    electricity = row[[name for name in row.index if name.endswith(".power_in")]]
    losses = row[[name for name in row.index if name.endswith(".loss_out")]]
    assert electricity.sum() == pytest.approx(CLASS_BASED_ROOT["electricity"], rel=1e-12)
    assert losses[losses > 0].sum() == pytest.approx(CLASS_BASED_ROOT["heat_loss"], rel=1e-12)
