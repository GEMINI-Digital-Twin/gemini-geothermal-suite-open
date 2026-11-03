# Strong points and evidence

What sets this submission apart, with the file that proves each point. Paths are relative
to `hackathon_work/`. Numbers are from the committed outputs (rules backend, final pick
`n2_q300_s1.8_ua1000_z3250`: 2 doublets at 3 250 m, 110 °C reservoir).

**Headline:** 5 148 t CO₂/yr, 80.7% below the conventional reference (gas boiler + electric
chiller, 26 706 t). External gas falls from 124.1 GWh to 0.004 GWh. Every day of 2027 is
served at 100 °C heating and 20 °C cooling, and all four judges' agent-reasoning tests pass.

| # | Strong point | What it shows | Evidence |
|---|---|---|---|
| 1 | **Absorption cooling on the hot brine** | At the pick, the absorption chiller sits at the hot end of the brine (before the HEX) and covers all 23.7 GWh of cooling. The electric chiller supplies 0 GWh. Drive limits (75 °C inlet, 70 °C outlet) are enforced every day. | `outputs/agent/final_design/summary.json` (`cool_absorption_GWh`), `daily_model.py`, dashboard panel 3 |
| 2 | **Cascade heating to the fixed 100 °C** | Heat goes HEX → heat pump on the brine leaving the HEX → CHP heat → boiler. At the pick: HEX 90.3, HP 11.4, CHP 9.9, external-gas boiler 0.003 of 111.7 GWh (91% geothermal). The 87 °C official reservoir cannot supply 100 °C through a HEX alone; the cascade closes the gap. | `outputs/agent/final_design/summary.json`, `outputs/candidates/base/comparison.md`, dashboard panels 2 and 7 |
| 3 | **CHP on the produced gas** | All 18.6 GWh of produced gas (GLR 0.8) goes to CHP first, with almost none flared. That gives 5.0 GWh of electricity offsetting plant load and 9.9 GWh of 100 °C top-up heat, so the heat pump only covers the lift CHP cannot. | `outputs/agent/final_design/summary.json` (`produced_gas_*`, `el_chp_GWh`), `daily_model.py` |
| 4 | **Depth parsimony rule** | Depth is a design variable: a 250 m ladder from 2 500 m, where each step is kept only if emissions fall ≥ 5%. A step within the tie tolerance of 5% counts as *not* met (conservative, because drilling cost and risk are not modelled). 3 500 m (−4.994%) is recorded as the marginal sensitivity case, not taken. | `outputs/agent/agent_trace.md` (Final pick, Marginal sensitivity cases), `run_candidates.py` (`threshold_test`), dashboard panel 5 |
| 5 | **Pluggable agent** | One loop (propose → validate → build GEMINI JSON → 365-day model → well checks → rank → revise) with interchangeable backends. `rules` is deterministic, needs no API and runs in ~12 s from a cold cache. `claude_cli` asks Claude Code for each candidate as JSON, and the agent still validates every proposal. The claude_cli run reached the same 2 doublets at 3 250 m (it ran on the earlier model version, 5 376 t). | `design_agent.py`, `outputs/agent/`, `outputs/agent/claude_cli/agent_trace.md` |
| 6 | **Missing-input handling (never invents a value)** | `REQUIRED_INPUTS` lists 12 inputs not in the organizers' data, each with unit, why it is needed, plausible range and provenance (OFFICIAL / DERIVED / ASSUMED). All are checked at startup. Any can be removed for the demo (`--remove NAME[,NAME]` or `all`): the default run stops with the full list, and `--interactive` asks, validates (re-asking on bad input) and continues with logged, timestamped answers. | `design_agent.py` (`REQUIRED_INPUTS`), `outputs/agent/agent_trace.md` (Scenario A), `outputs/agent/interactive/agent_trace.md`, dashboard panel 9 |
| 7 | **Constraint checker with negative tests** | Hard limits are checked per doublet and per plant with a reason for each. Negative cases cover 350 and 30 m³/h, 45 K brine ΔT, 4 doublets, 77.75 °C supply, curve-efficiency pump power, volume imbalance and missing cooling: 9/9 expectations met. In the agent, test (ii) shows 350 m³/h rejected and revised to 300 m³/h. | `test_constraint_checker.py`, `outputs/evidence/constraint_checker_tests.{txt,json}`, `constraints.py` |
| 8 | **GEMINI issues found and reported** | We found three `HeatpumpBasic` problems (diverging solve at low lift, a nonsensical `Ts_in_minimum` fallback, aliased `get_output()`), with a repro and a proposed fix. We do not edit `src/`: the daily model solves the same two equations with a bracketing root finder. We also report that ESP frequency does not extend the HC27000 flow range (zero head above 280 m³/h) and that the wellhead exceeds `PVTConstantSTP`'s 100 °C range from 3 000 m, which is flagged in the trace. | `outputs/evidence/heatpumpbasic_issue.md`, `repro_heatpumpbasic.py`, `CLAUDE.md` (GEMINI notes) |
| 9 | **Well engineering checks** | The ESP setting depth is a design variable: the shallowest depth with intake ≥ 30 bar at the flow cap (700 m at the pick, 30.9 bar). Tubing velocity must stay ≤ 4 m/s in 7-inch tubing (3.35 m/s at the pick). Wellhead pressure vs vapour pressure is also checked. Both limits are annual hard checks, logged per candidate. | `outputs/agent/agent_trace.md` (well_check tables), `daily_model.py` (`place_esp`, `engineering`), `outputs/agent/final_design/summary.json` |
| 10 | **Results dashboard** | A self-contained page (ECharts vendored, works offline). It has KPIs, heat and cooling supply stacks, per-doublet brine flow with the maintenance windows, the agent path, emissions vs the reference, a schematic, constraints and the judges' tests. It also exports 300 dpi PNGs for the report. | `dashboard/index.html`, `make_dashboard.py`, `outputs/figures/p1–p9_*.png` |
| 11 | **Sensitivity** | Heat pump η 0.5 with no COP cap: the same verdicts (C1 accepted; emissions 8 545 vs 8 908 t at 2 500 m). The 3 500 m marginal case is reported with its abatement (0.26 t/yr per extra metre) and its larger PVT-range excess. The 330-day rule interpretation (per-doublet staggered maintenance) is documented and pending organizer confirmation. | `outputs/candidates/HP_eta0.5_nocap/comparison.md`, `outputs/candidates/base/comparison.md`, `outputs/agent/agent_trace.md` |

## Reproduce

```powershell
$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py --clear-cache    # design loop + test (i) halt
$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py --remove all      # halts with all 12 missing inputs
$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py --interactive --remove cooling_return_T,brine_cp
$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/test_constraint_checker.py
$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/make_dashboard.py
```

## Honest limits

- Backup capacity is unlimited by construction, so unmet demand is 0. Peaks are daily averages, not hourly.
- Drilling cost and capex/opex are not modelled, which is why the depth rule is conservative.
- Free gas at the ESP intake is not modelled, and brine properties are extrapolated above 100 °C.
- The claude_cli run did not trigger tests (ii) and (iv): it never proposed an infeasible or over-cap candidate. The rules run triggers all four.
