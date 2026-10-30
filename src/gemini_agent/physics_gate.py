"""The physics gate: six checks between the simulator and the user.

1. Valid inputs - tool arguments match the schema and allowed ranges
   (done in :mod:`gemini_agent.tools` before anything runs).
2. Hard rules - every day: flow 50-300 m3/h, brine dT <= 40 K, <= 330
   days per doublet, production = injection, demand met. A failure here
   is a *design* outcome (reported, not hidden).
3. Energy balance - each day, heat, brine, boiler, cooling and
   electricity balances close to 0.1 %.
4. Second solver - the peak-heating day is rebuilt as a native GEMINI
   project and re-solved by ``gemini_simulator.Solver``; temperatures
   must agree within 0.5 K.
5. Sanity bounds - COPs below their Carnot/reversible limits,
   temperatures in physical order, pump powers consistent with their
   pressure rise and within a plausible range.
6. No orphan numbers - every number in a final answer must match a value
   from a tool result or cited run (or the brief / the user's message).

Checks 3-5 failing mark a run invalid: its numbers can not be cited and
the error goes back to the LLM, never to the user.
"""

import json
import math
import re

import numpy as np

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE

K = 273.15
BALANCE_TOL = 1e-3  # relative, of the day's largest energy flow
MAX_ESP_POWER_W = 3.0e6  # per doublet
MAX_INJECTION_PUMP_POWER_W = 2.5e6  # per doublet


def _finite(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def check_hard_rules(summary):
    """Gate 2: return the names of failed hard-rule checks."""
    return [name for name, ok in summary["checks"].items() if not ok]


def _col(d, name):
    """Column or zeros (older runs have no CHP / grid columns)."""
    return d[name] if name in d else 0.0 * d["heating_demand_w"]


def check_energy_balance(daily, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Gate 3: return a list of energy-balance errors (empty when all days close)."""
    d = daily.fillna(0.0)
    q_brine = d["n_active"] * d["flow_per_doublet_m3h"] / 3600.0
    separator_loss = (
        q_brine
        * challenge["brine_density"]
        * assumptions["brine_cp"]
        * assumptions["separator_temperature_drop_k"]
    )
    scale = np.maximum.reduce(
        [
            d["heating_demand_w"].abs().to_numpy(),
            d["cooling_demand_w"].abs().to_numpy(),
            d["geothermal_heat_w"].abs().to_numpy(),
            np.full(len(d), 1.0e3),
        ]
    )
    balances = {
        "district heat (CHP + HEX + heat pump + boiler = delivered)": d["heat_delivered_w"]
        - (_col(d, "chp_heat_w") + d["hex_heat_w"] + d["heat_pump_heat_w"] + d["boiler_heat_w"]),
        "brine heat (geothermal = HEX + absorption + HP source + separator loss)": (
            d["geothermal_heat_w"]
            - (
                d["hex_heat_w"]
                + d["absorption_heat_w"]
                + d["heat_pump_heat_w"]
                - d["heat_pump_power_w"]
                + separator_loss
            )
        ),
        "boiler (associated gas + purchased gas x efficiency)": d["boiler_heat_w"]
        - (d["associated_gas_heat_w"] + d["purchased_gas_w"] * assumptions["boiler_efficiency"]),
        "associated gas (CHP fuel + boiler fuel + flared = produced)": _col(
            d, "associated_gas_fuel_w"
        )
        - (
            _col(d, "chp_fuel_w")
            + d["associated_gas_heat_w"] / assumptions["boiler_efficiency"]
            + _col(d, "associated_gas_flared_w")
        ),
        "CHP (power + heat = fuel x efficiency)": _col(d, "chp_power_el_w")
        + _col(d, "chp_heat_w")
        - _col(d, "chp_fuel_w") * assumptions.get("chp_efficiency", 0.85),
        "grid (import - export = consumption - CHP power)": _col(d, "grid_import_w")
        - _col(d, "grid_export_w")
        - (d["electricity_w"] - _col(d, "chp_power_el_w")),
        "cooling (delivered + unmet = demand)": d["cooling_demand_w"]
        - (d["cooling_delivered_w"] + d["unmet_cooling_w"]),
        "heating (delivered + unmet = demand)": d["heating_demand_w"]
        - (d["heat_delivered_w"] + d["unmet_heat_w"]),
        "electricity (ESP + injection pump + heat pump + chillers)": d["electricity_w"]
        - (
            d["esp_power_w"]
            + d["injection_pump_power_w"]
            + d["heat_pump_power_w"]
            + d["chiller_power_w"]
        ),
    }
    errors = []
    for name, residual in balances.items():
        rel = np.abs(residual.to_numpy()) / scale
        worst = int(np.argmax(rel))
        if rel[worst] > BALANCE_TOL:
            errors.append(
                f"{name}: day {worst + 1} off by {rel[worst]:.2%} "
                f"({residual.iloc[worst] / 1e6:.3f} MW)"
            )
    return errors


def check_sanity(daily, reservoir_temperature_c, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Gate 5: return a list of physical-bounds errors."""
    errors = []
    d = daily
    active = d[d["n_active"] > 0]
    t_supply = challenge["heating_supply_c"] + K
    t_chill = challenge["cooling_supply_c"] + K
    t_cw = assumptions["cooling_water_c"] + K

    numeric = d.select_dtypes("number")
    if not np.isfinite(numeric.fillna(0.0).to_numpy()).all():
        errors.append("non-finite values in the daily results")

    if not active.empty:
        t_wh = active["wellhead_temperature_c"]
        if (t_wh > reservoir_temperature_c + 0.1).any():
            errors.append("wellhead temperature above reservoir temperature")
        if (active["injection_temperature_c"] > t_wh + 1e-6).any():
            errors.append("injection temperature above wellhead temperature (heat created)")
        if (active["injection_temperature_c"] < 0.0).any():
            errors.append("injection temperature below 0 degC")
        hydraulic = (
            active["n_active"]
            * active["flow_per_doublet_m3h"]
            / 3600.0
            * active["esp_dp_bar"].clip(lower=0.0)
            * 1e5
        )
        eff = active["esp_power_w"] / hydraulic.where(hydraulic > 0)
        if (eff.dropna() < 1.0 - 1e-9).any():
            errors.append("ESP delivers more hydraulic power than it consumes")
        if (active["esp_power_w"] / active["n_active"] > MAX_ESP_POWER_W).any():
            errors.append(f"ESP power above {MAX_ESP_POWER_W / 1e6:.1f} MW per doublet")
        if (
            active["injection_pump_power_w"] / active["n_active"] > MAX_INJECTION_PUMP_POWER_W
        ).any():
            errors.append(
                f"injection pump power above {MAX_INJECTION_PUMP_POWER_W / 1e6:.1f} MW per doublet"
            )
        if (active["drawdown_bar"] < 0).any():
            errors.append("negative drawdown at the producer")

    if "heat_pump_cop" in d:
        hp = d.dropna(subset=["heat_pump_cop"])
        hp = hp[hp["heat_pump_heat_w"] > 0]
        if not hp.empty:
            # sink at most 100 degC, source at most the wellhead temperature
            t_source = hp["wellhead_temperature_c"] + K
            lift = t_supply - t_source
            carnot = (t_supply / lift).where(lift > 0, float("inf"))
            if (hp["heat_pump_cop"] > carnot).any():
                errors.append("heat pump COP above Carnot")
            if (hp["heat_pump_cop"] < 1.0).any():
                errors.append("heat pump COP below 1")
    if "electric_chiller_cop" in d:
        cop = d["electric_chiller_cop"].dropna()
        carnot = t_chill / (t_cw - t_chill) if t_cw > t_chill else float("inf")
        if (cop > carnot).any():
            errors.append(f"electric chiller COP above Carnot ({carnot:.1f})")
        if (cop <= 0).any():
            errors.append("electric chiller COP not positive")
    if "absorption_cop" in d:
        ab = d.dropna(subset=["absorption_cop"])
        ab = ab[ab["absorption_heat_w"] > 0]
        if not ab.empty:
            t_hot = ab["wellhead_temperature_c"] + K
            rev = (1.0 - t_cw / t_hot) * t_chill / (t_cw - t_chill)
            if (ab["absorption_cop"] > rev + 1e-9).any():
                errors.append("absorption chiller COP above the reversible limit")
    if (d["supply_temperature_c"] > challenge["heating_supply_c"] + 0.05).any():
        errors.append("heating supply above 100 degC")
    for col in ("electricity_w", "purchased_gas_w", "boiler_heat_w", "heat_pump_heat_w"):
        if (d[col] < -1e-6).any():
            errors.append(f"negative {col}")
    return errors


def check_run(summary, daily, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Run gates 2, 3 and 5 on a year run; return a gate report dict.

    ``passed`` is the integrity verdict (3 and 5). Hard-rule failures
    (gate 2) are reported but do not make a run invalid.
    """
    balance = check_energy_balance(daily, challenge, assumptions)
    sanity = check_sanity(daily, summary["reservoir"]["temperature_c"], challenge, assumptions)
    hard = check_hard_rules(summary)
    return {
        "passed": not balance and not sanity,
        "1_inputs": "pass",
        "2_hard_rules": "pass" if not hard else "design fails: " + ", ".join(hard),
        "3_energy_balance": "pass" if not balance else balance,
        "5_sanity": "pass" if not sanity else sanity,
    }


# ---------------------------------------------------------------- gate 6

_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?![\w])|(?<![\w.])(\.\d+)")
_RUN_ID = re.compile(r"\bR\d{4}\b")
ALWAYS_ALLOWED = set(range(0, 13)) | {2026, 2027, 100.0}
SCALES = (1.0, 1e-3, 1e-6, 1e-9, 1e3, 1e6, 100.0, 24.0, 1e-3 * 24.0)


def extract_numbers(text):
    """Return ``(value, decimals)`` for every stand-alone number in ``text``.

    Run ids (R0003), chemical formulas (CO2) and unit exponents (m3) are
    skipped because the number is glued to a letter.
    """
    text = _RUN_ID.sub(" ", text)
    out = []
    for m in _NUMBER.finditer(text):
        if m.group(3):
            raw, decimals = m.group(3), len(m.group(3)) - 1
        else:
            raw = m.group(1).replace(",", "") + (m.group(2) or "")
            decimals = len(m.group(2)) - 1 if m.group(2) else 0
        out.append((float(raw), decimals))
    return out


def _flatten_numbers(obj, out):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            out.append(abs(float(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _flatten_numbers(v, out)
    elif isinstance(obj, str):
        out.extend(v for v, _ in extract_numbers(obj))


def allowed_values(sources):
    """Return a sorted array of every number (and unit-scaled variant) in ``sources``."""
    base = []
    for s in sources:
        if isinstance(s, str):
            try:
                s = json.loads(s)
            except (json.JSONDecodeError, TypeError):
                pass
        _flatten_numbers(s, base)
    values = np.array(base, dtype=float)
    if values.size == 0:
        return values
    scaled = np.concatenate([values * f for f in SCALES])
    return np.unique(scaled)


def _matches(x, decimals, values):
    if x in ALWAYS_ALLOWED and decimals == 0:
        return True
    if values.size == 0:
        return False
    tol = max(0.5 * 10.0 ** (-decimals), 0.01 * abs(x)) + 1e-9
    i = np.searchsorted(values, x)
    for j in (i - 1, i):
        if 0 <= j < values.size and abs(values[j] - x) <= tol:
            return True
    return False


def check_answer(answer, evidence, brief_sources, ledger=None):
    """Gate 6: every number in ``answer`` must be traceable.

    ``evidence`` holds tool results and cited-run summaries; ``brief_sources``
    holds the brief, assumptions and the user's own messages. Returns a list
    of errors (empty = pass).
    """
    errors = []
    cited = sorted(set(_RUN_ID.findall(answer)))
    if ledger is not None:
        for run_id in cited:
            if run_id not in ledger.entries:
                errors.append(f"cites unknown run {run_id}")
            elif not ledger.get(run_id)["valid"]:
                errors.append(f"cites run {run_id}, which failed the physics gate")
    brief_vals = allowed_values(brief_sources)
    run_vals = allowed_values(evidence)
    orphans, needs_citation = [], []
    for x, dec in extract_numbers(answer):
        if _matches(x, dec, brief_vals):
            continue
        if _matches(x, dec, run_vals):
            needs_citation.append(x)
            continue
        orphans.append(x)
    if orphans:
        shown = ", ".join(f"{v:g}" for v in orphans[:8])
        errors.append(
            f"numbers not found in any tool result or the brief: {shown}. "
            "Use only numbers from tool results, or run a tool to get them."
        )
    if needs_citation and not cited:
        errors.append("the answer quotes simulation results but cites no run id like [R0001]")
    return errors
