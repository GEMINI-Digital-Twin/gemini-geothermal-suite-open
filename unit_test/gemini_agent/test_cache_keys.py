"""Cached runs and oracle grids must not be reused for other inputs."""

import warnings

from gemini_agent.bench.oracle import Oracle, grid_designs, SMALL_GRID
from gemini_agent.fingerprint import code_hash, defaults_hash, demand_hash
from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.tools import ToolBox
from gemini_design.challenge import load_demand

INPUTS = "simulator_examples/hackathon_inputs"
DESIGN = {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"}


def test_hashes_are_stable_and_see_the_demand():
    """Same demand, same hash; 10 % more energy at the same peaks, another hash."""
    demand = load_demand(INPUTS)
    assert demand_hash(demand) == demand_hash(load_demand(INPUTS))
    other = demand.copy()
    low = other["heating_mw"] < other["heating_mw"].max() * 0.9
    other.loc[low, "heating_mw"] *= 1.1
    assert demand_hash(other) != demand_hash(demand)
    assert len(code_hash()) == 12 and len(defaults_hash()) == 12


def test_reused_workspace_reruns_on_new_demand(tmp_path):
    """A workspace that ran the design on one profile does not reuse it for another."""
    demand = load_demand(INPUTS)
    other = demand.copy()
    low = other["heating_mw"] < other["heating_mw"].max() * 0.9
    other.loc[low, "heating_mw"] *= 1.1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        first = ToolBox(demand, RunLedger(tmp_path), ProjectNotes(tmp_path), tmp_path, 1)
        a = first.call("run_design", DESIGN)
        again = ToolBox(demand, RunLedger(tmp_path), ProjectNotes(tmp_path), tmp_path, 1)
        assert again.call("run_design", DESIGN).get("reused_earlier_run")
        new = ToolBox(other, RunLedger(tmp_path), ProjectNotes(tmp_path), tmp_path, 1)
        b = new.call("run_design", DESIGN)
    assert not b.get("reused_earlier_run") and b["run_id"] != a["run_id"]
    assert b["lcoe_eur_per_mwh"] != a["lcoe_eur_per_mwh"]


def test_oracle_cache_path_depends_on_demand():
    """The oracle cache file changes with the demand profile."""
    demand = load_demand(INPUTS)
    other = demand.assign(cooling_mw=demand["cooling_mw"] * 1.1)
    designs = grid_designs(SMALL_GRID)
    assert Oracle.cache_path({}, designs, demand) == Oracle.cache_path({}, designs, demand.copy())
    assert Oracle.cache_path({}, designs, demand) != Oracle.cache_path({}, designs, other)
