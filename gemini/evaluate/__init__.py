"""What a finished run gave and whether it is acceptable.

Grouped by job: ``costs`` (capex, opex, annualised cost, levelised costs, NPV, payback),
``emissions`` (CO2), ``balances`` (energy, mass and plant balance, and the audits of one call),
``verdict`` (bounds, requirements, failures, the verdict) and ``summary`` and ``report`` (totals,
capacities, the report and its comparison). Every function is ``gm.evaluate.<name>``.
"""

from .balances import (
    call_emissions,
    call_energy_balance,
    call_mass_balance,
    collect_flows,
    energy_balance,
    mass_balance,
    plant_balance,
)
from .costs import annualised_cost, capex, lcoc, lcoh, lcts, npv, opex, payback
from .emissions import co2
from .report import compare, report
from .summary import capacities, totals
from .verdict import bounds, failures, requirements, run_all, verdict

__all__ = [
    "totals",
    "capacities",
    "report",
    "compare",
    "failures",
    "energy_balance",
    "mass_balance",
    "plant_balance",
    "call_energy_balance",
    "call_mass_balance",
    "collect_flows",
    "call_emissions",
    "bounds",
    "run_all",
    "requirements",
    "verdict",
    "capex",
    "opex",
    "lcoh",
    "lcoc",
    "lcts",
    "annualised_cost",
    "co2",
    "npv",
    "payback",
]
