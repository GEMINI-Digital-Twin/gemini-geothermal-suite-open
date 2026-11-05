# SPE GeoHackathon 2026: agentic geothermal heating + cooling design

Team **Single Core** (Sa'eed Telvari). Deadline 5 Nov 2026.

## Answer (for judges)

| | Submitted design |
|---|---|
| **Design** | 2 doublets at **3.2 km** (108 °C reservoir), HEX, CHP on the co-produced gas, 33 MW gas boiler, air-cooled screw backup chiller **10 MW** with free cooling and 3 ATES (aquifer cold store) well pairs; the two doublets take their 35-day stops at different times |
| **Levelised cost** | **€36.35/MWh** of heat and cooling delivered (both counted 1:1) |
| **CO₂** | **4,269 t/yr** (mostly the co-produced reservoir gas burnt in the CHP; the rest grid power) |
| **CAPEX** | **€47.6 M** (0 MWh of bought gas) |
| **Demand met** | Heating and cooling on all 365 days (KNMI Schiphol 2025 weather; also all 35 years 1991-2025, €35.45-37.02/MWh, median €36.15; 13 of 13 stress tests) |
| **Uncertainty** | Monte Carlo, 400 samples with the weather year sampled too: P50 €37.4/MWh (P10-P90 31.6-44.7), CO₂ P50 4.27 kt; demand met in 396 of 400 (99.0 %, 95 % CI 97.5-99.6 %). The 4 misses are cooling only, in 2014 or 2020 weather with cooling demand ×1.15-1.25 |
| **Against a gas boiler + chiller plant** | 40 % cheaper, 84 % less CO₂ (€60.43/MWh and 27.1 kt for the reference; 22.8 kt/yr avoided), payback 6.7 yr, NPV €44.9 M |
| **LLM** | DeepSeek V4.1 Flash (open weights, OpenRouter), chosen on a 6-model benchmark (11 cases × 3 runs, highest thinking setting): GPT-6.1 Sol 0.95, GLM 5.3 0.89 (26 of 33 runs), DeepSeek 0.86 ($0.043 a run), Qwen 3.8 27B 0.81, GPT-6 Luna 0.76, GPT-6.1 Terra 0.96 on the 8 of 11 cases it finished; an agent that does nothing scores 0.47. `simulator_examples/agent_bench_results/2026-11-04-max/honest_scores.md` |
| **Numbers from** | `simulator_examples/study_results/2026-11-04/margin_pick/` (committed outputs; its README also has the stress tests, baselines and the readings of the brief) |

Reproduce the headline from a fresh clone (no LLM, no API key; weather file is in the repo):

```bash
pip install numpy scipy pandas matplotlib requests pytest
PYTHONPATH=src python simulator_examples/run_heat_cool_design.py          # the design + rule table, 5 s
PYTHONPATH=src python simulator_examples/run_final_pick.py \
    --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt --year 2025          # variants, 30 s
#   add --mc 400 --mc-weather for the Monte Carlo and tornado (about 15 min on 4 free cores)
```

### Every rule of the brief against the design

Printed (and written to `outputs/<design>/rules.md`) by `run_heat_cool_design.py`. All checked
on every day of the year by `gemini_design.annual` and the physics gate.

| Rule (brief) | Limit | Reached by the design | Met |
|---|---|---|---|
| Heating demand met every day | 111,668 MWh/yr | unmet 0.0 MWh | yes |
| Cooling demand met every day | 23,743 MWh/yr | unmet 0.0 MWh | yes |
| Heating network supply temperature | 100 degC | min 100.0 degC on heating days | yes |
| Cooling network supply temperature | 20 degC | set point of the chiller, free-cooling and ATES models | yes |
| Flow per active doublet | 50-300 m3/h | 112-300 m3/h | yes |
| Brine cooling across the plant | at most 40 K | max 39.99 K | yes |
| Days per doublet (geothermal source availability) | at most 330 days | 330 and 330 days | yes |
| Number of doublets | 1-3 | 2 | yes |
| Production equals injection | every day | equal on all days | yes |
| No daily rule violations | 365 days | 0 days with a violation | yes |

Choices the brief leaves to us (organiser answers of 1 and 3 Nov): the outage schedule (we stop
each doublet at a different time; the whole source down together costs more but also meets
demand), the network return temperatures (40 degC heating, 26 degC cooling) and the well depth
(reservoir temperature from the brief's gradient at the drilled depth).

### Running on other data

Every headline script, the agent CLI and the benchmark take `--inputs DIR`, a folder with one
heating and one cooling daily demand CSV (or set `GEMINI_INPUTS=DIR`):

```bash
PYTHONPATH=src python simulator_examples/run_heat_cool_design.py --inputs path/to/demand
PYTHONPATH=src python -m gemini_agent --inputs path/to/demand --ask "Which design meets demand at the lowest cost?"
```

`gemini_design.challenge.load_demand` takes the official file names or any CSV whose name
contains `heat` / `cool`, any year, any date and value column names (MW, or kW/GW by name),
`,` or `;` separators and day-first dates. A leap year's 29 February is dropped (the design year
has 365 days), gaps of up to 3 days are interpolated with a warning, and anything else raises.
Cached results are keyed on a hash of the demand and weather, the physics code and its data
files, and the default assumptions (`gemini_agent.fingerprint`), so a reused agent workspace or
the benchmark oracle never hands back numbers made from other inputs.

## What this is

An agentic AI system that designs a deep-geothermal heating **and** cooling plant for a
district, and only reports numbers that GEMINI's own models can back up. The brief
(1 to 3 doublets, a 100 degC heating network, a 20 degC cooling network, a brine with
associated gas, a 40 K brine cooling cap and a geothermal source available 330 days a year, with the
full system meeting demand on all 365) is encoded
in `gemini_design`. A tool-using LLM agent (`gemini_agent`) plans the design, asks for
missing inputs and calls deterministic tools. Those tools size the doublets, dispatch the
plant day by day for a full year on GEMINI component models (wells, ESP, heat exchanger,
heat pump, boiler, CHP and two new chiller models) and price the result. Every run goes through
a physics gate (hard rules, energy balances, a peak-day re-solve with GEMINI's
`gemini_simulator.Solver` and sanity bounds), and every number in an answer must trace to a
tool result; see "Physics gate" for what each check does and does not catch.

![Environment and workflow: the LLM agent, its 15 tools, the deterministic GEMINI-based
simulation, the physics gate and the recommended design](docs/figures/system_workflow.png)

*Environment and workflow. Editable source: `docs/figures/system_workflow.svg`, generated by
`docs/figures/make_system_schematic.py`.*

This repository is a copy of the open-source
[GEMINI Geothermal Suite](https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open)
(TNO / WEP, Apache-2.0) with the hackathon packages added on top. The upstream
`README.md` below this file describes the original suite.

## What we added to upstream GEMINI

| Path | What it is |
|---|---|
| `src/gemini_model/chiller/` | New models: `AbsorptionChiller` (hot-water fired, reversible-COP limit) and `ElectricChiller` (refrigerant approaches, DOE-2 part-load curve, staged modules, heat-rejection auxiliaries). |
| `src/gemini_design/challenge.py` | The brief as `CHALLENGE` (given values only) and `ASSUMPTIONS` (everything the brief leaves out); loads the daily 2027 demand CSVs. |
| `src/gemini_design/doublet.py` | Doublet hydraulics at any depth: reservoir temperature and pressure, drawdown, ESP and injection pump power. `DoubletGroup`: doublets at different depths sharing one surface plant (brine mixed, 40 K cap on every producer, hottest available runs first). |
| `src/gemini_design/esp.py` | Optional sized downhole pump (`esp_rated_flow_m3h`, `esp_drive` = `vsd` or `fixed`): pump curve, operating flow range, efficiency away from the rated flow, surface choke (fixed speed) or speed control (VSD), and its cost against the ESP share of the surface cost. Default: ideal pump at the brief's 70 %. |
| `src/gemini_design/plant.py` | Daily flowsheet: separator, CHP on associated gas (optional), HEX with bypass (40 K cap, 100 degC setpoint), heat pump or gas boiler top-up, absorption or electric cooling. Options: electric boiler next to the gas boiler (cheaper fuel each day), a heat-recovery heat pump from the chilled water to the heating return line (run on days it pays), gas boiler units with a part-load curve (`boiler_part_load`, on by default; 0 = rated efficiency at any load). |
| `src/gemini_design/annual.py` | 365-day dispatch with the 35-day geothermal source outage (each doublet at a different time by default; whole source together, a fixed start day, or a design's own start day per doublet as options) and the hard-constraint checks. |
| `src/gemini_design/prices.py` | Daily electricity prices (`electricity_daily_prices`, on by default; 0 = flat prices): 2025 NL day-ahead daily means from Energy-Charts (`gemini_design/data/`), with the flat import and export prices' annual means kept. |
| `src/gemini_design/network.py` | District return temperatures as a design choice: other returns than the 40 / 26 degC reference network are priced (customer substation plate area via LMTD, network circulation pumping). |
| `src/gemini_design/economics.py` | CAPEX, energy cost, CO2 and LCOE. |
| `src/gemini_design/screening.py` | Candidate grid (1 to 3 doublets x depth x heat pump/boiler x electric/absorption x CHP on/off) and a parallel ranked screen. |
| `src/gemini_design/project_json.py` | Exports the peak day as a native `gemini_simulator` project and re-runs it through the Solver as a cross-check. |
| `src/gemini_design/fimbul/` | Fimbul.jl / JutulDarcy 30-year doublet simulations as a cached lookup (`simulate_doublet`, `lifetime_performance`); the cache is committed, so Julia is only needed for new cases. |
| `src/gemini_agent/` | The design agent: OpenAI-compatible LLM client, Codex CLI client, offline `ScriptedLLM`, 15 tools, physics gate, run ledger and project notes, sandboxed `write_model`, JSONL/Markdown transcripts with token counts, the benchmark (`bench/`). See `src/gemini_agent/README.md`. |
| `src/gemini_uncertainty/` | Latin-hypercube Monte Carlo, P10/P90 tornado, paired design comparison over 14 sourced parameters, ThermoGIS-style well cost, report figures. |
| `src/gemini_simulator/registry.py` | Registry entries for `heat_pump`, `absorption_chiller`, `electric_chiller`. |
| `src/gemini_simulator/well_flow.py` | Optional `pvt` override in well configs, so wells can use the brine density and viscosity. |
| `simulator_examples/run_*.py`, `compare_agent_models.py`, `plot_fimbul_results.py` | Runnable studies (see below). |
| `simulator_examples/hackathon_inputs/` | The challenge's daily heating and cooling demand for 2027. |
| `simulator_examples/weather/` | KNMI Schiphol daily weather 1991-2025 (used for free cooling, ATES and the air-cooled chiller). |
| `simulator_examples/study_results/` | Committed outputs of every study, by date; the newest folder is the basis of the report. |
| `unit_test/gemini_model/chiller`, `unit_test/gemini_design`, `unit_test/gemini_agent`, `unit_test/gemini_uncertainty` | Tests for all of the above. |

Also on this branch (from PR #1, merged): `gemini_design.climate` and free cooling
(`simulator_examples/run_free_cooling_study.py`), and `gemini_agent.red_team` with
`physics_gate.check_units` (`simulator_examples/run_gate_red_team.py`).

**Fixes to upstream behaviour** (GEMINI bugs found while building on it; they are part of this
submission, not a separate bug-fix PR; report §4.4)

- **Injector friction sign** (`src/gemini_simulator/nodal_solver.py`,
  `_well_bottomhole_pressure_injection`): upstream walked the injector with the
  production sign convention, so friction *added* to the bottomhole pressure and deep
  injectors looked as if they needed no pump. Bottomhole pressure is now
  `P_wh + dP_grav - dP_fric`. Covered by `unit_test/gemini_simulator/test_nodal_solver.py`.
- **NORSOK M-506 corrosion rate** (`src/gemini_model/corrosion/correlation/norsok_model.py`
  and `correlations_opt/norsok_model_opt.py`): the pH function f(pH)_t exists only at the
  standard's table temperatures, and at any other temperature upstream fell back to pH 7,
  which gave rates 10-30x too high. The rate is now interpolated linearly between table
  temperatures, as the standard does, and two slips in the 5 degC pH function (a sign and a
  coefficient, 1.061 for 1.051) are corrected. Covered by
  `unit_test/gemini_design/test_realism_options.py::test_norsok_interpolates_between_table_temperatures`.
- **Compressor power** (`src/gemini_model/compressor/compressor.py`): the isentropic work
  per stage was missing the factor k, `k/(k-1) R T1 (r^((k-1)/k) - 1)`, so power was 1/k too
  low. Expected value updated in `unit_test/gemini_model/compressor/test_compressor.py`.
- **`HeatpumpBasic` overshoot** (worked around in `src/gemini_design/plant.py`; the upstream
  model file is unchanged): its fallback solve, with the source pinned at `Ts_in_minimum`,
  can overshoot the supply setpoint or report a source outlet that does not match the heat
  delivered. The design layer takes only the COP from `HeatpumpBasic` and rebuilds both
  outlet temperatures from the energy balance (Qh = Qs + W).

## Install

Tested with Python 3.13 on Linux. Upstream GEMINI targets Python 3.11 to 3.12
(`pyproject.toml`); our packages need only:

```bash
pip install numpy scipy pandas matplotlib requests pytest
```

Versions used for the numbers below: numpy 2.5.3, scipy 1.18.1, pandas 3.0.5,
matplotlib 3.11.2, requests 2.34.2, pytest 9.2.0. The full upstream suite (Flask GUI,
framework, databases) needs the Poetry environment in `pyproject.toml`; none of it is
needed for the hackathon code. Nothing is installed as a package: run everything from
the repository root with `PYTHONPATH=src`.

## Quick start

All commands run from the repository root of a fresh clone. On Windows PowerShell
replace `PYTHONPATH=src` with `$env:PYTHONPATH="src";`. Timings are wall-clock on a
4-core Linux container.

| What | Command | Time |
|---|---|---|
| The submitted design, full year, gated (incl. Solver re-solve), rule table | `PYTHONPATH=src python simulator_examples/run_heat_cool_design.py` | 5 s |
| The old fixed example design (2 doublets, boiler, absorption; not the pick) | `PYTHONPATH=src python simulator_examples/run_heat_cool_design.py --example` | 2 s |
| Final pick, 10 gated variants, reference plant (add `--mc 400` for the Monte Carlo) | `PYTHONPATH=src python simulator_examples/run_final_pick.py --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt --year 2025` | 30 s |
| Full screen on KNMI 2025 (600 designs) | `PYTHONPATH=src python simulator_examples/run_full_screen.py --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt --year 2025` | about 30 min |
| Screen the 96 basic candidate designs (no weather) | `PYTHONPATH=src python simulator_examples/run_design_screening.py` | 4 min 10 s |
| Agent demo transcripts, offline (no LLM) | `PYTHONPATH=src python simulator_examples/run_agent_transcripts.py --backend scripted` | 3 min 45 s |
| Agent CLI help | `PYTHONPATH=src python -m gemini_agent --help` | under 1 s |
| Uncertainty study (small) | `PYTHONPATH=src python simulator_examples/run_uncertainty_study.py --samples 20` | 4 min 50 s |
| Backend comparison, offline | `PYTHONPATH=src python simulator_examples/compare_agent_models.py --backend scripted --repeats 1` | 3 min 5 s |

Outputs go to `simulator_examples/outputs/` (git-ignored):

- `run_heat_cool_design.py` runs the submitted design (`PICK` in `run_final_pick.py`) on KNMI
  Schiphol 2025 weather through the agent's ToolBox and physics gate, prints the headline and
  the rule table, and writes `outputs/<design>/` (`daily.csv`, `summary.json`, `rules.md`).
  `--example` runs the old fixed example design instead and also writes
  `peak_day_project.json` and `cross_check.json`. It exits 1 if a hard constraint fails.
- `run_final_pick.py` writes `outputs/final_pick/` (`runs.csv`/`.md`, `pick.json`,
  `pick_daily.csv`, and with `--mc` the Monte Carlo and tornado).
- `run_design_screening.py` writes `outputs/screening.csv`, ranked by LCOE among
  designs that meet every hard constraint and all demand, and prints the top 15.
- `run_agent_transcripts.py` writes `outputs/agent_scripted/`: one JSONL and one
  Markdown transcript per scenario, the run ledger, project notes, generated models and
  `index.md` with token totals. It runs 10 scenarios: an open design request, an off-topic
  question, an incomplete what-if, an invented number caught by gate 6, a permeability
  what-if, writing a missing model (dry cooler), an out-of-range request caught by gate 1,
  exploring more ambitious designs (writing a storage model), a design with a stated
  objective, and memory recall.

The `scripted` backend replays a fixed policy (`gemini_agent/scenarios.py`). Its
transcripts are labelled *scripted* and are **not** LLM output. They exist so the tools,
gate, memory and logging can be run without a model server. Use `--backend live` for a
real model (next section).

## The agent

```bash
PYTHONPATH=src python -m gemini_agent                       # interactive chat
PYTHONPATH=src python -m gemini_agent --ask "Which design meets demand at the lowest cost?"
PYTHONPATH=src python simulator_examples/run_agent_transcripts.py --backend live
```

CLI flags (`python -m gemini_agent`): `--config`, `--provider`, `--model`, `--base-url`,
`--workspace`, `--session`, `--no-native-tools`, `--ask` (repeatable), `--inputs`.
`run_agent_transcripts.py` also takes `--only`, `--config`, `--keep`, `--provider`,
`--model`, `--base-url`, `--label`, `--knmi`, `--year` and `--inputs`.

**LLM backends** (presets in `src/gemini_agent/config.py`; all go through the same tools
and gate):

- **Local Ollama, Qwen3 8B (default).** `provider=ollama`, `model=qwen3:8b`,
  `http://localhost:11434/v1`. Ollama's default context is too short for the agent, so
  start the server with `OLLAMA_CONTEXT_LENGTH=16384` and run `ollama pull qwen3:8b`
  first.
- **GPT-6 Luna via the Codex CLI.** `--provider codex` (model `gpt-6-luna`; `default`
  keeps Codex's configured model). Needs the Codex CLI (`npm install -g @openai/codex`)
  and `codex login` with a ChatGPT plan; no API key. Each agent step runs one ephemeral,
  read-only `codex exec`.
- **Any OpenAI-compatible endpoint.** Presets `llamacpp`, `vllm`, `openrouter`, `openai`,
  or set `--base-url` and `--model` directly. Use `--no-native-tools` if the model handles
  native tool calls poorly (tools are then described in the prompt and `<tool_call>` JSON
  is parsed).

**Configuration** comes from, in increasing priority: the defaults, a JSON file
(`--config`; example in `simulator_examples/agent_config.example.json`), environment
variables `GEMINI_AGENT_<FIELD>`, then command-line flags. The fields are `provider`,
`base_url`, `model`, `api_key`, `temperature`, `max_tokens`, `request_timeout_s`,
`reasoning_model`, `native_tool_calling`, `max_steps_per_question`, `max_gate_retries`,
`workspace` and `screen_workers` (for example `GEMINI_AGENT_MODEL`,
`GEMINI_AGENT_BASE_URL`, `GEMINI_AGENT_API_KEY`).

**API key.** The only key in the repository is the placeholder `YOUR_API_KEY_HERE`.
Local Ollama ignores it. For a hosted endpoint, set `GEMINI_AGENT_API_KEY` in the
environment. `compare_agent_models.py` also reads `OPENAI_API_KEY` for its `openai`
backend.

**Tools (15):** `describe_inputs`, `list_models`, `run_design`, `screen` (a grid; `vary` grids
any other run_design argument, such as sizes, ATES pairs, stores, return temperatures or
outage start days), `sensitivity`, `stress_test` (re-runs a design with a low reservoir,
+10 % demand, an unplanned doublet stop at the heating peak, one gas boiler unit out, and
the first three at once),
`cross_check`, `get_run`, `compare_runs`, `log_option`, `reservoir_simulation` (Fimbul lookup when available, otherwise
analytic), `write_model` (sandboxed, tested before it is registered), `ask_user`,
`memory_read`, `memory_write`.

**Memory:** a per-question scratchpad, a run ledger (`run_ledger.jsonl` plus
`runs/Rxxxx/`; identical runs are reused) and project notes loaded into every new session.
The default workspace is `agent_workspace/` (git-ignored).

**Comparing backends** on the same cases A1 to A6:

```bash
PYTHONPATH=src python simulator_examples/compare_agent_models.py \
    --backend qwen3-8b=ollama:qwen3:8b --backend gpt-6-luna=codex:gpt-6-luna --repeats 3
```

This writes `results.csv`, `results.json` and `summary.md` to
`simulator_examples/outputs/agent_compare/`.

## Physics gate

Implemented in `src/gemini_agent/physics_gate.py` (gate 1 in `gemini_agent/tools.py`). What
each check catches, and what it does not:

1. **Valid inputs.** Tool arguments must match the schema and allowed ranges (for
   example, at most 3 doublets). Errors go back to the LLM.
2. **Hard rules.** On every day: flow 50 to 300 m3/h per active doublet, brine cooling at
   most 40 K, at most 330 days per doublet, production equals injection, demand met on all
   365 days (the backup boiler and chillers carry the 35-day geothermal outage).
   A failure is a design outcome and is reported.
3. **Energy balance.** Heat, brine, boiler, cooling and electricity balances close to
   0.1 % on every day. Most of these are identities of the dispatcher's own bookkeeping, so
   the gate catches a broken or hand-edited result (and a written model that breaks them), not
   an error in a model's physics.
4. **Second solver.** The peak heating day is rebuilt as a native GEMINI project and
   re-solved by `gemini_simulator.Solver`; the supply and injection temperatures must agree
   within 0.5 K. It checks one day and two temperatures, and it is not run for designs that
   mix doublets at different depths (GEMINI's project schema holds one producer per
   flowsheet).
5. **Sanity bounds.** COPs below their Carnot or reversible limits, temperatures in
   physical order, pump powers consistent with their pressure rise.
6. **No orphan numbers.** Every number in a final answer must match a tool result, a
   cited run, the brief or the user's message. A number with a unit must match a value of
   that quantity (EUR/MWh, t, MWh, ...). A number above 12 with no unit or count after it is
   rejected unless it is a brief or user value as written: a bare number matches one of the
   hundreds of values in a run summary by chance about 43 % of the time, against 0-1 % with a
   unit (`simulator_examples/run_gate6_control.py`; with the bare-number rule, 1 %). Numbers
   with a unit outside those families (m, degC, days) are still matched loosely. Gate 6 checks
   numbers, not the claim around them.

If gates 3 to 5 fail, the run is marked invalid and its numbers cannot be cited. The
benchmark and the live transcripts of 1-4 Nov ran before the bare-number rule (5 Nov).

## Reproducing the report figures and tables

| Report content | Script | Output |
|---|---|---|
| Design screening table and choice of design | `run_design_screening.py` | `outputs/screening.csv` |
| Selected-design year: daily dispatch, KPIs, Solver cross-check | `run_heat_cool_design.py` (edit `DESIGN` for another design) | `outputs/<design>/` |
| Agent transcripts and token tables (appendix) | `run_agent_transcripts.py --backend live` (or `scripted` offline) | `outputs/agent_<label>/` |
| LLM backend comparison | `compare_agent_models.py` | `outputs/agent_compare/` |
| Uncertainty: LCOE ECDF, cost vs CO2, tornados, P(demand met), rank correlation, chiller margin | `run_uncertainty_study.py --samples 400` | `outputs/uncertainty/` (`fig_*.png`, CSVs, `headline.json`) |
| Final pick: 10 gated variants, Monte Carlo and tornado on the pick (report §5.1, Appendix E) | `run_final_pick.py --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt --year 2025 --mc 400` (about 15 min on 4 free cores) | `outputs/final_pick/`; committed copy in `study_results/2026-11-04/margin_pick/final_pick/` |
| Outage schedules, weather years 1991-2025, full screen | `run_outage_study.py`, `run_weather_years.py`, `run_full_screen.py` (each with `--knmi W --year 2025`) | committed copies next to the final pick |
| Reservoir: 30-year temperature decline and pressures (Fimbul.jl) | `run_fimbul_sweep.py`, then `plot_fimbul_results.py` | `src/gemini_design/fimbul/fimbul_table.json`, `outputs/fimbul/` |
| Upstream examples of the Solver/JSON schema | `run_doublet_plant_example.py`, `run_parallel_hex_plant_example.py` (under 1 s each) | printed KPIs |
| Free cooling, gate red team, gate 6 chance control | `run_free_cooling_study.py`, `run_gate_red_team.py`, `run_gate6_control.py` | printed |

`plot_fimbul_results.py` (2 s) works from a fresh clone: it reads the committed runs in
`src/gemini_design/fimbul/cache/` and the committed lookup table `fimbul_table.json`, which
is all the agent and the tests use. `run_fimbul_sweep.py` loads cached cases and runs the
rest in Julia with Fimbul.jl (`GEMINI_JULIA`, `GEMINI_FIMBUL_ENV`). On a fresh clone
without Julia it stops with `Fimbul result not cached and Julia is not available`: the
26 grid and check cases are cached, but the 4 two-doublet schedule cases
(`pick_L*_D*`) are keyed on the current dispatch schedule, which no longer matches the
cached runs.

## Tests and lint

GitHub Actions is turned off on this repository (the workflows in `.github/workflows/`
are manual-only, because Actions never got a runner here). Run the checks locally:

```bash
PYTHONPATH=src python -m pytest unit_test/gemini_model unit_test/gemini_simulator \
    unit_test/gemini_design unit_test/gemini_agent unit_test/gemini_uncertainty -q \
    --ignore unit_test/gemini_agent/test_bench.py
PYTHONPATH=src python -m pytest unit_test/gemini_agent/test_bench.py -q   # slow, see below
flake8 --max-line-length 100 --extend-ignore W503,W504,E127,E128,E203,E402,E722 \
    --extend-exclude simulator_examples/agent_compare_results,simulator_examples/agent_bench_results \
    src/gemini_agent src/gemini_design src/gemini_uncertainty src/gemini_model/chiller \
    src/gemini_simulator simulator_examples unit_test
```

Measured on this branch (4 free cores): **323 tests, all passed**: 306 without
`test_bench.py` in about 3 min, and the 17 in `test_bench.py` in 19 min. `test_bench.py` builds the small benchmark
oracle grids when no cache matches the current code, demand and defaults; that takes up to an
hour on 4 cores the first time and seconds afterwards (caches go to
`simulator_examples/agent_bench_oracle/`; the small-grid caches for this code are committed). flake8 reports **0 findings** with the command
above. The excluded folders hold models the LLM agents wrote during the recorded runs; they
are kept as the agents wrote them. `unit_test/gemini_framework` needs the upstream framework
dependencies and was not run.

## Known limitations

- The design layer is a daily steady-state dispatch, not a transient simulation.
  Reservoir decline over the project life comes from the cached Fimbul.jl lookup.
- Values the brief does not give (network return temperatures, prices, equipment costs,
  HEX size and so on) are assumptions in `gemini_design.challenge.ASSUMPTIONS`. The agent
  states them or asks for them.
- Gate 6 matches numbers, not claims. A sentence can still attribute a correct number to
  the wrong run, so runs are cited for checking. Gates 3 and 4 are consistency checks of the
  dispatcher, not an independent model of the plant (see "Physics gate").
- The design year is 365 days; a leap year's 29 February is dropped when loading demand.
- Small local models sometimes produce malformed tool calls. Gate 1 returns the error and
  the model retries, but larger models are more reliable.
- `write_model` runs generated tests in a separate process with a time limit and an
  import allowlist. This guards against mistakes, not against a hostile user.
- `gemini_uncertainty.tool` defines an `assess_design_uncertainty` tool spec, but it is
  not among the agent's 15 registered tools. Run the uncertainty study with
  `run_uncertainty_study.py`.
- The full screen takes about 4 minutes on 4 cores, and the 400-sample uncertainty study
  takes much longer than the 20-sample run timed above.
- `run_fimbul_sweep.py` needs Julia on a fresh clone (see above).

## Licence

The upstream Apache-2.0 `LICENSE` is kept unchanged and covers this repository. The
upstream code and its attribution belong to the GEMINI authors listed in `pyproject.toml`.

## Author

Sa'eed Telvari
