"""Two design rules, written once here and shared by the design plan, its checker, the optimiser and the economics.
Doublets: no heat unmet, capacity covers the peak, boiler energy at most 5 % of the heat served (rule_failures, meets_rule).
Associated gas: reinject it when that raises the cost of heat by less than GAS_LCOH_PENALTY_MAX, else burn it in the gas
engine (gas_choice)."""

BOILER_SHARE_MAX = 0.05   # boiler energy allowed as a share of the heat served, covers the outage days; assumed, no source
UNMET_MIN_GWH = 0.01      # unmet heat below this counts as zero, GWh; rounding, our choice


def rule_failures(row):
    """(reason, number, unit) per failure of a year row with unmet_GWh, peak_margin_pct, boiler_GWh, served_GWh."""
    f = []
    if row["unmet_GWh"] >= UNMET_MIN_GWH:
        f.append(("unmet heat", row["unmet_GWh"], "GWh"))
    if row.get("peak_margin_pct", 0.0) < 0.0:
        f.append(("peak margin", row["peak_margin_pct"], "%"))
    if row["boiler_GWh"] > BOILER_SHARE_MAX * row.get("served_GWh", 0):
        f.append(("boiler share", row.get("boiler_share_pct"), "%"))
    return f


def meets_rule(row):
    """True when the row has no failure."""
    return not rule_failures(row)


# largest rise of the cost of heat, as a share of the engine's, for which the gas is reinjected;
# our choice: a CO2 cut of about 40 % for under 1 % cost
GAS_LCOH_PENALTY_MAX = 0.01


def gas_penalty(engine, reinject):
    """(EUR/MWh, %) that reinjection adds to the cost of heat over the gas engine, from two economics dicts."""
    d = reinject["lcoh_EUR_MWh"] - engine["lcoh_EUR_MWh"]
    return d, 100 * d / engine["lcoh_EUR_MWh"]


def gas_choice(engine, reinject):
    """('reinject' or 'engine', one-sentence reason) from the economics dicts of the design with each gas option."""
    d, pct = gas_penalty(engine, reinject)
    co2 = f"CO2 {engine['co2_total_kt']:.2f} -> {reinject['co2_total_kt']:.2f} kt for {d:+.2f} EUR/MWh ({pct:+.1f} %)"
    if pct < 100 * GAS_LCOH_PENALTY_MAX:
        return "reinject", f"reinject the associated gas: {co2}, below the 1 % rule, permit assumed [C, A]"
    return "engine", f"keep the gas engine: reinjection would cut {co2}, above the 1 % rule [C, A]"
