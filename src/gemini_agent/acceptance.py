"""Acceptance tests the harness owns, run on every model the agent writes.

``write_model`` asks the agent for a model *and* its tests. Tests written
by the same LLM that wrote the model can share the model's mistakes (a
wrong sign in both, a missing case in both), so a passing agent test only
shows the model does what its author believed. These checks are written
by us, not by the LLM, and the agent can not see or change them:

1. Interface (every model): a ``gemini_model`` ``Model`` subclass that
   builds with no arguments, stores its results in ``self.output`` (read
   with ``get_output()``), returns only finite numbers, gives the same
   answer twice and does not change its input dict.
2. Physics (model slots with a contract, see :data:`CONTRACTS`): the model
   is probed over a grid of inputs, including edge cases its author may not
   have thought of (zero flow, air hotter than the water, a full store),
   and must conserve energy, respect the second law and its own limits,
   and respond in the physically right direction.

A model for a type without a contract only gets the interface checks; the
tool result says so, and no design run uses such a model.

Run in a separate process by :func:`gemini_agent.sandbox.write_model`::

    python -m gemini_agent.acceptance <model_file.py> <register_as>

which prints a JSON list of problems (empty = accepted).
"""

import importlib.util
import json
import math
import sys

from gemini_model.model_abstract import Model

WATER_RHO = 1000.0  # kg/m3, the contract's water properties
WATER_CP = 4186.0  # J/kg/K
PROPERTY_TOL = 0.02  # a model may use its own water properties within 2 %
MAX_FAN_FRACTION = 0.10  # fan power above 10 % of the heat rejected is implausible (1-3 % typical)
MAX_PROBLEMS = 12

CONTRACTS = {
    "dry_cooler": {
        "summary": "water-to-air dry cooler on the chiller condenser circuit",
        "parameters": "free; give every parameter a default in __init__ (for example ua in W/K)",
        "inputs": {
            "water_temperature_in": "degC",
            "water_flow_rate": "m3/s",
            "air_temperature": "degC",
        },
        "outputs": {
            "heat_rejected": "W, >= 0, zero when the air is not colder than the water",
            "water_temperature_out": "degC",
            "fan_power": "W",
            "effectiveness": "0-1",
        },
    },
    "thermal_storage": {
        "summary": "seasonal hot-water heat store, one 24 h day per call",
        "parameters": {
            "capacity_mwh": "MWh",
            "power_mw": "MW",
            "loss_fraction_per_day": "1/day",
        },
        "inputs": {
            "soc_mwh": "MWh, state of charge at the start of the day",
            "charge_request_mw": "MW",
            "discharge_request_mw": "MW",
        },
        "outputs": {
            "soc_mwh": "MWh at the end of the day",
            "charge_mw": "MW",
            "discharge_mw": "MW",
            "loss_mwh": "MWh",
        },
    },
}

CONTRACT_RULES = {
    "dry_cooler": [
        "energy balance: heat_rejected = 1000 * 4186 * flow * (T_in - T_out), within 2 %",
        "no heat when the flow is zero or the air is not colder than the water",
        "air temperature <= T_out <= T_in (second law)",
        "effectiveness 0-1, fan power 0-10 % of the heat rejected",
        "heat rejected rises with inlet temperature and flow, falls with air temperature",
    ],
    "thermal_storage": [
        "state of charge balances: soc_in + 24 * (charge - discharge) - loss = soc_out",
        "0 <= soc <= capacity; charge, discharge, loss >= 0",
        "charge and discharge never above the request or the power rating",
        "rated power delivered when there is energy and room (power_mw is honoured)",
    ],
}


def describe_contracts():
    """Contracts and the checks behind them, for list_models and the tool text."""
    return {key: {**spec, "harness_checks": CONTRACT_RULES[key]} for key, spec in CONTRACTS.items()}


# ---------------------------------------------------------------- helpers


def _finite_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _call(model, u):
    """Run one step; return (output dict, problem or None)."""
    before = dict(u)
    try:
        returned = model.calculate_output(u)
    except Exception as exc:  # a crash on a valid input is a problem, not a harness error
        return None, f"calculate_output({_short(u)}) raised {type(exc).__name__}: {exc}"
    if u != before:
        return None, "calculate_output changed its input dict"
    out = model.get_output()
    if not out:
        hint = " (it returned a dict instead)" if isinstance(returned, dict) and returned else ""
        return None, (
            "calculate_output must store its results in self.output; get_output() was empty" + hint
        )
    return out, None


def _short(u):
    return ", ".join(f"{k}={v:g}" for k, v in u.items())


def _outputs(out, keys, u):
    """Check the required keys are present and finite; return floats or a problem."""
    missing = [k for k in keys if k not in out]
    if missing:
        return None, f"output is missing {', '.join(missing)} (got {', '.join(sorted(out))})"
    bad = [k for k in keys if not _finite_number(out[k])]
    if bad:
        return None, f"non-finite or non-numeric {', '.join(bad)} at {_short(u)}"
    return {k: float(out[k]) for k in keys}, None


# ---------------------------------------------------------------- interface (all models)


def find_model_class(module):
    """Return the single Model subclass defined in ``module`` (or a problem string)."""
    classes = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Model) and obj.__module__ == module.__name__
    ]
    if len(classes) != 1:
        return None, f"expected one gemini_model Model subclass, found {len(classes)}"
    return classes[0], None


def check_interface(cls):
    """Return (model instance, problems) for the checks every model gets."""
    try:
        model = cls()
    except Exception as exc:
        return None, [f"{cls.__name__}() raised {type(exc).__name__}: {exc}"]
    problems = []
    if not callable(getattr(model, "calculate_output", None)):
        problems.append("no calculate_output(u, x=None) method")
    if not isinstance(getattr(model, "parameters", None), dict):
        problems.append("self.parameters must be a dict (call super().__init__())")
    return model, problems


# ---------------------------------------------------------------- dry cooler


DC_T_IN = (25.0, 32.0, 40.0, 55.0)
DC_FLOW = (0.0, 0.02, 0.3, 1.5)
DC_AIR = (-10.0, 5.0, 20.0, 30.0, 38.0, 60.0)
DC_KEYS = ("heat_rejected", "water_temperature_out", "fan_power", "effectiveness")


def check_dry_cooler(model):
    """Physics checks for a dry cooler over a grid of inlet, flow and air temperatures."""
    problems = []
    q = {}
    for t_in in DC_T_IN:
        for flow in DC_FLOW:
            for air in DC_AIR:
                u = {"water_temperature_in": t_in, "water_flow_rate": flow, "air_temperature": air}
                out, err = _call(model, u)
                if err:
                    return [err]
                o, err = _outputs(out, DC_KEYS, u)
                if err:
                    return [err]
                again, _ = _call(model, dict(u))
                if again is not None and any(again.get(k) != out[k] for k in DC_KEYS):
                    problems.append("not deterministic: the same input gave another output")
                heat, t_out = o["heat_rejected"], o["water_temperature_out"]
                q[(t_in, flow, air)] = heat
                at = f" at {_short(u)}"
                if heat < -1.0:
                    problems.append("negative heat_rejected" + at)
                if flow == 0.0 or air >= t_in:
                    if abs(heat) > 1.0:
                        problems.append(
                            "rejects heat with zero flow" + at
                            if flow == 0.0
                            else "rejects heat to air that is not colder than the water" + at
                        )
                    if flow > 0.0 and abs(t_out - t_in) > 0.01:
                        problems.append("outlet temperature changes with no heat rejected" + at)
                    continue
                c = WATER_RHO * WATER_CP * flow
                expected = c * (t_in - t_out)
                if abs(heat - expected) > PROPERTY_TOL * max(abs(heat), abs(expected)) + 1.0:
                    problems.append(
                        f"energy balance off: heat_rejected {heat:.4g} W but the water gives "
                        f"up {expected:.4g} W" + at
                    )
                if not air - 0.01 <= t_out <= t_in + 0.01:
                    problems.append(
                        f"outlet {t_out:.2f} degC outside air {air:g} .. inlet {t_in:g} degC "
                        "(second law)" + at
                    )
                if not -1e-9 <= o["effectiveness"] <= 1.0 + 1e-9:
                    problems.append(f"effectiveness {o['effectiveness']:.3g} outside 0-1" + at)
                if o["fan_power"] < -1e-9:
                    problems.append("negative fan_power" + at)
                elif o["fan_power"] > MAX_FAN_FRACTION * heat + 1.0:
                    problems.append(
                        f"fan power {o['fan_power']:.3g} W is over 10 % of the heat rejected" + at
                    )
    if problems:
        return problems
    if q[(40.0, 0.3, 20.0)] <= 1.0:
        problems.append("no heat rejected at 40 degC water, 20 degC air, 0.3 m3/s")
    tol = 1e-6
    for flow in DC_FLOW:
        for air in DC_AIR:
            row = [q[(t, flow, air)] for t in DC_T_IN]
            if any(b < a * (1 - tol) - 1.0 for a, b in zip(row, row[1:])):
                problems.append("heat rejected falls as the inlet temperature rises")
                break
    for t_in in DC_T_IN:
        for air in DC_AIR:
            row = [q[(t_in, f, air)] for f in DC_FLOW]
            if any(b < a * (1 - tol) - 1.0 for a, b in zip(row, row[1:])):
                problems.append("heat rejected falls as the water flow rises")
                break
        for flow in DC_FLOW:
            row = [q[(t_in, flow, a)] for a in DC_AIR]
            if any(b > a * (1 + tol) + 1.0 for a, b in zip(row, row[1:])):
                problems.append("heat rejected rises as the air gets warmer")
                break
    return problems


# ---------------------------------------------------------------- thermal storage


TS_CASES = (
    {"capacity_mwh": 10000.0, "power_mw": 10.0, "loss_fraction_per_day": 0.001},
    {"capacity_mwh": 500.0, "power_mw": 40.0, "loss_fraction_per_day": 0.01},
    {"capacity_mwh": 20000.0, "power_mw": 25.0, "loss_fraction_per_day": 0.002},
)


def check_thermal_storage(model):
    """Storage balance, limits and rating, for three sizes (one fills up in a day)."""
    from gemini_design.storage import check_model

    problems = []
    for params in TS_CASES:
        model.update_parameters(dict(params))
        try:
            found = check_model(model) or _check_rating(model, params)
        except Exception as exc:
            found = [f"{type(exc).__name__}: {exc}"]
        problems += [f"{p} (capacity {params['capacity_mwh']:g} MWh)" for p in found]
    return problems


def _check_rating(model, params):
    """Check the store delivers its rated power when it has the energy and the room."""
    cap, power = params["capacity_mwh"], params["power_mw"]
    if 24.0 * power > 0.4 * cap:  # energy-limited size: the rating is not reachable
        return []
    problems = []
    for soc, charge, discharge, key in (
        (0.5 * cap, power, 0.0, "charge_mw"),
        (0.5 * cap, 0.0, power, "discharge_mw"),
    ):
        u = {"soc_mwh": soc, "charge_request_mw": charge, "discharge_request_mw": discharge}
        model.calculate_output(u)
        got = float(model.get_output()[key])
        if abs(got - power) > 1e-6 * power:
            problems.append(
                f"{key} {got:.4g} MW at half charge for a {power:g} MW request "
                f"(power_mw parameter not honoured)"
            )
        u = {k: 2.0 * v if k != "soc_mwh" else v for k, v in u.items()}
        model.calculate_output(u)
        got = float(model.get_output()[key])
        if got > power * (1 + 1e-9):
            problems.append(f"{key} {got:.4g} MW above the {power:g} MW rating")
    return problems


CHECKS = {"dry_cooler": check_dry_cooler, "thermal_storage": check_thermal_storage}


# ---------------------------------------------------------------- entry points


def run_acceptance(cls, register_as):
    """All harness checks for a model class. Returns (problems, level)."""
    model, problems = check_interface(cls)
    check = CHECKS.get(register_as)
    if model is None or problems:
        return problems, "interface"
    if check is None:
        return [], "interface only (no contract for this type)"
    problems = sorted(set(check(model)), key=lambda p: (p.split(" at ")[0], p))
    if len(problems) > MAX_PROBLEMS:
        problems = problems[:MAX_PROBLEMS] + [f"... and {len(problems) - MAX_PROBLEMS} more"]
    return problems, f"interface + {register_as} physics"


def check_file(path, register_as):
    """Import a model file and run the harness checks on it."""
    try:
        spec = importlib.util.spec_from_file_location("agent_model_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return [f"import failed: {type(exc).__name__}: {exc}"], "import"
    cls, err = find_model_class(module)
    if err:
        return [err], "interface"
    return run_acceptance(cls, register_as)


def main(argv=None):
    """CLI used by the sandbox: print {"problems": [...], "level": ...} as JSON."""
    path, register_as = (argv or sys.argv[1:])[:2]
    problems, level = check_file(path, register_as)
    print(json.dumps({"problems": problems, "level": level}))


if __name__ == "__main__":
    main()
