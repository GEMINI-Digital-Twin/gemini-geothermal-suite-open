"""Hand-calculation tests for the cost model and the reviewer."""

import pytest
from costs import capital_recovery_factor, design_costs, well_cost_eur
from reviewer import review, ungrounded_numbers

YEAR = {
    "geothermal_heat_gwh": 96.7,
    "drive_gwh": 32.5,
    "gas_gwh": 14.9,
    "backup_gwh": 0.1,
    "absorption_gwh": 21.8,
    "electric_cooling_gwh": 1.9,
    "electricity_gwh": 6.62,
    "co2_kt": 6.6,
    "backup_peak_mw": 0.9,
    "electric_cooling_peak_mw": 3.4,
    "absorption_peak_mw": 10.0,
    "checks_failed": [],
}


def test_well_cost_matches_research_example():
    """ThermoGIS formula at 2,500 m should give about 4.88 MEUR per well."""
    assert well_cost_eur(2500) == pytest.approx(4.8804e6, rel=1e-4)


def test_capital_recovery_factor():
    """7% over 15 years gives a capital recovery factor of about 0.1098."""
    assert capital_recovery_factor() == pytest.approx(0.10979, abs=1e-5)


def test_design_cost_adds_up():
    """Capital should be the sum of wells, surface, chillers and backup."""
    result = design_costs(2, 3200, YEAR)
    wells = 4 * well_cost_eur(3200)
    surface = 2 * (3.5e6 + 882 * 13020 + 0.5e6)
    equipment = 400 * 10000 + 200 * 3400 + 100 * 900
    assert result["capital_meur"] == pytest.approx((wells + surface + equipment) / 1e6, abs=0.05)
    delivered = 96.7 + 14.9 + 0.1 + 21.8 + 1.9
    assert result["energy_delivered_gwh"] == pytest.approx(delivered, abs=0.05)
    assert result["levelised_cost_eur_per_mwh"] == pytest.approx(
        result["annual_cost_meur"] * 1e6 / (delivered * 1000), abs=0.1
    )


def test_reviewer_requires_recommendation_line():
    """An answer without the recommendation line should be sent back."""
    assert review("Use two doublets.", "q", {}, {}, [])


def test_reviewer_accepts_grounded_answer():
    """A tested, costed, grounded answer with enough options should pass."""
    year_runs = {(2, 3000.0): YEAR, (2, 3200.0): YEAR, (2, 3500.0): YEAR, (3, 3200.0): YEAR}
    cost = {"levelised_cost_eur_per_mwh": 60.0, "meets_geothermal_first": True}
    cost_runs = {design: cost for design in year_runs}
    answer = "Backup is 0.9 MW and CO2 is 6.6 kt.\nRECOMMENDATION: doublets=2, depth_m=3200"
    assert review(answer, "q", year_runs, cost_runs, [YEAR, cost]) == []


def test_reviewer_flags_invented_number():
    """A number not found in any tool result should be flagged."""
    assert ungrounded_numbers("CO2 is 4.4 kt", [YEAR], "q") == ["4.4"]


def test_reviewer_flags_cheaper_unexplained_design():
    """A clearly cheaper passing design that the answer ignores should be flagged."""
    year_runs = {(2, 3200.0): YEAR, (3, 2800.0): YEAR}
    cost_runs = {
        (2, 3200.0): {"levelised_cost_eur_per_mwh": 70.0, "meets_geothermal_first": True},
        (3, 2800.0): {"levelised_cost_eur_per_mwh": 60.0, "meets_geothermal_first": True},
    }
    answer = "RECOMMENDATION: doublets=2, depth_m=3200"
    problems = review(answer, "q", year_runs, cost_runs, [YEAR, cost_runs])
    assert any("costs 60.0" in problem for problem in problems)


def test_reviewer_rejects_design_failing_geothermal_first():
    """A design that buys too much energy should be rejected even if cheapest."""
    year_runs = {(1, 3000.0): YEAR, (2, 3000.0): YEAR}
    cost_runs = {
        (1, 3000.0): {"levelised_cost_eur_per_mwh": 64.2, "meets_geothermal_first": False,
                      "bought_energy_share_pct": 34.6},
        (2, 3000.0): {"levelised_cost_eur_per_mwh": 79.4, "meets_geothermal_first": True},
    }
    answer = "RECOMMENDATION: doublets=1, depth_m=3000"
    problems = review(answer, "q", year_runs, cost_runs, [YEAR, cost_runs])
    assert any("geothermal-first" in problem for problem in problems)


def test_reviewer_asks_for_depth_on_both_sides():
    """A recommended depth at the edge of what was costed should be questioned."""
    year_runs = {(2, 2800.0): YEAR, (2, 3000.0): YEAR, (3, 3000.0): YEAR}
    cost = {"levelised_cost_eur_per_mwh": 79.4, "meets_geothermal_first": True}
    cost_runs = {design: cost for design in year_runs}
    answer = "RECOMMENDATION: doublets=2, depth_m=3000"
    problems = review(answer, "q", year_runs, cost_runs, [YEAR, cost])
    assert any("deeper option" in problem for problem in problems)
