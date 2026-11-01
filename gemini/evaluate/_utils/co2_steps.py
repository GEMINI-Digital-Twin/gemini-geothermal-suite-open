"""The CO2 a run emitted, step by step."""

import numpy as np

from gemini.evaluate._utils.level import level
from gemini.evaluate._utils.series import leaf_total, results_total, steps
from gemini.modules.grids import ElectricityGrid


def released_steps(results, field):
    """Return the time integral of leaf column ``field`` in each tick; without it, zeros."""
    total = results_total(results, results.to_frame(), field)
    if total is None:
        return np.zeros(len(results.durations))
    return steps(total, results.durations)


def grid_steps(plant, results):
    """Return the energy [J] of grid electricity drawn in each tick."""
    total = leaf_total(plant, results.to_frame(), "net_import", ElectricityGrid)
    if total is None:
        return np.zeros(len(results.durations))
    return steps(total, results.durations)


def emissions_steps(plant, case, results):
    """Return ``(direct, methane, equivalent, electricity)``, the emissions of each tick [kg].

    The CO2 released, the methane released, that methane as CO2-equivalent (times
    ``economics.accounting.gwp.CH4``) and the CO2 of the grid electricity (times
    ``utilities.electricity.co2_intensity``).
    A factor is needed only when the run releases methane or draws grid electricity; then its
    absence raises ``missing_assumption``.
    """
    direct = released_steps(results, "co2_emission")
    methane = released_steps(results, "methane_emission")
    grid = grid_steps(plant, results)
    count = len(direct)
    equivalent = np.zeros(count)
    electricity = np.zeros(count)
    if methane.any():
        equivalent = methane * level(case, "economics.accounting.gwp.CH4", count)
    if grid.any():
        electricity = grid * level(case, "utilities.electricity.co2_intensity", count)
    return direct, methane, equivalent, electricity


def emitted_steps(plant, case, results):
    """Return the CO2-equivalent [kg] emitted in each tick of the run."""
    direct, _, equivalent, electricity = emissions_steps(plant, case, results)
    return direct + equivalent + electricity
