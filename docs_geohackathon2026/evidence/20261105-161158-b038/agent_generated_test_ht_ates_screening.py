"""Generated tests for ht_ates_screening (Model Forge)."""

import math  # noqa: F401

import pytest

from gemini_model.generated.ht_ates_screening import HtAtesScreening

CASES = [{"inputs": {"summer_surplus_gwh": 28.5, "winter_boiler_gwh": 31.5, "annual_heat_gwh": 111.67}, "parameters": {}, "expect": {"recovered_gwh": 17.5, "boiler_after_gwh": 14.0}, "tol": 1e-06}]
INVARIANTS = ["y['recovered_gwh'] <= y['stored_gwh']", "y['boiler_after_gwh'] >= 0"]


@pytest.mark.parametrize("case", CASES)
def test_ht_ates_screening(case):
    m = HtAtesScreening()
    m.update_parameters(case["parameters"])
    u = case["inputs"]
    m.calculate_output(u)
    y = m.get_output()
    for k, v in y.items():
        assert isinstance(v, (int, float, bool)) and v == v, f"output {k} is not a finite number"
    for k, exp in case["expect"].items():
        if isinstance(exp, list):
            assert (
                exp[0] - case["tol"] <= y[k] <= exp[1] + case["tol"]
            ), f"{k}={y[k]} not in {exp}"
        else:
            assert y[k] == pytest.approx(
                exp, abs=case["tol"], rel=1e-6
            ), f"{k}={y[k]} != {exp}"
    for inv in INVARIANTS:
        assert eval(inv, {"math": math, "u": u, "y": y, "m": m}), f"invariant failed: {inv}"
