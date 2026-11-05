"""The physics gate: six checks between the simulator and the user.

1. Valid inputs - tool arguments match the schema and allowed ranges
   (done in :mod:`gemini_agent.tools` before anything runs).
2. Hard rules - every day: flow 50-300 m3/h, brine dT <= 40 K, <= 330
   days per doublet (the geothermal source is down 35 days), production =
   injection, demand met on all 365 days. A failure here
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
HOURS = 24.0
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
    boiler_eff = (  # the day's part-load efficiency when the plant reports one
        d["boiler_efficiency_day"].where(
            d["boiler_efficiency_day"] > 0, assumptions["boiler_efficiency"]
        )
        if "boiler_efficiency_day" in d
        else assumptions["boiler_efficiency"]
    )
    balances = {
        "district heat (CHP + HEX + heat pump + boilers + heat recovery - storage charge "
        "+ discharge = delivered)": d["heat_delivered_w"]
        - (
            _col(d, "chp_heat_w")
            + d["hex_heat_w"]
            + d["heat_pump_heat_w"]
            + d["boiler_heat_w"]
            + _col(d, "electric_boiler_heat_w")
            + _col(d, "heat_recovery_heat_w")
            - _col(d, "storage_charge_w")
            + _col(d, "storage_discharge_w")
        ),
        "storage (state of charge: start + 24 h x (charge - discharge) - loss = end)": (
            _col(d, "storage_soc_start_mwh")
            + HOURS * (_col(d, "storage_charge_w") - _col(d, "storage_discharge_w")) / 1e6
            - _col(d, "storage_loss_mwh")
            - _col(d, "storage_soc_mwh")
        )
        * 1e6
        / HOURS,
        "brine heat (geothermal = HEX + absorption + HP source + ORC + separator loss)": (
            d["geothermal_heat_w"]
            - (
                d["hex_heat_w"]
                + d["absorption_heat_w"]
                + d["heat_pump_heat_w"]
                - d["heat_pump_power_w"]
                + _col(d, "orc_heat_w")
                + separator_loss
            )
        ),
        "boiler (associated gas + purchased gas x efficiency)": d["boiler_heat_w"]
        - (d["associated_gas_heat_w"] + d["purchased_gas_w"] * boiler_eff),
        "associated gas (CHP fuel + boiler fuel + flared = produced)": _col(
            d, "associated_gas_fuel_w"
        )
        - (
            _col(d, "chp_fuel_w")
            + d["associated_gas_heat_w"] / boiler_eff
            + _col(d, "associated_gas_flared_w")
        ),
        "CHP (power + heat = fuel x efficiency)": _col(d, "chp_power_el_w")
        + _col(d, "chp_heat_w")
        - _col(d, "chp_fuel_w") * assumptions.get("chp_efficiency", 0.85),
        "grid (import - export = consumption - CHP power - ORC power)": _col(d, "grid_import_w")
        - _col(d, "grid_export_w")
        - (d["electricity_w"] - _col(d, "chp_power_el_w") - _col(d, "orc_power_el_w")),
        "cooling (delivered + unmet = demand)": d["cooling_demand_w"]
        - (d["cooling_delivered_w"] + d["unmet_cooling_w"]),
        "heating (delivered + unmet = demand)": d["heating_demand_w"]
        - (d["heat_delivered_w"] + d["unmet_heat_w"]),
        "electricity (ESP + injection pump + heat pumps + chillers + ATES + e-boiler)": d[
            "electricity_w"
        ]
        - (
            d["esp_power_w"]
            + d["injection_pump_power_w"]
            + d["heat_pump_power_w"]
            + d["chiller_power_w"]
            + _col(d, "ates_power_w")
            + _col(d, "heat_recovery_power_w")
            + _col(d, "electric_boiler_power_w")
        ),
        "electric boiler (heat = power x efficiency)": _col(d, "electric_boiler_heat_w")
        - _col(d, "electric_boiler_power_w") * assumptions.get("electric_boiler_efficiency", 0.99),
        "heat-recovery heat pump (heat = cooling + power)": _col(d, "heat_recovery_heat_w")
        - _col(d, "heat_recovery_cooling_w")
        - _col(d, "heat_recovery_power_w"),
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
        el = d.dropna(subset=["electric_chiller_cop"])
        cop = el["electric_chiller_cop"]
        if "electric_chiller_sink_c" in el:  # the chiller's own heat sink that day
            t_rej = el["electric_chiller_sink_c"] + K
            carnot = (t_chill / (t_rej - t_chill)).where(t_rej > t_chill, float("inf"))
        elif "cooling_water_c" in el:  # the day's own heat-rejection temperature
            t_rej = el["cooling_water_c"] + K
            carnot = (t_chill / (t_rej - t_chill)).where(t_rej > t_chill, float("inf"))
        else:
            carnot = t_chill / (t_cw - t_chill) if t_cw > t_chill else float("inf")
        if (cop > carnot).any():
            errors.append(f"electric chiller COP above Carnot ({float(np.min(carnot)):.1f})")
        if (cop <= 0).any():
            errors.append("electric chiller COP not positive")
    if "absorption_cop" in d:
        ab = d.dropna(subset=["absorption_cop"])
        ab = ab[ab["absorption_heat_w"] > 0]
        if not ab.empty:
            t_hot = ab["wellhead_temperature_c"] + K
            if "cooling_water_c" in ab:
                t_cw = ab["cooling_water_c"] + K
            rev = (1.0 - t_cw / t_hot) * t_chill / (t_cw - t_chill)
            if (ab["absorption_cop"] > rev + 1e-9).any():
                errors.append("absorption chiller COP above the reversible limit")
    if "orc_efficiency" in d:
        orc = d.dropna(subset=["orc_efficiency"])
        orc = orc[orc["orc_power_el_w"] > 0]
        if not orc.empty:
            # Carnot between the ORC's brine inlet and the outdoor air
            t_hot = orc["orc_inlet_temperature_c"] + K
            t_air = orc["orc_air_c"] + K
            if (orc["orc_efficiency"] > 1.0 - t_air / t_hot + 1e-9).any():
                errors.append("ORC efficiency above Carnot")
            if (orc["orc_power_el_w"] > orc["orc_heat_w"] + 1e-6).any():
                errors.append("ORC power above its heat input")
    if "storage_top_c" in d:  # built-in pit store (gemini_design.pit_storage)
        top, bottom = d["storage_top_c"], d["storage_bottom_c"]
        if (top > assumptions.get("pit_store_top_max_c", 90.0) + 0.01).any():
            errors.append("pit store top above its liner temperature limit")
        if (top < bottom - 1e-6).any():
            errors.append("pit store colder at the top than at the bottom")
        if (bottom < assumptions.get("pit_store_ground_c", 10.0) - 0.01).any():
            errors.append("pit store colder than the ground around it")
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


# Words after a number that make it a quantity (a unit or a count), not a bare number.
_UNIT_AFTER = re.compile(
    r"\s*(?:%|°\s*C|degC|deg\b|(?:k|M|bn)?\s?EUR|€|million\b|billion\b|percent\b|pp\b|x\b|"
    r"kg\b|g\b|s\b|min\b|Pa\b|kPa\b|MPa\b|mm\b|cm\b|ppm\b|L\b|l/s\b|"
    r"(?:k|M|G)?W(?:h|th|e|el)?\b|MW|kt\b|t\b|tonnes?\b|"
    r"m3(?:/h)?|m\b|km\b|mD\b|bar\b|K\b|C\b|days?\b|h\b|hours?\b|years?\b|yr\b|"
    r"designs?\b|runs?\b|samples?\b|doublets?\b|pairs?\b|wells?\b|options?\b|cases?\b|"
    r"units?\b|modules?\b|steps?\b|rows?\b|of\s+\d|out\s+of\b|/)",
    re.I,
)
_RANGE_TO_NEXT = re.compile(r"\s*(?:to|-|–|and|or|vs\.?|versus|,)\s*(?:EUR|€)?\s*", re.I)
BARE_LIMIT = 12  # bare numbers up to 12 are counts and small integers
_DATE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[:h]\d{2}\b")


def _is_year(x, decimals):
    """A calendar year (1950-2100) written as a whole number."""
    return decimals == 0 and 1950 <= x <= 2100


def _numbers_with_unit_flag(text):
    """``(value, decimals, bare)`` for every number; ``bare`` = no unit or count word.

    A number before a currency sign or followed by a unit (or a count such as
    "96 designs") is not bare. In "from 35.9 to 36.2 EUR/MWh" and "20 and 26 degC"
    the first number takes the unit of the next one.
    """
    text = _RUN_ID.sub(" ", text)
    matches = list(_NUMBER.finditer(text))
    dates = [d.span() for d in _DATE.finditer(text)]
    out = []
    has_unit = []
    for m in matches:
        unit = (
            bool(_UNIT_AFTER.match(text[m.end() :]))
            or bool(_PREFIX_EUR.search(text[max(0, m.start() - 6) : m.start()]))
            or any(a <= m.start() < b for a, b in dates)
        )
        has_unit.append(unit)
    for i in range(len(matches) - 2, -1, -1):  # ranges: borrow the next number's unit
        m, nxt = matches[i], matches[i + 1]
        gap = text[m.end() : nxt.start()]
        if not has_unit[i] and has_unit[i + 1] and _RANGE_TO_NEXT.fullmatch(gap):
            has_unit[i] = True
    for m, unit in zip(matches, has_unit):
        if m.group(3):
            raw, decimals = m.group(3), len(m.group(3)) - 1
        else:
            raw = m.group(1).replace(",", "") + (m.group(2) or "")
            decimals = len(m.group(2)) - 1 if m.group(2) else 0
        out.append((float(raw), decimals, not unit))
    return out


def _flatten_numbers(obj, out, free_text=True):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            out.append(abs(float(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out, free_text)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _flatten_numbers(v, out, free_text)
    elif isinstance(obj, str):
        if free_text or not any(c.isspace() for c in obj.strip()):
            out.extend(v for v, _ in extract_numbers(obj))


def allowed_values(sources, free_text=True, scales=SCALES):
    """Return a sorted array of every number (and unit-scaled variant) in ``sources``.

    ``free_text=False`` (used for tool results) ignores numbers inside prose
    strings: a note or message in a tool result is not a computed value, and a
    number planted there (prompt injection) must not count as traceable.
    """
    base = []
    for s in sources:
        if isinstance(s, str):
            try:
                s = json.loads(s)
            except (json.JSONDecodeError, TypeError):
                pass
        _flatten_numbers(s, base, free_text)
    values = np.array(base, dtype=float)
    if values.size == 0:
        return values
    scaled = np.concatenate([values * f for f in scales])
    return np.unique(scaled)


def _matches(x, decimals, values, slack=0.01):
    if x in ALWAYS_ALLOWED and decimals == 0:
        return True
    if values.size == 0:
        return False
    tol = max(0.5 * 10.0 ** (-decimals), slack * abs(x)) + 1e-9
    i = np.searchsorted(values, x)
    for j in (i - 1, i):
        if 0 <= j < values.size and abs(values[j] - x) <= tol:
            return True
    return False


# ---------------------------------------------------------------- gate 6b: unit binding
# A number written with a unit must match a value of that same quantity, not just
# any number somewhere in the evidence (a full run summary holds hundreds).
_UNITS = [  # (regex after the number, family, factor to the family's base unit)
    (r"\s*(?:EUR|€)?\s*/\s*MWh", "eur_per_mwh", 1.0),
    (r"\s*(?:EUR|€)?\s*/\s*kWh", "eur_per_mwh", 1e3),
    (r"\s*kt\b", "t", 1e3),
    (r"\s*t(?=\s*(?:/\s*yr|/\s*year|CO2|of CO2|per year|a year))", "t", 1.0),
    (r"\s*(?:M\s?EUR|MEUR|million EUR)", "meur", 1.0),
    (r"\s*(?:k\s?EUR|kEUR)", "meur", 1e-3),
    (r"\s*GWh\b", "mwh", 1e3),
    (r"\s*MWh\b", "mwh", 1.0),
    (r"\s*m3/h\b", "m3h", 1.0),
    (r"\s*K\b", "k", 1.0),
    (r"\s*%", "pct", 1.0),
]
_PREFIX_EUR = re.compile(r"(?:EUR|€)\s*$")


def _family(path):
    """Quantity family of a field from its key path, or None."""
    key = path[-1] if path else ""
    parent = path[-2] if len(path) > 1 else ""
    if key.endswith("eur_per_mwh"):
        return "eur_per_mwh", 1.0
    if key.endswith("meur"):
        return "meur", 1.0
    if parent == "capex_eur" or key.endswith("_eur"):
        return "meur", 1e-6
    if "co2_t" in key or key.endswith("_t_per_year") or key.endswith("_t"):
        return "t", 1.0
    if key.endswith("_mwh") or parent == "energy_mwh" or key.endswith("mwh_fuel"):
        return "mwh", 1.0
    if key.endswith("m3h"):
        return "m3h", 1.0
    if key.endswith("_k"):
        return "k", 1.0
    if key.endswith("_pct"):
        return "pct", 1.0
    if "share" in key or key.endswith("_fraction"):
        return "pct", 100.0
    return None


def _family_values(obj, out, path=(), free_text=True):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        fam = _family(path)
        if fam and math.isfinite(obj):
            out.setdefault(fam[0], []).append(abs(float(obj)) * fam[1])
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _family_values(v, out, path + (str(k),), free_text)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _family_values(v, out, path, free_text)
    elif isinstance(obj, str):
        if not free_text and any(c.isspace() for c in obj.strip()):
            return  # prose in a tool result is not a computed value
        for fam, x, _ in unit_claims(obj):
            out.setdefault(fam, []).append(x)


def unit_claims(text):
    """Return ``(family, value in the family's base unit, decimals)`` for numbers with a unit."""
    text = _RUN_ID.sub(" ", text)
    out = []
    for m in _NUMBER.finditer(text):
        rest = text[m.end() :]
        for pattern, fam, factor in _UNITS:
            u = re.match(pattern, rest)
            if not u:
                continue
            if (
                fam == "eur_per_mwh"
                and not re.match(r"\s*(?:EUR|€)", rest)
                and not (_PREFIX_EUR.search(text[: m.start()]))
            ):
                continue  # "/MWh" without a currency is not a price
            if m.group(3):
                raw, decimals = m.group(3), len(m.group(3)) - 1
            else:
                raw = m.group(1).replace(",", "") + (m.group(2) or "")
                decimals = len(m.group(2)) - 1 if m.group(2) else 0
            out.append((fam, float(raw) * factor, decimals - round(math.log10(factor))))
            break
    return out


def check_units(answer, evidence, brief_sources):
    """Gate 6b: each number written with a unit must match a field of that quantity."""
    values = {}
    sources = [(s, False) for s in evidence] + [(s, True) for s in brief_sources]
    for s, free_text in sources:
        if isinstance(s, str):
            try:
                s = json.loads(s)
            except (json.JSONDecodeError, TypeError):
                pass
        _family_values(s, values, free_text=free_text)
    bad = []
    for fam, x, decimals in unit_claims(answer):
        pool = np.unique(np.array(values.get(fam, []), dtype=float))
        if not _matches(x, max(decimals, 0), pool):
            bad.append(f"{x:g} ({fam.replace('_', ' ')})")
    if not bad:
        return []
    return [
        "numbers do not match any result of the same quantity: "
        + ", ".join(bad[:8])
        + ". Check the unit and which field the number comes from."
    ]


_BASIS_STOPWORDS = {
    "eur",
    "per",
    "mwh",
    "pct",
    "days",
    "day",
    "the",
    "and",
    "geothermal",
    "heat",
    "heating",
    "cooling",
    "design",
    "doublet",
    "doublets",
    "price",
    "cost",
}
_BASIS_SAID = re.compile(
    r"different (basis|bases|assumptions?)|not on the same basis|same basis|"
    r"other (basis|assumptions?)|basis differs",
    re.I,
)


def _run_basis(entry):
    """Assumption overrides a design run was priced and simulated with."""
    req = entry.get("request") or {}
    basis = entry.get("overrides") or req.get("assumptions") or {}
    return {k: v for k, v in basis.items()}


def check_basis(answer, cited, ledger):
    """Gate 6c: compared design runs must share one basis, or the answer must say so.

    Two cited runs with different assumption overrides (a common geothermal stop,
    other prices, another outage day...) are not like for like. The answer passes if
    it names the assumption that differs or says the runs are on different bases.
    """
    bases = {}
    for run_id in cited:
        e = ledger.entries.get(run_id)
        if e and e.get("kind") == "design":
            bases[run_id] = _run_basis(e)
    if len(bases) < 2:
        return []
    keys = set().union(*bases.values())
    differ = sorted(
        k for k in keys if len({json.dumps(b.get(k), sort_keys=True) for b in bases.values()}) > 1
    )
    if not differ or _BASIS_SAID.search(answer):
        return []
    text = answer.lower()
    words = {w for k in differ for w in k.lower().split("_") if len(w) > 2} - _BASIS_STOPWORDS
    if any(re.search(rf"\b{re.escape(w)}", text) for w in words):
        return []
    groups = {}
    for run_id, b in bases.items():
        groups.setdefault(json.dumps({k: b.get(k) for k in differ}, sort_keys=True), []).append(
            run_id
        )
    shown = "; ".join(f"{', '.join(v)}: {k}" for k, v in groups.items())
    return [
        f"the cited runs are not on one basis (they differ in {', '.join(differ)}: {shown}). "
        "Compare runs with the same assumptions, or say which assumption differs."
    ]


def check_answer(answer, evidence, brief_sources, ledger=None, unit_binding=True):
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
    run_vals = allowed_values(evidence, free_text=False)
    brief_raw = allowed_values(brief_sources, scales=(1.0,))
    orphans, needs_citation, bare_numbers = [], [], []
    for x, dec, bare in _numbers_with_unit_flag(answer):
        if bare and x > BARE_LIMIT and not _is_year(x, dec):
            # a number with no unit matches one of the hundreds of values in a run
            # summary (or their unit-scaled copies) about half the time by chance
            # (run_gate6_control.py). It passes only as a brief or user value, as written.
            if not _matches(x, dec, brief_raw, slack=0.0):
                bare_numbers.append(x)
            continue
        if _matches(x, dec, brief_vals):
            continue
        if _matches(x, dec, run_vals):
            needs_citation.append(x)
            continue
        orphans.append(x)
    if bare_numbers:
        shown = ", ".join(f"{v:g}" for v in bare_numbers[:8])
        errors.append(
            f"numbers without a unit: {shown}. Write the unit or what is counted after every "
            "number above 12 (for example 36.0 EUR/MWh, 4,600 t CO2 per year, 3,100 m, "
            "96 designs), so it can be checked against the result of that quantity."
        )
    if orphans:
        shown = ", ".join(f"{v:g}" for v in orphans[:8])
        errors.append(
            f"numbers not found in any tool result or the brief: {shown}. "
            "Use only numbers from tool results, or run a tool to get them."
        )
    if ledger is not None:
        errors.extend(check_basis(answer, cited, ledger))
    if needs_citation and not cited:
        errors.append("the answer quotes simulation results but cites no run id like [R0001]")
    if unit_binding and not orphans:
        errors.extend(check_units(answer, evidence, brief_sources))
    return errors
