"""One plant for the trials of a batch: its state is saved, put back and reset."""

from copy import deepcopy

from gemini.study._utils import trial
from gemini.study._utils.shared import STATE, Shared
from gemini.units import Quantity
from tests.unit.engine.schedule.test_schedule import plant_of_two
from tests.unit.study._utils.test_batch import VALUED, _case


def _state(plant):
    """Return every piece of state a trial can change, by module path."""
    return {
        path: (
            {name: module.__dict__.get(name) for name in STATE}
            | {"history": [(item.valid_from, item.params) for item in module._param_history]},
            {name: parameter.value for name, parameter in module._parameters.items()},
        )
        for path, module in plant.named_modules()
    }


def test_the_shared_plant_is_put_back_as_the_copy_was_made():
    """After trials that set parameters, apply a case and run, ``reset`` leaves the copy's state."""
    plant, case = plant_of_two(), _case()
    shared = Shared(plant)
    before = deepcopy(_state(shared.plant))
    trial.run_trials(shared, case, None, VALUED, ["peak_heat"], True)
    assert _state(shared.plant) != before
    shared.reset()
    assert _state(shared.plant) == before
    assert plant.get_submodule("boiler").capacity == Quantity(40, "MW").si
