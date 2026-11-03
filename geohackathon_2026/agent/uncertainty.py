"""Subsurface, demand and grid uncertainty for a chosen design.

Samples the inputs that the challenge fixes but a real project would not know
exactly, runs the 365-day model for each sample, and reports P10, P50 and P90
results, how often the design still meets the geothermal-first rule, and how
often it stays cheaper than an alternative design under the same conditions.

Ranges are assumptions, chosen around the challenge values:
- geothermal gradient 27-33 C/km (challenge 30): +-10%, typical of a regional gradient map
- permeability 100-300 mD (challenge 200): a factor 1.5 either way, as from well tests
- demand 90-110% of the supplied profiles: building stock and weather year
- grid CO2 factor 0.15-0.45 kg/kWh (GEMINI example 0.3): grid mix over the project life
"""

import numpy as np
from costs import design_costs
from yearly_energy import EnergyDesign, run_design

SAMPLES = 40
SEED = 2027
RANGES = {
    "gradient_c_per_km": (27.0, 33.0),
    "permeability_md": (100.0, 300.0),
    "demand_factor": (0.9, 1.1),
    "grid_co2_kg_per_kwh": (0.15, 0.45),
}


def latin_hypercube(samples, seed=SEED):
    """Return one dict of inputs per sample, spread evenly over every range."""
    rng = np.random.default_rng(seed)
    columns = {}
    for name, (low, high) in RANGES.items():
        strata = (rng.permutation(samples) + rng.random(samples)) / samples
        columns[name] = low + strata * (high - low)
    return [{name: float(values[i]) for name, values in columns.items()} for i in range(samples)]


def run_sample(doublets, depth_m, layout, sample, demand):
    """Run and cost one design under one sample of the uncertain inputs."""
    dates, heating, cooling, first, second = demand
    top_up, cooling_option = layout.split("+")
    design = EnergyDesign(
        doublets,
        depth_m,
        heating_top_up=top_up,
        cooling=cooling_option,
        gradient_c_per_m=sample["gradient_c_per_km"] / 1000.0,
        permeability_md=sample["permeability_md"],
        grid_co2_kg_per_kwh=sample["grid_co2_kg_per_kwh"],
    )
    factor = sample["demand_factor"]
    _, year = run_design(design, dates, heating * factor, cooling * factor, first, second)
    cost = design_costs(doublets, depth_m, year)
    return {
        "levelised_cost_eur_per_mwh": cost["levelised_cost_eur_per_mwh"],
        "co2_kt": year["co2_kt"],
        "bought_energy_share_pct": cost["bought_energy_share_pct"],
        "meets_geothermal_first": cost["meets_geothermal_first"],
        "backup_peak_mw": year["backup_peak_mw"],
        "checks_passed": all(year["checks"].values()),
    }


def percentiles(values):
    """Return P10, P50 and P90, rounded."""
    return {f"p{p}": round(float(np.percentile(values, p)), 2) for p in (10, 50, 90)}


def rank_correlation(x, y):
    """Return the Spearman rank correlation of two sequences."""
    rank = lambda values: np.argsort(np.argsort(values))  # noqa: E731
    return float(np.corrcoef(rank(np.asarray(x)), rank(np.asarray(y)))[0, 1])


def assess(design, alternative, demand, samples=SAMPLES):
    """Return the uncertainty summary for a design and, optionally, an alternative.

    ``design`` and ``alternative`` are (doublets, depth_m, layout) tuples.
    """
    inputs = latin_hypercube(samples)
    runs = [run_sample(*design, sample, demand) for sample in inputs]
    lcoe = [run["levelised_cost_eur_per_mwh"] for run in runs]
    summary = {
        "samples": samples,
        "input_ranges": {name: list(bounds) for name, bounds in RANGES.items()},
        "levelised_cost_eur_per_mwh": percentiles(lcoe),
        "co2_kt": percentiles([run["co2_kt"] for run in runs]),
        "bought_energy_share_pct": percentiles([run["bought_energy_share_pct"] for run in runs]),
        "backup_peak_mw": percentiles([run["backup_peak_mw"] for run in runs]),
        "meets_geothermal_first_pct": round(100.0 * np.mean([run["meets_geothermal_first"] for run in runs]), 1),
        "all_checks_pass_pct": round(100.0 * np.mean([run["checks_passed"] for run in runs]), 1),
        "cost_driver_rank_correlation": {
            name: round(rank_correlation([sample[name] for sample in inputs], lcoe), 2) for name in RANGES
        },
    }
    if alternative:
        other = [run_sample(*alternative, sample, demand) for sample in inputs]
        cheaper = [
            mine["levelised_cost_eur_per_mwh"] <= theirs["levelised_cost_eur_per_mwh"]
            for mine, theirs in zip(runs, other)
        ]
        cleaner = [mine["co2_kt"] <= theirs["co2_kt"] for mine, theirs in zip(runs, other)]
        summary["versus_alternative"] = {
            "alternative": {"doublets": alternative[0], "depth_m": alternative[1], "layout": alternative[2]},
            "design_cheaper_pct": round(100.0 * np.mean(cheaper), 1),
            "design_lower_co2_pct": round(100.0 * np.mean(cleaner), 1),
        }
    return summary
