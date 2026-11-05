"""Price sensitivity and unplanned peak-day outage for the main candidate designs.

Writes results/sensitivity.md and prints the same tables.

Run from the project folder:
    PYTHONPATH=../src:cases:agent python agent/sensitivity_study.py
"""

from pathlib import Path

from costs import DEFAULT_PRICES, design_costs
from tools import simulate_year, unplanned_outages
from yearly_energy import (
    ASSUMED_COOLING_COP,
    COOLING_FILE,
    HEATING_FILE,
    EnergyDesign,
    lowest_demand_windows,
    read_demand,
    run_design,
)

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "results" / "sensitivity.md"

DESIGNS = [
    (1, 3000.0, "chp+absorption"),
    (2, 3000.0, "chp+absorption"),
    (2, 3000.0, "chp+electric"),
    (2, 3000.0, "boiler+electric"),
    (3, 3000.0, "chp+absorption"),
    (2, 2500.0, "heat_pump+electric"),
]
CASES = [
    ("Base", {}),
    ("Gas 60 EUR/MWh", {"gas_eur_per_mwh": 60.0}),
    ("Gas 100 EUR/MWh", {"gas_eur_per_mwh": 100.0}),
    ("CO2 150 EUR/t", {"co2_eur_per_tonne": 150.0}),
    ("CO2 250 EUR/t", {"co2_eur_per_tonne": 250.0}),
    ("Gas 80 and CO2 150", {"gas_eur_per_mwh": 80.0, "co2_eur_per_tonne": 150.0}),
    ("Wells x1.5 (about 7-9 MEUR each)", {"well_cost_multiplier": 1.5}),
    ("Discount rate 5%", {"discount_rate": 0.05}),
    ("Discount rate 9%", {"discount_rate": 0.09}),
    ("Absorption chiller 800 EUR/kW", {"absorption_chiller_eur_per_kw": 800.0}),
    ("Electricity 150 EUR/MWh", {"electricity_eur_per_mwh": 150.0}),
    ("Electricity 300 EUR/MWh", {"electricity_eur_per_mwh": 300.0}),
    ("Heat pump 1,000 EUR/kW", {"heat_pump_eur_per_kw": 1000.0}),
    ("Absorption chiller 250 EUR/kW", {"absorption_chiller_eur_per_kw": 250.0}),
    ("CHP 1,500 EUR/kWe", {"chp_eur_per_kw_el": 1500.0}),
    ("Sold electricity 40 EUR/MWh", {"export_eur_per_mwh": 40.0}),
]
UNPLANNED_START = "2027-01-25"
UNPLANNED_DAYS = 7


def lcoe(design, year, prices):
    """Return the levelised cost for one design and price set."""
    return design_costs(design[0], design[1], year, prices)["levelised_cost_eur_per_mwh"]


def label(design):
    """Return a short design label."""
    return f"{design[0]} x {design[1]:.0f} m {design[2]}"


def price_table(years):
    """Return markdown lines for the price sensitivity table."""
    eligible = [d for d in DESIGNS if design_costs(d[0], d[1], years[d])["meets_geothermal_first"]]
    header = "| Case | " + " | ".join(label(d) for d in DESIGNS) + " | Chosen by rule | Cheapest overall |"
    lines = [header, "|" + "---|" * (len(DESIGNS) + 3)]
    for name, prices in CASES:
        costs = {d: lcoe(d, years[d], prices) for d in DESIGNS}
        chosen = min(eligible, key=costs.get)
        cheapest = min(DESIGNS, key=costs.get)
        cells = " | ".join(f"{costs[d]:.1f}" for d in DESIGNS)
        lines.append(f"| {name} | {cells} | {label(chosen)} | {label(cheapest)} |")
    return lines


def break_even_co2(years, low, high, gas_price):
    """Return the CO2 price (EUR/t) at which two designs cost the same, or None."""
    def gap(co2):
        prices = {"gas_eur_per_mwh": gas_price, "co2_eur_per_tonne": co2}
        return lcoe(high, years[high], prices) - lcoe(low, years[low], prices)

    first, second = gap(0.0), gap(1000.0)
    if first == second:
        return None
    return first * 1000.0 / (first - second)


def outage_table(years):
    """Return markdown lines comparing planned and unplanned outage cases."""
    dates, heating = read_demand(HEATING_FILE)
    _, cooling = read_demand(COOLING_FILE)
    first, second = lowest_demand_windows(heating + cooling / ASSUMED_COOLING_COP)
    lines = [
        "| Design | Case | Peak backup MW | Bought gas heat GWh | Peak electric cooling MW | CO2 kt | LCOE EUR/MWh | Checks |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for design in DESIGNS:
        planned = years[design]
        rows, summary = run_design(
            EnergyDesign(design[0], design[1], heating_top_up=design[2].split("+")[0], cooling=design[2].split("+")[1]),
            dates, heating, cooling, first, second,
            outages=unplanned_outages(design[0], dates.index(UNPLANNED_START), UNPLANNED_DAYS, first, second),
        )
        unplanned = summary
        for name, year in (("Planned only", planned), ("Unplanned 25-31 Jan", unplanned)):
            failed = year.get("checks_failed")
            if failed is None:
                failed = [key for key, passed in year["checks"].items() if not passed]
            lines.append(
                f"| {label(design)} | {name} | {year['backup_peak_mw']:.1f} | "
                f"{year['backup_gwh']:.1f} | {year['electric_cooling_peak_mw']:.1f} | "
                f"{year['co2_kt']:.2f} | {lcoe(design, year, {}):.1f} | "
                f"{'pass' if not failed else ', '.join(failed)} |"
            )
    return lines


def main():
    """Run both studies and write the markdown report."""
    years = {design: simulate_year(design[0], design[1], layout=design[2]) for design in DESIGNS}
    lines = [
        "# Sensitivity and unplanned outage",
        "",
        "Generated by `agent/sensitivity_study.py`. Levelised cost of energy in EUR/MWh of heat and "
        "cooling delivered. Base prices: " + ", ".join(f"{k}={v}" for k, v in DEFAULT_PRICES.items()) + ".",
        "",
        "## Price sensitivity",
        "",
        *price_table(years),
        "",
        "## CO2 price at which 2 x 3000 m costs the same as 1 x 3000 m (both chp+absorption)",
        "",
    ]
    for gas in (40.0, 80.0, 120.0):
        value = break_even_co2(years, DESIGNS[0], DESIGNS[1], gas)
        lines.append(f"- Gas {gas:.0f} EUR/MWh: {'none' if value is None else f'{value:.0f} EUR/t'}")
    lines += [
        "",
        "## Unplanned outage over the peak",
        "",
        f"Doublet 1 fails for {UNPLANNED_DAYS} days from {UNPLANNED_START}, covering the 28 January "
        "peak; its other planned days are shortened so the total stays 35. Backup capacity is "
        "re-sized to the new peak and costed.",
        "",
        *outage_table(years),
    ]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
