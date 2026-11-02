"""The values of a module tree: what is missing, what is stored and what is restored."""

import pytest

from gemini.errors import ValidationError
from gemini.modules.control import PIDController
from gemini.modules.pumps import ESP
from tests.fixtures import si
from tests.fixtures.errors import raises


def test_check_lists_every_missing_parameter_and_a_call_names_them_all():
    """One ``missing`` issue per unset parameter; a call raises one error listing every path."""
    pump = ESP()
    found = pump.check()
    assert {issue.kind for issue in found} == {"missing"}
    assert "stage_count" in {issue.path for issue in found}
    with raises(ValidationError, "missing_value", match="uninitialized parameters.*stage_count"):
        pump._prepare()
    assert not pump.is_initialized


def test_set_params_stores_dated_values_and_state_dict_restores_them():
    """Values set with a quantity are SI; a snapshot restores them on another module."""
    pid = si.set_params(PIDController(), "", {"proportional_gain": 2.0, "direction": "reverse"})
    pid.set_params("", {"integral_time": si.params(pid, {"integral_time": 100.0})["integral_time"]})
    assert pid.params_at("")["integral_time"] == 100.0
    other = PIDController().set_state_dict(pid.state_dict())
    assert other.state_dict()[""]["params"] == pid.state_dict()[""]["params"]
    with pytest.raises(ValidationError, match="state paths differ"):
        other.set_state_dict({"elsewhere": {}})


def test_a_control_is_set_before_the_run_and_listed_by_has_input_value():
    """Persisting a control is a pre-run value; the module reports it as set."""
    pid = PIDController()
    assert not pid._has_input_value("setpoint")
    pid._set_inputs({"setpoint": 1.0})
    assert pid._has_input_value("setpoint") and pid.setpoint == 1.0
    with raises(ValidationError, "unknown_name", match="did you mean 'setpoint'"):
        pid._set_inputs({"setpint": 1.0})
