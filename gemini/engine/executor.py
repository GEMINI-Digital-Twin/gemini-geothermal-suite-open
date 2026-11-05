"""Executors: the ways the engine runs a module over the rows of a chunk.

An ``Executor`` has two steps. ``prepare(module, streams, inputs, stepped)`` takes the inlet
streams and the controls and boundaries (dotted path to column) of the selected rows and returns
what ``run`` needs; an exception of this step is the error of every selected row.
``run(prepared, rows, context)`` returns a ``ChunkResult`` (``gemini.engine.chunkresult``);
``context`` holds ``dt`` (the seconds of every row) and ``states`` (the state tree of a stepped
call). The eager executor of ``gemini.engine.eager`` is always there; a package that runs
better registers a factory under the name ``"compiled"`` with ``register_executor``, and an
engine built with ``compile=True`` uses it.

A run is a generator of ``Request`` objects: each asks an executor to run one prepared call and
receives its result. ``driven`` answers them one at a time, which is a plain run; a study answers
those of many runs at once with ``Executor.run_batch`` (see ``gemini.study._utils.batch``).
"""

from typing import NamedTuple

from gemini._utils.strings import did_you_mean, join_names
from gemini.errors import ValidationError

_FACTORIES = {}
COMPILED = "compiled"
EAGER = "eager"


class Request(NamedTuple):
    """One prepared call asked of an executor: what ``Executor.run`` takes."""

    executor: object
    prepared: object
    rows: int
    context: dict

    def run(self):
        """Return the result of the call, run alone."""
        return self.executor.run(self.prepared, self.rows, self.context)


def driven(steps):
    """Run a generator of ``Request`` objects, answering each one alone; return its value.

    An exception of a request is thrown into the generator at its ``yield``, so the ``finally``
    blocks of the run see it as they do in a plain call.
    """
    try:
        request = next(steps)
        while True:
            try:
                answer = request.run()
            except BaseException as error:
                request = steps.throw(error)
                continue
            request = steps.send(answer)
    except StopIteration as stop:
        return stop.value


class Executor:
    """Base of the executors: subclasses define ``prepare`` and ``run``."""

    def prepare(self, module, streams, inputs, stepped):
        """Return what ``run`` needs for ``module`` on the given inlets and inputs."""
        raise NotImplementedError(f"{type(self).__name__} does not prepare")

    def run(self, prepared, rows, context):
        """Return the ``ChunkResult`` of the prepared call over ``rows`` rows."""
        raise NotImplementedError(f"{type(self).__name__} does not run")

    def batchable(self, prepared):
        """Return whether ``run_batch`` can evaluate this prepared call together with others.

        A call that cannot runs alone, and a module it runs for real reads the plant as it is.
        """
        return False

    def run_batch(self, calls):
        """Return, for each ``(prepared, rows, context)`` of ``calls``, its result or its error.

        The calls are independent runs of the same module structure with other values, such as
        the trials of a study, each one ``batchable``. An executor that can run them as one array
        pass overrides this; the base runs them one after the other. A call that raises gives its
        exception, not a raise.
        """
        answers = []
        for prepared, rows, context in calls:
            try:
                answers.append(self.run(prepared, rows, context))
            except Exception as error:
                answers.append(error)
        return answers


def register_executor(name, factory):
    """Make ``factory(plant)``, which returns an ``Executor``, selectable by ``name``."""
    _FACTORIES[name] = factory
    return factory


def executor_for(plant, compile=True):
    """Return the executor for ``plant``: the compiled one when asked and registered, else eager."""
    name = COMPILED if compile and COMPILED in _FACTORIES else EAGER
    if name not in _FACTORIES:
        raise ValidationError(
            f"executors: executor = {name!r}; expected one of {join_names(_FACTORIES)}"
            f"{did_you_mean(name, _FACTORIES)}",
            code="unknown_name",
        )
    return _FACTORIES[name](plant)
