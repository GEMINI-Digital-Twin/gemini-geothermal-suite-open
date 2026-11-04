"""Tests for the return temperature and unplanned outage tools."""

from tools import call_tool


def test_return_temperature_comparison_finds_highest_return_without_penalty():
    """Below 50 C the 40 C brine cooling limit caps heat, so cost stops falling."""
    result = call_tool("compare_return_temperatures", {"doublets": 2, "depth_m": 3000, "return_options": [40, 50, 60]})
    assert result["returns_with_lowest_cost_c"] == [40.0, 50.0]
    assert result["best_return_c"] == 50.0
    costs = {row["return_c"]: row["levelised_cost_eur_per_mwh"] for row in result["options"]}
    assert costs[60.0] > costs[50.0]


def test_return_temperature_comparison_needs_two_options():
    result = call_tool("compare_return_temperatures", {"doublets": 2, "depth_m": 3000, "return_options": [50]})
    assert result["nothing_was_run"]


def test_unplanned_outage_needs_more_backup_than_planned():
    """A failure over the peak must raise the backup boiler size, and the cost with it."""
    result = call_tool("check_unplanned_outage", {"doublets": 2, "depth_m": 3000})
    assert result["backup_peak_mw_with_failure"] > result["backup_peak_mw_planned_only"]
    assert result["levelised_cost_with_backup_for_failure"] > result["levelised_cost_planned_only"]
    assert result["checks_failed"] == []


def test_one_doublet_failure_needs_backup_for_the_whole_peak():
    result = call_tool("check_unplanned_outage", {"doublets": 1, "depth_m": 3000})
    assert result["backup_peak_mw_with_failure"] >= 29.0


def test_unplanned_outage_rejects_four_doublets():
    result = call_tool("check_unplanned_outage", {"doublets": 4, "depth_m": 3000})
    assert result["nothing_was_run"]


def test_compare_designs_brackets_best_depth():
    """With 3000 m as the deepest depth tried, a deeper option is added for the winner."""
    result = call_tool("compare_designs", {"doublet_options": [1, 2, 3], "depths_m": [2000, 2500, 3000]})
    assert result["lowest_cost_eligible"]["depth_m"] == 3000.0
    assert {"doublets": 2, "depth_m": 3500.0, "layout": "chp+absorption"} in result["depths_added_to_bracket_best"]


def test_return_temperature_comparison_uses_demand_scenario():
    """A 50 MW scenario must give different numbers from the supplied 30 MW profile."""
    base = call_tool("compare_return_temperatures", {"doublets": 3, "depth_m": 3000, "return_options": [40, 50]})
    scenario = call_tool(
        "compare_return_temperatures", {"doublets": 3, "depth_m": 3000, "return_options": [40, 50], "heating_peak_mw": 50}
    )
    assert scenario["heating_peak_mw_used"] == 50.0
    assert scenario["lowest_cost_eur_per_mwh"] != base["lowest_cost_eur_per_mwh"]


def test_compare_designs_ranks_layouts():
    """With a CHP on the produced gas, 2 x 3000 m with absorption cooling is the cheapest eligible design."""
    result = call_tool("compare_designs", {"doublet_options": [2], "depths_m": [3000, 3500]})
    best = result["lowest_cost_eligible"]
    assert (best["doublets"], best["depth_m"], best["layout"]) == (2, 3000.0, "chp+absorption")
    assert "boiler+electric" in result["trade_off"]


def test_electric_beats_absorption_with_a_gas_boiler():
    """Without a CHP, electric chillers emit less than absorption: absorption needs more brine and gas."""
    electric = call_tool("estimate_cost", {"doublets": 2, "depth_m": 3000, "layout": "boiler+electric"})
    absorption = call_tool("estimate_cost", {"doublets": 2, "depth_m": 3000, "layout": "boiler+absorption"})
    year_electric = call_tool("simulate_year", {"doublets": 2, "depth_m": 3000, "layout": "boiler+electric"})
    year_absorption = call_tool("simulate_year", {"doublets": 2, "depth_m": 3000, "layout": "boiler+absorption"})
    assert electric["levelised_cost_eur_per_mwh"] < absorption["levelised_cost_eur_per_mwh"]
    assert year_electric["co2_kt"] < year_absorption["co2_kt"]


def test_chp_cuts_grid_electricity_and_matches_gemini():
    """Produced gas in a CHP covers most of the plant's electricity, checked daily against GEMINI's CHP."""
    boiler = call_tool("simulate_year", {"doublets": 2, "depth_m": 3000, "layout": "boiler+absorption"})
    chp = call_tool("simulate_year", {"doublets": 2, "depth_m": 3000, "layout": "chp+absorption"})
    assert chp["checks_failed"] == []
    assert chp["electricity_gwh"] < 0.5 * boiler["electricity_gwh"]
    assert chp["chp_electricity_gwh"] > 0
    assert chp["co2_kt"] < boiler["co2_kt"]


def test_heat_pump_layout_removes_backup_at_2000_m():
    """At 2000 m a heat pump uses the brine below the heat exchanger and replaces the backup boiler."""
    boiler = call_tool("simulate_year", {"doublets": 2, "depth_m": 2000, "layout": "boiler+electric"})
    heat_pump = call_tool("simulate_year", {"doublets": 2, "depth_m": 2000, "layout": "heat_pump+electric"})
    assert heat_pump["checks_failed"] == []
    assert heat_pump["backup_peak_mw"] < 0.1 < boiler["backup_peak_mw"]
    assert heat_pump["co2_kt"] < boiler["co2_kt"]


def test_unknown_layout_is_rejected():
    result = call_tool("simulate_year", {"doublets": 2, "depth_m": 3000, "layout": "solar+magic"})
    assert result["nothing_was_run"]


def test_uncertainty_keeps_choice_and_rule():
    """Under sampled subsurface, demand and grid inputs the chosen design stays valid and cleaner."""
    result = call_tool(
        "assess_uncertainty",
        {"doublets": 2, "depth_m": 3000, "layout": "boiler+electric", "alternative_layout": "boiler+absorption"},
    )
    assert result["all_checks_pass_pct"] == 100.0
    assert result["meets_geothermal_first_pct"] >= 90.0
    cost = result["levelised_cost_eur_per_mwh"]
    assert cost["p10"] < cost["p50"] < cost["p90"]
    assert result["versus_alternative"]["design_lower_co2_pct"] >= 90.0


def test_latin_hypercube_covers_each_range():
    from uncertainty import RANGES, latin_hypercube

    samples = latin_hypercube(20)
    for name, (low, high) in RANGES.items():
        values = sorted(sample[name] for sample in samples)
        assert low <= values[0] < low + (high - low) / 20
        assert high - (high - low) / 20 < values[-1] <= high


def test_gemini_year_passes_every_day():
    """Every operating day of the chosen design, solved by GEMINI, stays within the limits."""
    result = call_tool("validate_year_in_gemini", {"doublets": 2, "depth_m": 3000, "layout": "boiler+electric"})
    assert result["gemini_days_run"] == 365
    assert result["days_failing_gemini_checks"] == 0
    assert result["worst_brine_cooling_c"] <= 40.0
    assert result["max_heat_difference_pct"] <= 0.5


def test_gemini_year_passes_with_absorption_and_chp():
    """The brine loop of the absorption and CHP layout also stays within the limits on every day."""
    result = call_tool("validate_year_in_gemini", {"doublets": 2, "depth_m": 3000, "layout": "chp+absorption"})
    assert result["gemini_days_run"] == 365
    assert result["days_failing_gemini_checks"] == 0


def test_uncertainty_rejects_same_alternative():
    result = call_tool(
        "assess_uncertainty",
        {"doublets": 2, "depth_m": 3000, "layout": "boiler+electric", "alternative_layout": "boiler+electric"},
    )
    assert result["nothing_was_run"]


def test_compressed_comparison_is_much_shorter():
    import json

    from run_agent import for_model

    result = call_tool("compare_designs", {"doublet_options": [1, 2, 3], "depths_m": [2000, 2500, 3000]})
    assert len(json.dumps(for_model("compare_designs", result))) < 0.6 * len(json.dumps(result))
    assert result["alternative_for_verify_design"]["alternative_layout"] == "chp+absorption"


def test_verify_design_combines_the_four_checks():
    result = call_tool(
        "verify_design",
        {"doublets": 2, "depth_m": 3000, "layout": "boiler+electric", "alternative_layout": "boiler+absorption"},
    )
    assert result["return_temperature"]["best_return_c"] == 50.0
    assert result["unplanned_failure"]["backup_peak_mw_with_failure"] > 10.0
    assert result["uncertainty"]["all_checks_pass_pct"] == 100.0
    assert result["gemini_year"]["days_failing_gemini_checks"] == 0


def test_compare_designs_goes_deeper_when_nothing_is_eligible():
    """Screening only 2000 m finds no eligible design, so deeper depths are added until one is."""
    result = call_tool("compare_designs", {"doublet_options": [1, 2, 3], "depths_m": [2000]})
    assert result["depths_added_because_none_eligible"]
    assert result["lowest_cost_eligible"] is not None
    best = result["lowest_cost_eligible"]
    assert (best["doublets"], best["depth_m"], best["layout"]) == (2, 3000.0, "chp+absorption")
