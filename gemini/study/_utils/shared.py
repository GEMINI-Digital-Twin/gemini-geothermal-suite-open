"""One plant for many trials: the values a trial sets are saved and put back, nothing is copied.

A trial of a study sets its variables on a plant, applies the case, runs and reads the metrics.
``Shared`` holds one copy of the plant for all the trials of a batch. ``reset`` puts the plant
back as the copy was made, a trial sets its values, ``capture`` keeps the plant as that trial has
it (``Held``) and ``Held.restore`` puts it back whenever the trial goes on, so trials that wait for
one array pass between their steps each see their own values. Only the state a trial changes is
saved: the parameter values, the dated parameter snapshots, the persisted controls and boundaries,
the fluids and the records of what was stated; the structure is the plant's, equal for every trial.
"""

from copy import deepcopy

import numpy as np

from gemini.engine.apply import remember_case
from gemini.streams.fluid import Fluid

STATE = (
    "_param_overrides",
    "_input_values",
    "_inputs",
    "_fluid",
    "_derived_params",
    "_stated",
    "_stated_child_params",
    "_baselines",
)
"""The attributes of a module that setting a value, applying a case or a run changes."""

_MISSING = object()
_PLAIN = (str, int, float, bool, type(None), frozenset)


def _clone(value):
    """Return a copy of ``value`` that shares nothing mutable with it; a ``Fluid`` is frozen."""
    kind = type(value)
    if kind in _PLAIN or value is _MISSING or isinstance(value, Fluid):
        return value
    if kind is dict:
        return {key: _clone(item) for key, item in value.items()}
    if kind is list:
        return [_clone(item) for item in value]
    if kind is tuple:
        return tuple(_clone(item) for item in value)
    if kind is set:
        return set(value)
    if kind is np.ndarray:
        return value.copy()
    return deepcopy(value)


def _put(module, name, saved):
    """Put the attribute ``name`` of ``module`` back to ``saved``, in place for a container."""
    if saved is _MISSING:
        module.__dict__.pop(name, None)
        return
    held = module.__dict__.get(name, _MISSING)
    if type(saved) in (dict, set) and type(held) is type(saved):
        held.clear()
        held.update(_clone(saved))
    else:
        object.__setattr__(module, name, _clone(saved))


class _Module:
    """The saved state of one module."""

    def __init__(self, module):
        """Save the state of ``module``: attributes, parameters and dated parameter snapshots."""
        self.module = module
        self.attributes = {name: _clone(module.__dict__.get(name, _MISSING)) for name in STATE}
        self.parameters = [(item, _clone(item.value)) for item in module._parameters.values()]
        self.dated = [(entry, _clone(entry.params)) for entry in module._param_history]

    def restore(self):
        """Put the saved state back on the module."""
        module = self.module
        for name, value in self.attributes.items():
            _put(module, name, value)
        for parameter, value in self.parameters:
            parameter.value = _clone(value)
        module._param_history[:] = [entry for entry, _ in self.dated]
        for entry, params in self.dated:
            entry.params.clear()
            entry.params.update(_clone(params))


class Held:
    """The state of a plant as one trial has it, to put back when the trial goes on."""

    def __init__(self, plant, case):
        """Save the state of every module of ``plant``, which carries the values of ``case``."""
        self._plant = plant
        self._case = case
        self._saved = [_Module(module) for module in plant.modules()]

    def restore(self):
        """Put every saved value back on the plant."""
        for saved in self._saved:
            saved.restore()
        if self._case is not None:
            remember_case(self._plant, self._case)


class Shared:
    """The one plant of a batch of trials, with its state as the copy was made."""

    def __init__(self, plant):
        """Copy ``plant`` once and keep its state to ``reset`` to."""
        self.plant = deepcopy(plant)
        self._base = Held(self.plant, None)

    def reset(self):
        """Put the plant back as the copy was made."""
        self._base.restore()

    def capture(self, case=None):
        """Return the plant as it is now as a ``Held``, carrying ``case`` if it has the values."""
        return Held(self.plant, case)
