"""Feed Fimbul's production-temperature decline back into the annual runner.

The annual runner treats the reservoir as steady (constant production
temperature, Darcy PI for both wells). Here the year-1 dispatch gives each design's annual-average
flow per doublet; the Fimbul lookup turns that into a production
temperature per year; and the runner is re-run at chosen years with the
reservoir temperature lowered accordingly (and, by default, the
simulated producer PI and injector injectivity in place of Darcy's), so KPIs and costs can be
reported over the plant's life rather than for year 1 only.
"""

import numpy as np

from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_design.fimbul.lookup import simulate_doublet


def lifetime_performance(
    design,
    demand,
    well_spacing_m=1200.0,
    permeability_md=None,
    years=30,
    evaluate_years=(1, 15, 30),
    correct_hydraulics=True,
    challenge=CHALLENGE,
    assumptions=ASSUMPTIONS,
):
    """Return the year-by-year reservoir response and runner KPIs at selected years.

    Returns a dict with ``reservoir`` (the :func:`simulate_doublet` result for
    the design's mean flow per doublet) and ``by_year`` (for each year in
    ``evaluate_years``: production temperature drop, the simulated PI and
    injectivity ratios (applied when ``correct_hydraulics``), LCOE, geothermal share,
    purchased gas, CO2 and whether every hard constraint is still met).
    """
    daily, steady = run_year(design, demand, challenge, assumptions)
    active = daily["n_active"] * daily["flow_per_doublet_m3h"]
    mean_flow = float(active.sum() / (len(daily) * design.n_doublets))
    on = daily["n_active"] > 0
    t_inj = float(
        np.average(daily.loc[on, "injection_temperature_c"], weights=active[on])
        if on.any()
        else 60.0
    )
    reservoir = simulate_doublet(
        depth_m=design.depth_m,
        flow_m3h=mean_flow,
        well_spacing_m=well_spacing_m,
        years=years,
        permeability_md=permeability_md,
        injection_temperature_c=t_inj,
    )
    by_year = {}
    for year in evaluate_years:
        k = min(year, years) - 1
        drop = max(0.0, reservoir["temperature_drop_c"][k])
        a = dict(assumptions, production_temperature_drop_c=drop)
        if correct_hydraulics:
            a["productivity_ratio"] = reservoir["productivity_ratio"][k]
            a["injectivity_ratio"] = reservoir["injectivity_ratio"][k]
        _, s = run_year(design, demand, challenge, a)
        by_year[year] = {
            "production_temperature_drop_c": drop,
            "productivity_ratio": a.get("productivity_ratio", 1.0),
            "injectivity_ratio": a.get("injectivity_ratio", 1.0),
            "lcoe_eur_per_mwh": s["economics"]["lcoe_eur_per_mwh"],
            "geothermal_share_of_heat": s["kpi"]["geothermal_share_of_heat"],
            "purchased_gas_mwh": s["energy_mwh"]["purchased_gas_fuel"],
            "co2_t_per_year": s["kpi"]["co2_t_per_year"],
            "all_hard_constraints_met": s["all_hard_constraints_met"],
        }
    return {
        "design": design.name,
        "steady_state": {
            "lcoe_eur_per_mwh": steady["economics"]["lcoe_eur_per_mwh"],
            "co2_t_per_year": steady["kpi"]["co2_t_per_year"],
        },
        "mean_flow_per_doublet_m3h": mean_flow,
        "mean_injection_temperature_c": t_inj,
        "reservoir": reservoir,
        "by_year": by_year,
    }
