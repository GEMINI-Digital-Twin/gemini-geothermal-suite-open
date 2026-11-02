"""The record of a row that gave no result: its code, its path and its time."""

from gemini.errors import PhysicsError, RunError, ValidationError
from gemini.errors.rows import SKIPPED, failed_row, row_code, skipped_row


def test_an_exception_gets_the_row_code_of_its_cause():
    """A solve that fails, a value out of its bounds and anything else have their own codes."""
    assert row_code(PhysicsError("x", code="loop_not_converged")) == "no_convergence"
    assert row_code(PhysicsError("x", code="out_of_range")) == "out_of_range"
    assert row_code(ValidationError("x", code="invalid_value")) == "out_of_bounds"
    assert row_code(RunError("x", code="step")) == "module_error"
    assert row_code(ValueError("x")) == "module_error"
    assert row_code(RunError("x"), inlet=True) == "invalid_inlet"


def test_a_failed_row_names_the_module_that_raised_else_the_twin():
    """The path of the exception wins over the path of the twin."""
    named = failed_row("plant", ValidationError("bad", path="plant.pump", code="out_of_bounds"))
    assert named["path"] == "plant.pump" and named["code"] == "out_of_bounds"
    assert failed_row("plant", ValueError("bad"))["path"] == "plant"


def test_a_skipped_row_has_the_code_that_tells_it_from_a_failure():
    """The skip code is the one ``gm.evaluate.failures`` reads."""
    row = skipped_row("plant.pump", "frequency", "2024-01-01T00:00:00+00:00")
    assert row["code"] == SKIPPED == "missing_value"
    assert row["message"] == "frequency" and row["time"] == "2024-01-01T00:00:00+00:00"
