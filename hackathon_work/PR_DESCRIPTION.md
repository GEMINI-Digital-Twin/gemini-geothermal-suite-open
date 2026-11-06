# Hackathon: agentic 2027 geothermal design (`hackathon_work/`), plus three GEMINI issues found

**Base:** `development` · **Head:** `hackathon/agentic-design`

## Summary

This PR adds the hackathon submission as one self-contained folder, `hackathon_work/`. A design agent drives the
GEMINI brine-chain simulator through a 365-day model of a 2027 district heating (100 °C) and cooling (20 °C) system.
It checks every hard constraint and picks a design by a stated ranking rule.

**The PR changes nothing outside `hackathon_work/`.** `src/`, `simulator_examples/` and `unit_test/` are identical to
`development`, and every GEMINI workaround is applied at runtime from `hackathon_work/`. The organizer PDFs are not
included (`.gitignore`).

**Result:** 2 doublets at 3 500 m (117 °C reservoir), 300 m³/h each. The produced CO₂ is reinjected and the CH₄ feeds
the CHP. The plant emits **3 983 t CO₂/yr, 85.1% below** the gas-boiler + electric-chiller reference (26 706 t).
External gas falls from 124.1 GWh to 0.016 GWh, and demand is met on all 365 days.

## What is added

| Area | Files | What it does |
|---|---|---|
| GEMINI project | `projects/doublet_challenge.json`, `doublet_model.py`, `run_doublet_challenge.py` | The challenge doublet as a GEMINI project, with the brine PVT and a scaled ESP installed at runtime. There is a control solve for the target flow, and inputs and outputs are logged. |
| Constraint checker | `constraints.py`, `test_constraint_checker.py` | Pass, fail or missing for each hard limit, per doublet and per plant, with a reason for each. Ten tests (T0–T9), including reinjected gas that cannot dissolve. |
| 365-day model | `daily_model.py`, `demand_baseline.py`, `reference_case.py` | The GEMINI brine chain is solved per day, followed by a surface cascade: absorption chiller on the hot brine, HEX, heat pump, CHP, then boiler. It covers the 330-day source rule with staggered maintenance and annual well and engineering checks. N-1 resilience (one doublet out on the peak days) is also simulated. |
| Gas handling | `gas_solubility.py` | Three options: CHP on all gas, CO₂ reinjected, or all gas reinjected. A DERIVED dissolution check covers the reinjected gas: IAPWS G7-04 Henry constants, Weisenberger–Schumpe salting-out and Peng–Robinson. |
| Design agent | `design_agent.py`, `run_candidates.py` | The loop is propose → validate → build GEMINI JSON → 365-day model → well checks → rank → revise. Backends are `rules` (deterministic) and `claude_cli` (Claude Code). Ranking is lexicographic (external gas → emissions → grid → doublets → drilled m), with tie tolerances and a 5% parsimony rule for each depth or doublet step. Missing inputs are never invented: the agent stops and asks, or asks interactively. |
| Sensitivity | `sensitivity.py` | Ten one-at-a-time cases. The final design is re-simulated in each, and the agent is re-run to see whether its pick changes. |
| Dashboard | `make_dashboard.py`, `dashboard/index.html` | An offline page (ECharts vendored) with 15 panels, exported as 300 dpi PNGs to `outputs/figures/`. |
| Documentation | `EVIDENCE_APPENDIX.md`, `STRONG_POINTS.md`, `CLAUDE.md`, `DECISIONS_LOG.md`, `README.md` | The evidence in one place; inputs and provenance (OFFICIAL / DERIVED / ASSUMED); user decisions and minor decisions. |
| Outputs | `outputs/` | The agent logs and traces (rules, claude_cli, interactive), final design, reference, candidates, sensitivity, checker evidence and figures. Regenerable bulk (the cache and daily CSVs) is ignored. |

## How to run

Run from the repository root with the GEMINI Poetry environment (Python 3.11), on Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
py -3.11 -m poetry run python hackathon_work/test_constraint_checker.py             # 10/10 expectations met
py -3.11 -m poetry run python hackathon_work/reference_case.py                      # reference: 26 706 t
py -3.11 -m poetry run python hackathon_work/design_agent.py --clear-cache          # rules agent, 14 evaluations, ~30 s
py -3.11 -m poetry run python hackathon_work/design_agent.py --remove all           # stops and lists the 12 inputs it needs
py -3.11 -m poetry run python hackathon_work/design_agent.py --interactive --remove heating_return_T
py -3.11 -m poetry run python hackathon_work/design_agent.py --backend claude_cli   # needs Claude Code; ~USD 1.5
py -3.11 -m poetry run python hackathon_work/sensitivity.py                         # 10 agent runs, ~5 min
py -3.11 -m poetry run python hackathon_work/make_dashboard.py                      # dashboard + PNGs (needs Edge/Chrome)
```

Then open `hackathon_work/dashboard/index.html`, which needs no server.

## Results

| | Final pick | Reference |
|---|---|---|
| Design | `n2_q300_s1.8_ua1000_z3500_co2ri` | gas boiler η 0.90 + electric chiller COP 5.0 |
| Emissions | 3 983 t CO₂/yr | 26 706 t CO₂/yr |
| External gas | 0.016 GWh | 124.1 GWh |
| Grid import | 0.87 GWh | 4.75 GWh |
| Heating | HEX 100.6, heat pump 2.0, CHP 9.1, external-gas boiler 0.013 GWh (92% geothermal) | boiler |
| Cooling | absorption chiller 23.7 GWh, electric chiller 0 | electric chiller |

The evidence for these results:
- **Judges' agent-reasoning tests:** all four pass in the rules run, with trace excerpts in `EVIDENCE_APPENDIX.md` §1.
- **Second backend:** the claude_cli backend, re-run on the final model, reaches the **same pick** in 10 evaluations
  instead of 14. It made 11 calls, used 186 k input and 6.8 k output tokens, and cost USD 1.46.
- **Checker tests:** 10/10. T9 rejects reinjected CO₂ at 200× the official load (reservoir margin 0.7), and its
  control at the official load passes (margin 148).
- **Dissolution margins at the pick:** 7.3 at the injector wellhead and 148 at the reservoir. The all-gas option needs
  a dip tube of at least 558 m.
- **N-1 resilience:** with one doublet out on the peak heating day, a 15.1 MWth boiler covers the load and no demand
  is unmet.
- **Sensitivity:** the design stays feasible in all 10 cases (3 874–4 618 t). The pick changes in 5 of the 10, but
  the architecture holds in all of them. Depth moves with the gradient, and at absorption COP 0.6 a third doublet is
  added.

Known limitations:
- The wellhead reaches 114 °C, beyond the 100 °C `PVTConstantSTP` range.
- The chiller COPs are fixed.
- There is no cost model.
- The model runs at daily resolution.

All four are described in `EVIDENCE_APPENDIX.md` §9.

## GEMINI issues found (no `src/` changes in this PR)

| # | Where | Issue | Workaround here | Evidence |
|---|---|---|---|---|
| 1 | `src/gemini_model/heatpump/heatpump_basic.py` | The Nelder-Mead solve diverges at low lift or small sink flow: COP 0.014 and Th_out 409 °C, where its own equations give COP 17.7 at 100 °C. The `Ts_in_minimum` fallback returns Th_out 836 °C at COP 1.00. `get_output()` returns the internal dict instead of a copy, so a stored result is overwritten by the next call. | `daily_model.py` solves the same two equations with a bracketing root finder and logs HeatpumpBasic as a cross-check. | `hackathon_work/outputs/evidence/heatpumpbasic_issue.md` (repro + proposed fix), `hackathon_work/repro_heatpumpbasic.py` |
| 2 | ESP in `src/gemini_simulator/well_flow` (HC27000 curve) | Efficiency is an output of the curve (58% in the example run, 62–65% at the challenge flows) and cannot be set to the challenge's 70%. Frequency scales head by (f/60)² but does not extend the flow range: the curve has zero head above 280 m³/h, and the challenge doublet reaches only ~176 m³/h at 70 Hz. | Pump power is reported as Q·Δp/0.70 and checked (test T6). `ScaledESP` stage options are installed at runtime. | `hackathon_work/CLAUDE.md` (Known code facts), `hackathon_work/doublet_model.py` |
| 3 | Fluid properties | `src/gemini_model/fluid/pvt_water_stp.py:16` `PVTConstantSTP` is constant, with `temperature_max` 100 °C. `src/gemini_simulator/kpi.py:35-36`, `heat_exchanger.py:16-17` and `boiler.py:16-17` hard-code 1 050 kg/m³ and 4 200 J/(kg K). The separator's gas composition is unused, and wells carry gas mass fraction 0. | The challenge brine (1 030 / 4 100) is installed at runtime by replacing `well_flow.PVTConstantSTP`, and the override is verified. The surface models get it through their parameters, and the KPIs are computed in `hackathon_work`. | `hackathon_work/doublet_model.py` (`install_brine_pvt`) |

Issue 1 is worth fixing upstream. The proposed patch in `heatpumpbasic_issue.md` makes three changes: it replaces
Nelder-Mead with a bracketed root solve, never returns Th_out above the target, and returns `dict(self.output)`. It
also adds validation warnings. I'm happy to open it as a separate
PR against `src/` if the maintainers want it.

## Checklist

- [x] No changes to `src/`, `simulator_examples/` or `unit_test/` (`git diff development --name-only` lists only `hackathon_work/`)
- [x] Constraint checker tests: 10/10 (`outputs/evidence/constraint_checker_tests.txt`)
- [x] Agent outputs regenerated from a fresh cache on this commit (rules, claude_cli and sensitivity)
- [x] Every new value tagged OFFICIAL / DERIVED / ASSUMED in `_provenance` (counts in `EVIDENCE_APPENDIX.md` §7)
- [x] Organizer PDFs are not committed

🤖 Generated with [Claude Code](https://claude.com/claude-code)
