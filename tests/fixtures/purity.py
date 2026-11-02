"""The purity guard: running ``forward`` or ``update`` leaves a module and its children unchanged.

``snapshot`` freezes everything in the ``__dict__`` of a module and of every child: plain values by
value, arrays by bytes, declarations (parameter values included) by their own attributes, any other
object by identity. ``unchanged`` runs a block and fails naming the module and the attribute that a
block wrote, replaced or added.
"""

import dataclasses
from collections.abc import Mapping
from contextlib import contextmanager

import numpy as np

from gemini.modules.declarations import Declaration
from gemini.modules.module import Module
from gemini.streams.fluid import BRINE

PLAIN = (int, float, complex, str, bool, bytes, type(None))
SKIPPED = ("_parent",)


def frozen(value, seen=()):
    """Return ``value`` as something that compares equal when nothing was written to it."""
    if id(value) in seen:
        return ("cycle", id(value))
    seen = (*seen, id(value))
    if isinstance(value, PLAIN):
        return value
    if isinstance(value, Module):
        return ("module", id(value))
    if isinstance(value, np.ndarray):
        return ("array", value.dtype.str, value.shape, value.tobytes())
    if isinstance(value, Mapping):
        return ("map", tuple((key, frozen(item, seen)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(frozen(item, seen) for item in value))
    if isinstance(value, (set, frozenset)):
        return ("set", frozenset(frozen(item, seen) for item in value))
    if isinstance(value, Declaration) or (
        dataclasses.is_dataclass(value) and not isinstance(value, type)
    ):
        return (type(value).__name__, id(value), frozen(vars(value), seen))
    return ("object", type(value).__name__, id(value))


def snapshot(module):
    """Return the frozen attributes of ``module`` and of every module below it, by path."""
    return {
        path: {name: frozen(value) for name, value in vars(member).items() if name not in SKIPPED}
        for path, member in module.named_modules()
    }


def changes(before, after):
    """Return ``path.attribute`` of every attribute that differs between two snapshots."""
    found = []
    for path in before.keys() | after.keys():
        old, new = before.get(path, {}), after.get(path, {})
        found += [
            f"{path or 'root'}.{name}"
            for name in old.keys() | new.keys()
            if old.get(name) != new.get(name)
        ]
    return sorted(found)


@contextmanager
def unchanged(module):
    """Fail, naming what changed, when the block writes to ``module`` or to a child."""
    before = snapshot(module)
    yield
    written = changes(before, snapshot(module))
    assert not written, f"{type(module).__name__}: a call wrote {written}"


PID_TUNING = dict(
    proportional_gain=2.0,
    integral_time=100.0,
    derivative_time=10.0,
    minimum_output=0.0,
    maximum_output=1.0,
    direction="reverse",
)
FRESH_PID = {"integral": 0.0, "previous_error": 0.0, "previous_step": 0.0}


def esp_case():
    """Return a pump set to run, and what a run of it calls."""
    from gemini.modules.pumps import ESP
    from gemini.streams.flows import Stream
    from gemini.streams.ports import Ports
    from gemini.units import Quantity
    from tests.fixtures import si
    from tests.fixtures.esp_design import ESP_PARAMS

    pump = si.set_params(ESP(), "", ESP_PARAMS)
    pump.frequency = Quantity(50, "Hz")
    suction = Stream(
        fluid=BRINE, m_dot=Quantity(30, "kg/s"), T=Quantity(300, "K"), p=Quantity(5e6, "Pa")
    )

    def run(module):
        module(fluid_in=suction)
        module.forward({"frequency": 50.0}, Ports({"fluid_in": suction}), {})

    return pump, run


def pid_case():
    """Return a controller set to run, and what a run of it calls: forward, update and a step."""
    from gemini.modules.control import PIDController
    from tests.fixtures import si

    pid = si.set_params(PIDController(), "", PID_TUNING)
    pid.setpoint, pid.measurement = 1.0, 0.8
    inputs = {"setpoint": 1.0, "measurement": 0.8}

    def run(module):
        module(state=FRESH_PID)
        module.forward(inputs, {}, FRESH_PID)
        module.update(inputs, {}, {}, FRESH_PID, 60)
        module.step(FRESH_PID, 60, {})

    return pid, run


CASES = {"ESP": esp_case, "PIDController": pid_case}
"""``{class name: function giving (module, run)}`` for every converted class, by the converter.

``run`` calls ``module`` and its ``forward`` (and ``update``) directly; the module is made ready
to run, its plan built, before it is returned, because building comes before a call.
"""
