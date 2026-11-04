"""Compare the recommended design with a conventional system: gas boilers and electric chillers.

The conventional system has no geothermal wells. Gas boilers supply all heating at 100 C
and electric chillers all cooling at 20 C, priced with the same assumptions as costs.py.

Run from the project folder:
    PYTHONPATH=../src:cases:agent python cases/reference_case.py
"""

from costs import (
    BACKUP_BOILER_EUR_PER_KW,
    DEFAULT_PRICES,
    ELECTRIC_CHILLER_EUR_PER_KW,
    capital_recovery_factor,
)
from tools import call_tool
from yearly_energy import ELECTRIC_CHILLER_COP, ELECTRICITY_CO2_KG_PER_KWH
from yearly_heating import (
    BACKUP_BOILER_EFFICIENCY,
    BACKUP_EMISSION_KG_PER_GJ,
    COOLING_FILE,
    HEATING_FILE,
    read_demand,
)

MAINTENANCE_SHARE = 0.02  # assumed: boilers and chillers cost 2% of their price a year to maintain
GJ_PER_MWH = 3.6


def conventional():
    """Return yearly energy, CO2 and cost of gas boilers plus electric chillers."""
    _, heating = read_demand(HEATING_FILE)
    _, cooling = read_demand(COOLING_FILE)
    heat_mwh = heating.sum() * 24
    cool_mwh = cooling.sum() * 24
    gas_mwh = heat_mwh / BACKUP_BOILER_EFFICIENCY
    electricity_mwh = cool_mwh / ELECTRIC_CHILLER_COP
    co2_t = gas_mwh * GJ_PER_MWH * BACKUP_EMISSION_KG_PER_GJ / 1000 + electricity_mwh * ELECTRICITY_CO2_KG_PER_KWH
    capital = BACKUP_BOILER_EUR_PER_KW * heating.max() * 1000 + ELECTRIC_CHILLER_EUR_PER_KW * cooling.max() * 1000
    annual = (
        capital * capital_recovery_factor(DEFAULT_PRICES["discount_rate"])
        + capital * MAINTENANCE_SHARE
        + gas_mwh * DEFAULT_PRICES["gas_eur_per_mwh"]
        + electricity_mwh * DEFAULT_PRICES["electricity_eur_per_mwh"]
        + co2_t * DEFAULT_PRICES["co2_eur_per_tonne"]
    )
    return {
        "co2_kt": co2_t / 1000,
        "levelised_cost_eur_per_mwh": annual / (heat_mwh + cool_mwh),
        "gas_gwh": gas_mwh / 1000,
        "electricity_gwh": electricity_mwh / 1000,
    }


def main():
    """Print the conventional system next to the recommended design."""
    reference = conventional()
    design = {"doublets": 2, "depth_m": 3000, "layout": "chp+absorption"}
    year = call_tool("simulate_year", design)
    cost = call_tool("estimate_cost", design)
    saved = 1 - year["co2_kt"] / reference["co2_kt"]
    print("System                          CO2 kt/yr   Cost EUR/MWh   Grid GWh/yr")
    print(f"Conventional (gas + electric)   {reference['co2_kt']:9.2f}   {reference['levelised_cost_eur_per_mwh']:12.1f}   {reference['electricity_gwh']:11.2f}")
    print(f"Recommended geothermal design   {year['co2_kt']:9.2f}   {cost['levelised_cost_eur_per_mwh']:12.1f}   {year['electricity_gwh']:11.2f}")
    print(f"CO2 saved: {saved:.0%} ({reference['co2_kt'] - year['co2_kt']:.1f} kt a year)")


if __name__ == "__main__":
    main()
