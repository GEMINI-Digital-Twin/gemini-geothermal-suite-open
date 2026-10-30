"""Tests for the uncertainty parameters, sourced economics, Monte Carlo study and agent tool."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, load_demand
from gemini_uncertainty.economics import capital_cost, energy_prices, thermogis_well_cost_eur
from gemini_uncertainty.parameters import (
    PARAMETERS,
    SOURCES,
    base_values,
    get_parameters,
    sample,
)
from gemini_uncertainty.study import (
    apply_values,
    compare,
    design_from_name,
    evaluate,
    monte_carlo,
    summarise,
    tornado,
    with_capacity,
)
from gemini_uncertainty.tool import TOOL_SPEC, run_tool

INPUTS = Path(__file__).resolve().parents[2] / "simulator_examples" / "hackathon_inputs"


@pytest.fixture(scope="module")
def demand():
    return load_demand(INPUTS)


def test_every_parameter_has_a_known_source_and_sane_quantiles():
    for p in PARAMETERS:
        for key in p.source.split("+"):
            assert key in SOURCES, (p.name, key)
        p10, p50, p90 = p.ppf([0.1, 0.5, 0.9])
        assert p10 < p50 < p90
        assert p10 <= p.base <= p90


def test_lognormal_hits_its_stated_p10_p90():
    perm = get_parameters(["permeability_md"])[0]
    p10, p50, p90 = perm.ppf([0.1, 0.5, 0.9])
    assert p10 == pytest.approx(100.0, rel=1e-6)
    assert p50 == pytest.approx(200.0, rel=1e-6)
    assert p90 == pytest.approx(400.0, rel=1e-6)


def test_latin_hypercube_covers_each_marginal_once_per_stratum():
    n = 50
    s = sample(PARAMETERS, n, seed=1)
    assert s.shape == (n, len(PARAMETERS))
    for p in PARAMETERS:
        lo, hi = p.ppf([0.0, 1.0])
        assert s[p.name].between(lo - 1e-9, hi + 1e-9).all()
        # LHS: exactly one sample in each 1/n probability stratum
        u = np.array([_cdf_bin(p, v, n) for v in s[p.name]])
        assert np.array_equal(np.sort(u), np.arange(n))


def _cdf_bin(param, value, n):
    """Return the 1/n probability stratum of ``value`` by bisection on ``ppf``."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if param.ppf(mid) < value else (lo, mid)
    return min(int(lo * n), n - 1)


def test_overrides_and_unknown_names():
    p = get_parameters(overrides={"co2_price_eur_per_t": {"args": [50, 60, 70]}})
    assert {x.name: x for x in p}["co2_price_eur_per_t"].base == 60
    with pytest.raises(KeyError):
        get_parameters(overrides={"not_a_parameter": {}})


def test_thermogis_well_cost_matches_published_curve():
    # 1.3 x (0.25e6 + 700 x 2500 + 0.2 x 2500^2) = 4.225 MEUR
    assert thermogis_well_cost_eur(2500.0) == pytest.approx(4.225e6)
    assert thermogis_well_cost_eur(3100.0) > thermogis_well_cost_eur(2500.0)


def test_capital_cost_scales_wells_and_surface_separately():
    d = design_from_name("2D-3100m-boiler-electric")
    base = capital_cost(d, ASSUMPTIONS)
    wells_up = capital_cost(d, ASSUMPTIONS, well_cost_factor=1.5)
    surface_up = capital_cost(d, ASSUMPTIONS, surface_cost_factor=1.2)
    assert base["wells"] == pytest.approx(4 * thermogis_well_cost_eur(3100.0))
    assert wells_up["wells"] == pytest.approx(1.5 * base["wells"])
    assert wells_up["boiler"] == pytest.approx(base["boiler"])
    assert surface_up["boiler"] == pytest.approx(1.2 * base["boiler"])
    assert surface_up["wells"] == pytest.approx(base["wells"])


def test_energy_prices_are_derived_consistently():
    a = energy_prices(
        {
            "electricity_wholesale_eur_per_mwh": 80.0,
            "electricity_adder_eur_per_mwh": 30.0,
            "ttf_gas_eur_per_mwh": 40.0,
        },
        ASSUMPTIONS,
    )
    assert a["electricity_price_eur_per_mwh"] == pytest.approx(110.0)
    assert a["electricity_export_price_eur_per_mwh"] == pytest.approx(72.0)
    assert a["gas_price_eur_per_mwh"] == pytest.approx(45.0)
    assert a["electricity_export_price_eur_per_mwh"] < a["electricity_price_eur_per_mwh"]


def test_apply_values_routes_each_target(demand):
    values = dict(base_values(), permeability_md=50.0, skin=2.0, heating_scale=1.1)
    c, a, dem = apply_values(values, demand)
    assert c["permeability_md"] == 50.0 and CHALLENGE["permeability_md"] == 200.0
    assert a["skin"] == 2.0 and ASSUMPTIONS["skin"] == 0.0
    assert dem["heating_mw"].max() == pytest.approx(1.1 * demand["heating_mw"].max())
    assert dem["cooling_mw"].equals(demand["cooling_mw"])


def test_design_names_round_trip_and_resizing():
    d = design_from_name("2D-3100m-boiler-absorption+C12")
    assert d.chiller_capacity_mw == 12.0 and d.electric_backup_mw == 6.0
    assert d.name == "2D-3100m-boiler-absorption+C12"
    assert with_capacity(design_from_name("1D-2800m-boiler-electric"), boiler_mw=33).name.endswith(
        "+B33"
    )
    with pytest.raises(ValueError):
        design_from_name("4D-nonsense")


def test_evaluate_base_case_meets_demand_and_bigger_cooling_does_not(demand):
    d = design_from_name("2D-3100m-boiler-electric")
    base = evaluate(d, base_values(), demand)
    assert base["demand_met"] and base["operational_ok"]
    assert 20.0 < base["lcoe_eur_per_mwh"] < 60.0
    hot_summer = evaluate(d, dict(base_values(), cooling_scale=1.2), demand)
    assert not hot_summer["cooling_met"]
    assert hot_summer["unmet_cooling_mwh"] > 0
    resized = evaluate(with_capacity(d, 12.5), dict(base_values(), cooling_scale=1.2), demand)
    assert resized["cooling_met"]


def test_low_temperature_gradient_needs_more_gas(demand):
    d = design_from_name("2D-3100m-boiler-electric")
    cold = evaluate(d, dict(base_values(), geothermal_gradient_c_per_km=27.0), demand)
    warm = evaluate(d, dict(base_values(), geothermal_gradient_c_per_km=33.0), demand)
    assert cold["reservoir_temperature_c"] < warm["reservoir_temperature_c"]
    assert cold["purchased_gas_mwh"] > warm["purchased_gas_mwh"]


def test_monte_carlo_summary_compare_and_tornado(demand):
    names = ["2D-3100m-boiler-electric", "1D-2800m-boiler-electric"]
    designs = [design_from_name(n) for n in names]
    params = get_parameters(["cooling_scale", "co2_price_eur_per_t"])
    results, samples = monte_carlo(designs, demand, n=8, seed=3, params=params, workers=1)
    assert len(results) == 16 and len(samples) == 8
    summary = summarise(results)
    assert set(summary["design"]) == set(names)
    assert summary["p_demand_met"].between(0, 1).all()
    # cooling is only unmet when the cooling scale pushes the peak above 10 MW
    r0 = results[results["design"] == names[0]]
    assert (r0.loc[~r0["cooling_met"], "cooling_scale"] > 1.0).all()
    cmp = compare(results, *names)
    assert cmp["n"] == 8 and 0.0 <= cmp["p_a_cheaper"] <= 1.0
    assert cmp["p_a_lower_co2"] == 1.0  # two deep doublets burn far less gas
    tor = tornado(designs[0], demand, params, workers=1)
    assert list(tor.columns[:2]) == ["parameter", "label"]
    co2 = tor.set_index("parameter").loc["co2_price_eur_per_t"]
    assert co2["lcoe_high"] > co2["lcoe_low"]


def test_tool_spec_and_errors(demand):
    assert TOOL_SPEC["name"] == "assess_design_uncertainty"
    assert TOOL_SPEC["parameters"]["required"] == ["designs"]
    bad = run_tool({"designs": ["9D-1m-x-y"]}, demand=demand)
    assert "error" in bad
    too_many = run_tool({"designs": ["2D-3100m-boiler-electric"], "n_samples": 5}, demand=demand)
    assert "error" in too_many


def test_tool_runs_end_to_end(demand, tmp_path):
    out = run_tool(
        {
            "designs": ["2D-3100m-boiler-electric", "1D-2800m-boiler-electric"],
            "n_samples": 8,
            "fix_parameters": [p.name for p in PARAMETERS if p.name != "permeability_md"],
            "output_dir": str(tmp_path),
        },
        demand=demand,
        workers=1,
    )
    assert out["sampled_parameters"] == ["permeability_md"]
    assert len(out["summary"]) == 2
    assert out["paired_comparisons"][0]["n"] == 8
    assert pd.read_csv(tmp_path / "mc_results.csv").shape[0] == 16
