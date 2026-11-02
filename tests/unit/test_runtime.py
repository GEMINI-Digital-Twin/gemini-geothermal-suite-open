"""Context-local runtime settings."""

from concurrent.futures import ThreadPoolExecutor

import pytest

import gemini as gm
from gemini.errors import ValidationError
from tests.fixtures.engine_plants import pair_frame, pair_plant
from tests.fixtures.errors import raises


def test_settings_restore_and_context_isolation():
    """Temporary settings restore and separate copied thread contexts."""
    assert gm.runtime.get_precision() == "float64"
    with gm.runtime.settings(precision="float32", display_units="field"):
        assert gm.runtime.get_precision() == "float32"
        assert gm.runtime.get_display_units() == "field"
    assert gm.runtime.get_precision() == "float64"
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: gm.runtime.get_precision(), range(2)))
    assert values == ["float64", "float64"]


def test_state_round_trip():
    """Serializable runtime state restores all settings through ``settings``."""
    before = gm.runtime.state()
    with gm.runtime.settings(display_units="field"):
        with gm.runtime.settings(**before):
            assert gm.runtime.state() == before
    assert gm.runtime.state() == before


def test_unknown_settings_are_rejected():
    """A misspelled setting raises with a suggestion instead of doing nothing."""
    with raises(ValidationError, "unknown_name", match="did you mean 'precision'"):
        with gm.runtime.settings(precison="float32"):
            pass
    with raises(ValidationError, "unknown_name", match="float16"):
        with gm.runtime.settings(precision="float16"):
            pass
    assert gm.runtime.get_precision() == "float64"


def test_settings_decorator():
    """A decorated function sees the setting on every call."""

    @gm.runtime.settings(display_units="field")
    def current():
        return gm.runtime.get_display_units()

    assert current() == "field"
    assert gm.runtime.get_display_units() == "si"


def test_there_is_no_default_fluid():
    """The fluid is no setting: the name is refused and the state holds none."""
    with pytest.raises(ValidationError, match="default_fluid"):
        gm.runtime.settings(default_fluid=gm.WATER)
    assert "default_fluid" not in gm.runtime.state()


def test_processes_is_a_whole_number_of_at_least_one():
    """One serial process is the setting of a run; anything else that is not a count is refused."""
    assert gm.runtime.get_processes() == 1
    with gm.runtime.settings(processes=3):
        assert gm.runtime.get_processes() == 3 and gm.runtime.state()["processes"] == 3
    assert gm.runtime.get_processes() == 1
    for bad in (0, -1, 2.5, True, "2"):
        with raises(ValidationError, "invalid_value", match="processes"):
            with gm.runtime.settings(processes=bad):
                pass


def test_the_compiled_and_the_eager_run_agree():
    """P4: ``compile`` is a runtime setting, so both runs give the same numbers within 1e-9.

    ``processes`` is kept true by ``test_a_sample_in_workers_equals_the_serial_sample`` of
    ``tests/unit/study/_utils/test_parallel.py``, which compares a real sample in workers with the
    serial one.
    """
    data = gm.Dataset.from_frame(pair_frame())
    frames = [
        gm.Engine(pair_plant(), compile=flag).replay(data).to_frame().select_dtypes("number")
        for flag in (True, False)
    ]
    assert list(frames[0].columns) == list(frames[1].columns)
    assert frames[0].to_numpy() == pytest.approx(
        frames[1].to_numpy(), rel=1e-9, abs=1e-9, nan_ok=True
    )
