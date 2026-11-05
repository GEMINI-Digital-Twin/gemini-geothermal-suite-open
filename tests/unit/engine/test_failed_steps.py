"""A step that fails physically is a row of the result; a programming error still raises."""

import pandas as pd
import pytest

import gemini as gm
from gemini.engine.lockstep import Lane, lockstep
from gemini.engine.simulate import simulation_steps
from gemini.errors import DefinitionError, PhysicsError
from gemini.errors.rows import PHYSICAL_ROW_CODES
from gemini.study._utils.shared import Shared
from gemini.study._utils.trial import run_trials
from gemini.units import Quantity
from tests.fixtures.engine_tank import ROW, TIME, Tank, tank
from tests.unit.engine.schedule.test_schedule import FULL, case_of, demand, plant_of_two

COLD = 0.015
"""A gradient of 15 K/km in K/m: the brine cannot reach the temperature the demand asks for."""
COOL = 0.02
"""20 K/km: the brine reaches it at the lower demand of the second day only."""


def _cold(gradient):
    """Return the two-doublet plant and a three-day case at ``gradient`` [K/m]."""
    case = case_of(demand(FULL, 0.5 * FULL, FULL)).with_value("site.ground.gradient", gradient)
    return plant_of_two(), case


def test_a_cold_reservoir_finishes_with_failed_rows_and_an_infeasible_verdict():
    """The run ends; each failing step is a row with its reason and invalid (NaN) outputs."""
    plant, case = _cold(COLD)
    results = gm.simulate(plant, case)
    errors = results.errors()
    assert len(errors) == 3 and {row["code"] for row in errors} <= PHYSICAL_ROW_CODES
    assert all(row["path"] == "hx" and row["message"] and row["time"] for row in errors)
    verdict = gm.evaluate.verdict(plant, case, results)
    assert not verdict["feasible"]
    reason = next(item for item in verdict["reasons"] if item["kind"] == "failed_step")
    assert reason["message"].startswith("3 steps failed; most frequent: hx out_of_range (3 rows)")


def test_a_run_with_one_failed_step_keeps_the_others():
    """At 20 K/km the second step still works: a failed row is NaN, the others are results."""
    plant, case = _cold(COOL)
    results = gm.simulate(plant, case)
    failed = pd.DatetimeIndex([row["time"] for row in results.errors()])
    frame = results.to_frame()
    assert 0 < len(failed) < len(frame)
    assert frame.loc[failed].isna().all().all()
    assert frame.drop(failed).notna().any().any()


def test_a_normal_case_has_no_failed_rows():
    """The same plant at 30 K/km runs every step."""
    plant, case = _cold(0.03)
    assert gm.simulate(plant, case).errors() == []


def test_the_study_reads_the_failed_run_as_infeasible():
    """A trial of a study on a cold reservoir is infeasible with a reason, not an exception."""
    plant, case = _cold(0.03)
    values = {"case.site.ground.gradient": COLD}
    [(metrics, reason, violation)] = run_trials(Shared(plant), case, None, [values], ["lcts"], True)
    assert reason["kind"] == "failed_step" and violation > 0


def _broken(error):
    """Return a tank whose ``forward`` raises ``error``."""

    class Broken(Tank):
        """A tank that fails the way a wrongly written module does."""

        def forward(self, inputs, inlets, state):
            """Raise the chosen error."""
            raise error

    module = Broken()
    module.set_params("", {"pressure": Quantity(2e5, "Pa"), "temperature": Quantity(320.0, "K")})
    module.bindings = tank().bindings
    return module


def _frame(rows=3):
    return pd.DataFrame(
        {name: [value] * rows for name, value in ROW.items()},
        index=pd.date_range(TIME, periods=rows, freq="15min"),
    )


@pytest.mark.parametrize("code", sorted(PHYSICAL_ROW_CODES - {"invalid_inlet", "out_of_bounds"}))
def test_a_physical_error_of_a_module_is_a_failed_row(code):
    """A simulation goes on after a step whose module cannot find a solution."""
    error = PhysicsError("no solution", code="no_convergence" if code == "no_convergence" else code)
    results = gm.simulate(_broken(error), plan=gm.Dataset.from_frame(_frame()))
    assert [row["code"] for row in results.errors()] == [code] * 3


@pytest.mark.parametrize("error", [KeyError("nope"), DefinitionError("wrong")])
def test_a_programming_error_still_raises(error):
    """A wrong key or a wrong definition ends a simulation."""
    with pytest.raises(type(error)):
        gm.simulate(_broken(error), plan=gm.Dataset.from_frame(_frame()))
    assert (
        gm.simulate(
            _broken(error), plan=gm.Dataset.from_frame(_frame()), on_error="record"
        ).errors()[0]["code"]
        == "module_error"
    )


def test_the_physical_codes_are_row_codes():
    """Every physical failure is a code of ``ROW_CODES``."""
    assert PHYSICAL_ROW_CODES <= set(gm.errors.ROW_CODES)
    assert "module_error" not in PHYSICAL_ROW_CODES


def test_trials_run_together_with_one_failing_give_the_rows_each_gives_alone():
    """A cold trial next to normal ones, in one array pass: the same failed rows as run alone."""
    gradients = [0.03, COLD, COOL]
    trials = [_cold(gradient) for gradient in gradients]
    lanes = [Lane(simulation_steps(plant, case)) for plant, case in trials]
    together = lockstep(lanes)
    for (plant, case), found in zip(trials, together):
        alone = gm.simulate(plant, case)
        assert found.errors() == alone.errors()
        pd.testing.assert_frame_equal(found.to_frame(), alone.to_frame())
    assert [len(found.errors()) for found in together] == [0, 3, 1]
