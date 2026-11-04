"""The rule for enough doublets: no heat unmet, capacity covers the peak, boiler energy at most 5 % of the heat served.
Written once here and shared by the design plan, its checker and the optimiser. Returns the failures of one year row."""

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
