"""The record of a row of a run that gave no result: one shape, one code, built in one place.

A row is a tick of a run, for one module. It fails when the module raises, a bound leaves its
limits or an inlet breaks the stream limits, and it is skipped when a bound column has no value.
Either way the run goes on and the row is a problem (``gm.errors`` shape ``{path, code, message,
suggestions}``) with the ``time`` of the tick and a code of ``gm.errors.ROW_CODES``. The engine
builds these records from the exceptions of an executor (eager or compiled, the exception is the
same), ``Results.errors`` lists them and ``gm.evaluate.failures`` groups them: ``SKIPPED`` tells
the two kinds apart.
"""

from gemini.errors.base import GeminiError, ValidationError, problem

SKIPPED = "missing_value"
"""The code of a row skipped for a missing value; every other code is a row that failed."""


def row_code(error, inlet=False):
    """Return the code in ``gm.errors.ROW_CODES`` of the exception that failed a row.

    ``inlet`` tells that the row failed on the limits of an inlet stream.
    """
    if inlet:
        return "invalid_inlet"
    code = error.code if isinstance(error, GeminiError) else None
    if code == "loop_not_converged":
        return "no_convergence"
    if code in ("no_convergence", "out_of_range"):
        return code
    if isinstance(error, ValidationError) and code in ("out_of_bounds", "invalid_value"):
        return "out_of_bounds"
    return "module_error"


def failed_row(path, error, inlet=False):
    """Return the record of the row that the exception ``error`` of a twin failed.

    The path is the one the error names, the module that raised, else the path of the twin.
    """
    where = getattr(error, "path", None) if isinstance(error, GeminiError) else None
    return problem(where or path, row_code(error, inlet), error)


def skipped_row(path, reason, time):
    """Return the record of the row of ``time`` that ``path`` skipped for the missing ``reason``."""
    return problem(path, SKIPPED, reason, time=time)
