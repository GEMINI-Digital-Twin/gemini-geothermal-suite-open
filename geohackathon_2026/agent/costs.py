"""Cost of a design: capital, yearly cost and levelised cost of energy.

The challenge gives no prices. Sourced values come from the ThermoGIS economic
model (https://www.thermogis.nl/en/economic-model); every other value is an
assumption and is labelled as one in the result.
"""

# Sourced: ThermoGIS economic model
WELL_COST_FACTOR = 1.96
SURFACE_FIXED_EUR = 3.5e6  # per doublet
SURFACE_EUR_PER_KW = 882.0
OPEX_EUR_PER_KW_YEAR = 81.0
OPEX_EUR_PER_MWH = 0.62  # 0.062 euro cent per kWh
ELECTRICITY_EUR_PER_MWH = 230.0
LIFETIME_YEARS = 15  # SDE++ horizon used by ThermoGIS

# Assumptions, no source found
DISCOUNT_RATE = 0.07
ABSORPTION_CHILLER_EUR_PER_KW = 400.0  # including cooling tower
ELECTRIC_CHILLER_EUR_PER_KW = 200.0
BACKUP_BOILER_EUR_PER_KW = 100.0
GAS_EUR_PER_MWH = 40.0  # bought natural gas for the backup boiler
CO2_EUR_PER_TONNE = 80.0
GAS_TREATMENT_EUR_PER_DOUBLET = 0.5e6  # separator, gas handling, produced-gas boiler

DESIGN_POWER_PER_DOUBLET_KW = 13_020.0  # 300 m3/h and 37 C usable cooling, see STATE.md
BACKUP_BOILER_EFFICIENCY = 0.9

DEFAULT_PRICES = {
    "well_cost_multiplier": 1.0,  # 1.0 is the ThermoGIS formula
    "discount_rate": DISCOUNT_RATE,
    "gas_eur_per_mwh": GAS_EUR_PER_MWH,
    "co2_eur_per_tonne": CO2_EUR_PER_TONNE,
    "electricity_eur_per_mwh": ELECTRICITY_EUR_PER_MWH,
    "absorption_chiller_eur_per_kw": ABSORPTION_CHILLER_EUR_PER_KW,
}

# Selection rule: geothermal must carry the load before cost decides
MAX_BOUGHT_ENERGY_SHARE = 0.10  # bought-gas heat plus electric cooling, share of energy delivered


def well_cost_eur(depth_m):
    """Return the ThermoGIS cost of one well (EUR) at a depth in m."""
    return WELL_COST_FACTOR * (790_000 + 555 * depth_m + 0.05 * depth_m**2)


def capital_recovery_factor(rate=DISCOUNT_RATE, years=LIFETIME_YEARS):
    """Return the capital recovery factor for annualising investment."""
    growth = (1 + rate) ** years
    return rate * growth / (growth - 1)


def design_costs(doublets, depth_m, year, prices=None):
    """Return capital, yearly and levelised costs for a simulated design.

    ``year`` is the summary returned by the simulate_year tool. ``prices``
    overrides any of DEFAULT_PRICES, for sensitivity studies.
    """
    prices = {**DEFAULT_PRICES, **(prices or {})}
    recovery = capital_recovery_factor(prices["discount_rate"])
    wells = 2 * doublets * well_cost_eur(depth_m) * prices["well_cost_multiplier"]
    surface = doublets * (
        SURFACE_FIXED_EUR + SURFACE_EUR_PER_KW * DESIGN_POWER_PER_DOUBLET_KW
        + GAS_TREATMENT_EUR_PER_DOUBLET
    )
    chillers = (
        prices["absorption_chiller_eur_per_kw"] * year["absorption_peak_mw"] * 1000
        + ELECTRIC_CHILLER_EUR_PER_KW * year["electric_cooling_peak_mw"] * 1000
    )
    backup = BACKUP_BOILER_EUR_PER_KW * year["backup_peak_mw"] * 1000
    capital = wells + surface + chillers + backup

    geothermal_mwh = (year["geothermal_heat_gwh"] + year["drive_gwh"]) * 1000
    fixed_opex = OPEX_EUR_PER_KW_YEAR * DESIGN_POWER_PER_DOUBLET_KW * doublets
    variable_opex = OPEX_EUR_PER_MWH * geothermal_mwh
    electricity = prices["electricity_eur_per_mwh"] * year["electricity_gwh"] * 1000
    gas = prices["gas_eur_per_mwh"] * year["backup_gwh"] * 1000 / BACKUP_BOILER_EFFICIENCY
    carbon = prices["co2_eur_per_tonne"] * year["co2_kt"] * 1000
    annual = capital * recovery + fixed_opex + variable_opex + electricity + gas + carbon

    delivered_mwh = (
        year["geothermal_heat_gwh"] + year["gas_gwh"] + year["backup_gwh"]
        + year["absorption_gwh"] + year["electric_cooling_gwh"]
    ) * 1000
    bought_share = (year["backup_gwh"] + year["electric_cooling_gwh"]) * 1000 / delivered_mwh
    return {
        "bought_energy_share_pct": round(bought_share * 100, 1),
        "meets_geothermal_first": bought_share <= MAX_BOUGHT_ENERGY_SHARE,
        "capital_meur": round(capital / 1e6, 1),
        "wells_meur": round(wells / 1e6, 1),
        "annual_cost_meur": round(annual / 1e6, 2),
        "energy_delivered_gwh": round(delivered_mwh / 1000, 1),
        "levelised_cost_eur_per_mwh": round(annual / delivered_mwh, 1),
        "annual_parts_meur": {
            "capital": round(capital * recovery / 1e6, 2),
            "maintenance": round((fixed_opex + variable_opex) / 1e6, 2),
            "electricity": round(electricity / 1e6, 2),
            "bought_gas": round(gas / 1e6, 2),
            "co2": round(carbon / 1e6, 2),
        },
        "basis": (
            "Wells, surface, maintenance and electricity price from ThermoGIS; 15 years. "
            "Assumed: 7% discount rate, chiller and boiler prices, gas 40 EUR/MWh, CO2 80 EUR/t, "
            "gas treatment 0.5 MEUR per doublet. Well cost ignores pipe diameter."
        ),
    }
