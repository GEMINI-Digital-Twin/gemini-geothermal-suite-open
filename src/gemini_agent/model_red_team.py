"""Red-team the checks on agent-written models: plant known bugs, count what is caught.

``write_model`` registers a model only if two test sets pass: the tests the
agent wrote itself and the harness acceptance tests
(:mod:`gemini_agent.acceptance`). This module measures what each set adds.
It takes the two reference models an agent writes in the demo scenarios (a
dry cooler and a seasonal heat store, with the agent's own tests), plants
one bug at a time, and records which test set rejects the mutant. The
unmutated models measure false alarms.

Each fault has an ``expected`` verdict for the harness: ``catch`` (it breaks
a law or a limit the harness checks) or ``blind`` (the model is wrong but
still physical, for example a dry cooler that is half as effective as it
should be: that is a calibration error, which needs vendor data, not
physics, to catch). Blind faults are reported, not hidden.

No LLM and no simulator run is involved, so the study takes about a second.
"""

import sys
import types

from gemini_agent.acceptance import find_model_class, run_acceptance
from gemini_agent.scenarios import (
    DRY_COOLER_CODE,
    DRY_COOLER_TESTS,
    THERMAL_STORAGE_CODE,
    THERMAL_STORAGE_TESTS,
)

MODELS = {
    "dry_cooler": ("dry_cooler", DRY_COOLER_CODE, DRY_COOLER_TESTS),
    "thermal_storage": ("thermal_storage", THERMAL_STORAGE_CODE, THERMAL_STORAGE_TESTS),
}

# name: (model type, description, old text, new text, expected harness verdict)
MODEL_FAULTS = {
    # ---------------------------------------------------------------- dry cooler
    "dc_heat_overstated": (
        "dry_cooler",
        "reports 15 % more heat rejected than the water gives up (energy created)",
        '"heat_rejected": q,',
        '"heat_rejected": 1.15 * q,',
        "catch",
    ),
    "dc_cp_in_kj": (
        "dry_cooler",
        "water heat capacity in kJ/kg/K instead of J/kg/K (unit slip)",
        '"water_cp": 4186.0',
        '"water_cp": 4.186',
        "catch",
    ),
    "dc_flow_per_hour": (
        "dry_cooler",
        "treats the flow as m3/h while the contract says m3/s (unit slip)",
        'c_water = p["water_density"] * p["water_cp"] * u["water_flow_rate"]',
        'c_water = p["water_density"] * p["water_cp"] * u["water_flow_rate"] / 3600.0',
        "catch",
    ),
    "dc_effectiveness_above_1": (
        "dry_cooler",
        "effectiveness scaled by 1.3, so at low flow the water leaves colder than the air",
        'eff = 1.0 - math.exp(-p["ua"] / c_water)',
        'eff = 1.3 * (1.0 - math.exp(-p["ua"] / c_water))',
        "catch",
    ),
    "dc_wrong_ntu_formula": (
        "dry_cooler",
        "effectiveness exp(-C/UA): plausible numbers, but heat falls as the flow rises",
        'eff = 1.0 - math.exp(-p["ua"] / c_water)',
        'eff = math.exp(-c_water / p["ua"])',
        "catch",
    ),
    "dc_zero_flow_crash": (
        "dry_cooler",
        "no guard for zero flow (division by zero when the pumps stop)",
        'if c_water <= 0 or u["water_temperature_in"] <= u["air_temperature"]:',
        'if u["water_temperature_in"] <= u["air_temperature"]:',
        "catch",
    ),
    "dc_fan_power_high": (
        "dry_cooler",
        "fan power 25 % of the heat rejected (typical is 1-3 %)",
        '"fan_power_fraction": 0.02,',
        '"fan_power_fraction": 0.25,',
        "catch",
    ),
    "dc_effectiveness_percent": (
        "dry_cooler",
        "effectiveness reported in percent",
        '"effectiveness": eff,',
        '"effectiveness": 100.0 * eff,',
        "catch",
    ),
    "dc_returns_dict": (
        "dry_cooler",
        "returns the outputs instead of storing them in self.output (GEMINI convention)",
        "self.output = {",
        "return {",
        "catch",
    ),
    "dc_outlet_sign": (
        "dry_cooler",
        "outlet temperature rises instead of falling (sign error)",
        't_out = u["water_temperature_in"] - (q / c_water',
        't_out = u["water_temperature_in"] + (q / c_water',
        "catch",
    ),
    "dc_heat_from_hot_air": (
        "dry_cooler",
        "uses |T_water - T_air|, so it 'rejects' heat to air hotter than the water",
        'if c_water <= 0 or u["water_temperature_in"] <= u["air_temperature"]:',
        'if c_water <= 0 or u["water_temperature_in"] == u["air_temperature"]:',
        "catch",
    ),
    "dc_fouling_drift": (
        "dry_cooler",
        "UA shrinks by 1 % on every call (hidden state: same input, different output)",
        "        p = self.parameters\n        c_water",
        '        p = self.parameters\n        p["ua"] = 0.99 * p["ua"]\n        c_water',
        "catch",
    ),
    "dc_half_effective": (
        "dry_cooler",
        "half the effectiveness it should have (still physical: a calibration error)",
        'eff = 1.0 - math.exp(-p["ua"] / c_water)',
        'eff = 0.5 * (1.0 - math.exp(-p["ua"] / c_water))',
        "blind",
    ),
    # ---------------------------------------------------------------- heat store
    "ts_charge_above_rating": (
        "thermal_storage",
        "charging is not limited by the power rating",
        'charge = min(max(u["charge_request_mw"], 0.0), power, (cap - soc) / HOURS_PER_DAY)',
        'charge = min(max(u["charge_request_mw"], 0.0), (cap - soc) / HOURS_PER_DAY)',
        "catch",
    ),
    "ts_overfills": (
        "thermal_storage",
        "charging ignores the free room, so the store overfills",
        'charge = min(max(u["charge_request_mw"], 0.0), power, (cap - soc) / HOURS_PER_DAY)',
        'charge = min(max(u["charge_request_mw"], 0.0), power)',
        "catch",
    ),
    "ts_goes_negative": (
        "thermal_storage",
        "discharging ignores the energy left, so the store goes below empty",
        'discharge = min(max(u["discharge_request_mw"], 0.0), power, soc / HOURS_PER_DAY)',
        'discharge = min(max(u["discharge_request_mw"], 0.0), power)',
        "catch",
    ),
    "ts_loss_sign": (
        "thermal_storage",
        "standing loss added to the store instead of removed",
        "        soc -= loss\n",
        "        soc += loss\n",
        "catch",
    ),
    "ts_free_discharge": (
        "thermal_storage",
        "only 90 % of the discharged heat leaves the store (energy created on discharge)",
        "soc += HOURS_PER_DAY * (charge - discharge)",
        "soc += HOURS_PER_DAY * (charge - 0.9 * discharge)",
        "catch",
    ),
    "ts_charge_bonus": (
        "thermal_storage",
        "5 % more energy stored than charged",
        "soc += HOURS_PER_DAY * (charge - discharge)",
        "soc += HOURS_PER_DAY * (1.05 * charge - discharge)",
        "catch",
    ),
    "ts_loss_not_reported": (
        "thermal_storage",
        "standing loss taken from the store but reported as zero",
        '"loss_mwh": loss,',
        '"loss_mwh": 0.0,',
        "catch",
    ),
    "ts_power_hardcoded": (
        "thermal_storage",
        "power rating fixed at 10 MW, ignoring the power_mw parameter",
        'cap, power = p["capacity_mwh"], p["power_mw"]',
        'cap, power = p["capacity_mwh"], 10.0',
        "catch",
    ),
    "ts_hours_wrong": (
        "thermal_storage",
        "one call treated as one hour, not one day (time unit slip)",
        "HOURS_PER_DAY = 24.0\n\n\nclass",
        "HOURS_PER_DAY = 1.0\n\n\nclass",
        "catch",
    ),
}


def _load(module_name, code):
    """Import model code as ``module_name`` so the agent's tests can import it."""
    module = types.ModuleType(module_name)
    module.__file__ = f"<{module_name}>"
    exec(compile(code, module.__file__, "exec"), module.__dict__)  # noqa: S102 (our own code)
    return module


def agent_tests_fail(module_name, code, test_code):
    """Run the agent's own tests on ``code``; return the first failure or None."""
    saved = sys.modules.get(module_name)
    try:
        sys.modules[module_name] = _load(module_name, code)
        scope = {"__name__": f"test_{module_name}"}
        exec(compile(test_code, f"<test_{module_name}>", "exec"), scope)  # noqa: S102
        for name, fn in scope.items():
            if name.startswith("test_") and callable(fn):
                try:
                    fn()
                except Exception as exc:
                    return f"{name}: {type(exc).__name__}"
        return None
    except Exception as exc:
        return f"import: {type(exc).__name__}: {exc}"
    finally:
        if saved is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = saved


def harness_fails(module_name, code, register_as):
    """Run the harness acceptance tests on ``code``; return the problems."""
    try:
        module = _load(module_name, code)
    except Exception as exc:
        return [f"import: {type(exc).__name__}: {exc}"]
    cls, err = find_model_class(module)
    if err:
        return [err]
    problems, _ = run_acceptance(cls, register_as)
    return problems


def mutate(kind, old, new):
    """Return the reference code for ``kind`` with ``old`` replaced once by ``new``."""
    _, code, _ = MODELS[kind]
    if code.count(old) != 1:
        raise ValueError(f"fault text must occur exactly once in the {kind} model: {old!r}")
    return code.replace(old, new)


def run_model_trials():
    """One row per fault plus one clean row per model."""
    rows = []
    for kind, (module_name, code, tests) in MODELS.items():
        rows.append(_trial(f"{kind}_clean", kind, "reference model, no bug", code, "pass"))
    for name, (kind, desc, old, new, expected) in MODEL_FAULTS.items():
        rows.append(_trial(name, kind, desc, mutate(kind, old, new), expected))
    return rows


def _trial(name, kind, desc, code, expected):
    module_name, _, tests = MODELS[kind]
    agent = agent_tests_fail(module_name, code, tests)
    harness = harness_fails(module_name, code, kind)
    return {
        "fault": name,
        "model": kind,
        "description": desc,
        "expected": expected,
        "agent_tests_reject": agent is not None,
        "harness_rejects": bool(harness),
        "either_rejects": agent is not None or bool(harness),
        "agent_test_failure": agent or "",
        "harness_problem": harness[0] if harness else "",
    }


def score_models(rows):
    """Catch counts for the agent's tests alone, the harness alone, and both."""
    faults = [r for r in rows if r["expected"] != "pass"]
    designed = [r for r in faults if r["expected"] == "catch"]
    clean = [r for r in rows if r["expected"] == "pass"]
    return {
        "faults": len(faults),
        "designed": len(designed),
        "agent_tests_caught": sum(r["agent_tests_reject"] for r in faults),
        "harness_caught": sum(r["harness_rejects"] for r in faults),
        "both_caught": sum(r["either_rejects"] for r in faults),
        "harness_caught_designed": sum(r["harness_rejects"] for r in designed),
        "clean": len(clean),
        "false_alarms": sum(r["either_rejects"] for r in clean),
    }
