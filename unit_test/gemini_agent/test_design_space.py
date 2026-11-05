"""Tests for the wider design space: screen 'vary' and per-doublet outage start days."""

import numpy as np
import pytest

from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.tools import ToolBox
from gemini_design.annual import schedule_outages
from gemini_design.challenge import load_demand
from gemini_design.plant import Design

INPUTS = "simulator_examples/hackathon_inputs"


@pytest.fixture(scope="module")
def toolbox(tmp_path_factory):
    """Build a tool box in a temporary workspace."""
    ws = tmp_path_factory.mktemp("ws")
    return ToolBox(load_demand(INPUTS), RunLedger(ws), ProjectNotes(ws), ws, workers=1)


def test_outage_start_days_place_each_doublet_stop():
    """Fixed start days stop each doublet there; -1 goes to a free low-load window."""
    demand = load_demand(INPUTS)
    design = Design(n_doublets=3, depth_m=3100, cooling="electric", outage_start_days=(10, -1, 200))
    available = schedule_outages(demand, design)
    assert available.shape == (365, 3)
    assert not available[10:45, 0].any() and available[:10, 0].all()
    assert not available[200:235, 2].any()
    down = np.flatnonzero(~available[:, 1])
    assert len(down) == 35 and not (~available[down, 0]).any() and not (~available[down, 2]).any()
    assert "stops10,auto,200" in design.name
    with pytest.raises(ValueError):
        Design(n_doublets=2, depth_m=3100, outage_start_days=(10,))


def test_default_design_key_is_unchanged():
    """Designs without outage_start_days keep their earlier dict (and run keys)."""
    assert "outage_start_days" not in Design(n_doublets=1, depth_m=2500).as_dict()


def test_screen_varies_other_run_design_arguments(toolbox):
    """'vary' grids any run_design argument and reports impossible combinations."""
    out = toolbox.call(
        "screen",
        {
            "n_doublets": [2],
            "depths_m": [3100],
            "upgrades": ["boiler"],
            "coolings": ["electric", "absorption"],
            "vary": {"boiler_capacity_mw": [30, 33], "free_cooling": [False, True]},
            "top": 10,
        },
    )
    assert "error" not in out, out
    # absorption + free cooling is not a design: 2 x 2 electric + 2 absorption
    assert out["designs_run"] == 6
    assert sum(out["skipped_combinations"].values()) == 2
    bad = toolbox.call(
        "screen",
        {
            "n_doublets": [1],
            "depths_m": [3100],
            "upgrades": ["boiler"],
            "coolings": ["electric"],
            "vary": {"depth_m": [2000]},
        },
    )
    assert "can not be varied" in bad["error"]


def test_stress_test_reruns_a_design_in_harder_conditions(toolbox):
    """stress_test logs one gated run per case and reports whether demand is still met."""
    base = toolbox.call(
        "run_design", {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"}
    )
    out = toolbox.call("stress_test", {"run_id": base["run_id"], "cases": ["trip_at_peak"]})
    assert "error" not in out, out
    row = out["cases"][0]
    assert row["case"] == "trip_at_peak" and row["run_id"] != base["run_id"]
    assert row["physics_gate"] == "pass"
    assert "stops" in toolbox.ledger.get(row["run_id"])["headline"]["design"]


def test_return_temperatures_are_design_choices_with_a_cost():
    """Returns other than the reference change substation area and pumping, both ways."""
    from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
    from gemini_design.network import check_returns, delta_costs, design_assumptions

    heat = np.full(365, 10e6)
    cool = np.full(365, 3e6)
    ref = delta_costs(heat, cool, CHALLENGE, ASSUMPTIONS)
    assert ref["substation_capex_eur"] == 0.0 and ref["pumping_mwh_el"] == 0.0
    low = {**ASSUMPTIONS, "heating_return_c": 33.0}
    d = delta_costs(heat, cool, CHALLENGE, low)
    assert d["substation_capex_eur"] > 0 and d["pumping_mwh_el"] < 0  # more plate, less water
    high = {**ASSUMPTIONS, "heating_return_c": 55.0}
    d = delta_costs(heat, cool, CHALLENGE, high)
    assert d["substation_capex_eur"] < 0 and d["pumping_mwh_el"] > 0
    warm = {**ASSUMPTIONS, "cooling_return_c": 29.0}
    d = delta_costs(heat, cool, CHALLENGE, warm)
    assert d["substation_capex_eur"] > 0 and d["pumping_mwh_el"] < 0
    with pytest.raises(ValueError):
        check_returns(CHALLENGE, {**ASSUMPTIONS, "heating_return_c": 31.0})
    design = Design(n_doublets=1, depth_m=3100, heating_return_c=50)
    assert design_assumptions(design, ASSUMPTIONS)["heating_return_c"] == 50.0
    assert design.as_dict()["heating_return_c"] == 50.0 and "ret50/ref" in design.name


def test_run_design_with_own_returns_is_gated(toolbox):
    """A design's own return temperatures reach the plant and the Solver cross-check."""
    args = {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"}
    base = toolbox.call("run_design", args)
    own = toolbox.call("run_design", {**args, "heating_return_c": 50, "cooling_return_c": 28})
    assert own["physics_gate"] == "pass", own
    assert own["run_id"] != base["run_id"]
    summary = toolbox.ledger.summary(own["run_id"])
    assert summary["network"]["heating_return_c"] == 50.0
    assert summary["economics"]["capex_eur"]["network_substations_vs_reference"] != 0.0


def test_mixed_doublet_depths_share_one_plant():
    """Mixed depths: hottest available doublet runs first, the cap holds for every producer."""
    from gemini_design.annual import run_year
    from gemini_design.doublet import DoubletGroup, DoubletHydraulics

    group = DoubletGroup((2500.0, 3400.0))
    assert group.active(1) == (1,)  # the deeper (hotter) doublet first
    assert group.active(1, available=[True, False]) == (0,)
    hot, cold = DoubletHydraulics(3400.0), DoubletHydraulics(2500.0)
    both = group.producer(200.0, active=(0, 1))
    t_hot = hot.producer(200.0)["wellhead_temperature_c"]
    t_cold = cold.producer(200.0)["wellhead_temperature_c"]
    assert both["cap_temperature_c"] == pytest.approx(t_hot)
    assert both["wellhead_temperature_c"] == pytest.approx(0.5 * (t_hot + t_cold))

    design = Design(n_doublets=2, depth_m=3100, cooling="electric", doublet_depths_m=(3400, 2500))
    assert design.depth_m == 3400 and design.name.startswith("2D-3400+2500m")
    same = Design(n_doublets=2, depth_m=1, doublet_depths_m=(3100, 3100)).as_dict()
    assert same["depth_m"] == 3100 and "doublet_depths_m" not in same
    daily, summary = run_year(design, load_demand(INPUTS))
    active = daily[daily["n_active"] > 0]
    assert (active["brine_cooling_k"] <= 40.0 + 1e-6).all()
    assert (active["hottest_wellhead_temperature_c"] >= active["wellhead_temperature_c"]).all()
    assert summary["reservoir"]["doublet_depths_m"] == [3400.0, 2500.0]


def test_mixed_depth_run_skips_only_the_solver_cross_check(toolbox):
    """The agent can run mixed depths; gate 4 says why it is not applicable."""
    out = toolbox.call(
        "run_design",
        {
            "n_doublets": 2,
            "depth_m": 3100,
            "doublet_depths_m": [3400, 2800],
            "upgrade": "boiler",
            "cooling": "electric",
        },
    )
    assert out["physics_gate"] == "pass", out
    gate = toolbox.ledger.get(out["run_id"])["gate"]
    assert gate["4_second_solver"]["agrees"] is None


def test_stress_test_boiler_unit_out(toolbox):
    """N-1 on the gas boiler: one of three units gone all year."""
    base = toolbox.call(
        "run_design",
        {
            "n_doublets": 2,
            "depth_m": 3100,
            "upgrade": "boiler",
            "cooling": "electric",
            "boiler_units": 3,
        },
    )
    out = toolbox.call("stress_test", {"run_id": base["run_id"], "cases": ["boiler_unit_out"]})
    assert "error" not in out, out
    request = toolbox.ledger.get(out["cases"][0]["run_id"])["request"]
    assert request["boiler_units"] == 2 and request["boiler_capacity_mw"] == pytest.approx(
        toolbox.peak_heating_mw * 2 / 3
    )
