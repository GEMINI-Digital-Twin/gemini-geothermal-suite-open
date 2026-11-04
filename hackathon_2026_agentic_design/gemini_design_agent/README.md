# GEMINI Agentic Geothermal Design Agent

Hackathon submission for the **GEMINI Agentic Geothermal Design Hackathon**: an agentic AI
workflow that selects, sizes and validates a deep-geothermal heating and cooling system for the
supplied 2027 daily demand profiles, using the GEMINI geothermal digital twin for the
subsurface / well-engineering evaluation and our own component models for the surface plant.

```
propose design  ->  evaluate with the twin  ->  detect violations  ->  diagnose  ->  repair
       ^                                                                             |
       +------------------------- explore alternatives, refine, rank  <--------------+
                                             |
                       closed-loop geothermal management over the project life
            (reservoir cooling, injectivity decline, ESP wear  ->  controller actions)
```

## What the agent does

1. **Interprets the demand** (365 daily values, heating peak 30 MW on 28 Jan, cooling peak
   10 MW on 19 Jul; 111.7 GWh heat and 23.7 GWh cooling per year).
2. **Starts from a deliberately minimal design** (one doublet at 2,500 m, no heat pump, no
   chiller) and lets the digital twin push back. Every added component is justified by a
   detected violation, and the rationale is logged.
3. **Evaluates each candidate with a full 365-day power / energy balance.** For every day it
   finds the minimum brine flow that meets both loads with the doublets available (one at a
   time can be in its 35-day maintenance window so each doublet runs 330 days), evaluates the
   wells with the GEMINI models at that flow and checks every constraint.
4. **Repairs violations with engineering rules** (add doublet, size heat pump, set ESP deeper
   to stay above the gas bubble point, larger casing for erosional velocity, re-select the ESP
   frame for the VSD window, corrosion mitigation, deepen wells, ...).
5. **Explores structurally different alternatives** (2 or 3 doublets x 2,500 / 3,000 / 3,500 /
   4,000 m x absorption or electric cooling), repairs each, then **trims** capacities to what the
   annual simulation actually used and **ranks** feasible designs by total annual cost
   (tie-break: geothermal share).
6. **Closes the loop over 25 years**: Gringarten-Sauty thermal breakthrough, injector skin
   growth, ESP efficiency loss are fed back into the twin each year; the controller schedules
   acid stimulation, ESP workovers and heat-pump / chiller retrofits and recommends the
   producer-injector spacing.
7. **Writes a report** (`outputs/DESIGN_REPORT.md` + figures + JSON/CSV) that explains every
   major engineering decision and shows the full agent trajectory.

## How GEMINI is used

Directly from `gemini_model` (no Docker / databases needed):

| GEMINI model | Used for |
|---|---|
| `reservoir.reservoir_pressuredrop.bottomhole_skin_dp` | productivity and injectivity index from k, h, re, rw, skin |
| `reservoir.inflow_performance.IPR` | production / injection bottom-hole pressure vs flow |
| `well.pressure_drop.DPDT` (+ `PVTConstantSTP`) | wellbore pressure and temperature, marched in 100 m segments with the geothermal gradient as ambient, for producer (reservoir -> ESP -> wellhead) and injector (wellhead -> reservoir) |
| `pump.esp.ESP` | stage head curve (HC27000 from the GEMINI unit tests, affinity-scaled to the pump frame); stage count and VSD frequency are solved from the required head |
| `corrosion.co2_corrosion.CO2Corrosion` (DLM) | CO2 corrosion rate of tubing at 20 mol% CO2 -> material / inhibitor decision |
| `erosion.erosion_model.ErosionModel` (API RP14E) | erosional velocity vs tubing velocity -> casing ID decision |

Complementary component models (`gemini_design_agent/components.py`): plate heat exchanger,
brine-source high-temperature heat pump (Carnot-fraction COP), single-effect absorption chiller
(COP vs driving temperature), electric chiller, associated-gas handling (GLR 0.8, CH4/CO2) and a
bubble-point estimate used to place the ESP.

Plant topology: brine is split in parallel between the heating train (direct HX, then heat-pump
evaporator) and the cooling train (absorption generator), re-mixed and injected. The split
fraction is optimised daily.

## Key engineering findings

* At the specified 2,500 m the reservoir is 87 C and the wellhead ~85 C: **below the 100 C
  supply**, so heating needs a high-temperature heat pump (COP ~4) and the absorption chiller is
  driving-temperature limited. Deeper wells (3,500 m, ~113 C at the wellhead) allow direct
  heat exchange and full-COP absorption cooling; the agent evaluates both routes.
* The **40 C brine-cooling cap** (not the temperature) sets the extractable heat per doublet:
  ~13.4 MW at 300 m3/h. 30 MW peak heating therefore needs 3 doublets with direct heating or
  2 doublets with a heat pump that adds its compressor work.
* **330 operating days per doublet** makes a single doublet infeasible (35 days without supply);
  outages are staggered into the lowest-load period.
* The ESP must sit deep enough (>= ~800 m) to keep the intake above the ~29 bar bubble point of
  the CH4-rich gas at GLR 0.8 Nm3/m3.
* Un-mitigated CO2 corrosion is >10 mm/yr (de Waard-Milliams): inhibitor + GRE-lined tubing.

## External optimisers and dashboard

`gemini_design_agent/optimize_ext.py` exposes the annual evaluation as a constrained black-box
problem and runs it through petlab's optimiser interface (`py-trsqp` DFTR-Filter, COBYLA) and
StoSAG (robust optimisation over a geological ensemble). `run_optimizers.py <case>` runs one
case, `report_opt.py` re-checks every candidate at full fidelity and writes
`outputs_opt/OPTIMIZATION_REPORT.md`. The three repositories are expected next to this folder
(`../py-trsqp-main`, `../stosag-master`, `../petlab-master`) plus `pip install casadi`.

`make_dashboard_data.py / make_component_data.py` flattens the run outputs into the row files behind the interactive
dashboard (https://claude.ai/artifact/NsWjVJL11z7fZCAK5Fe4my); `outputs_dashboard/index.html`
is the dashboard page.

## Run

```bash
cd gemini_design_agent
pip install -r requirements.txt
python -m gemini_design_agent run \
    --heating ../GEMINI_Heating_Demand_Daily_2027.csv \
    --cooling ../GEMINI_Cooling_Demand_Daily_2027.csv \
    --out outputs --mode rule --years 25
python -m pytest tests -q
```

The GEMINI repository is expected next to this folder as
`../gemini-geothermal-suite-open-main` (the path is added to `sys.path` automatically).

`--mode claude` lets Claude (Anthropic API, `claude-opus-5-5`) drive the same tools and write its
own rationale; set `ANTHROPIC_API_KEY`. `--mode auto` uses Claude when a key is present and the
deterministic rule-based agent otherwise, so results are reproducible offline.

`claude_session.py` is a step-by-step driver for orchestrating the toolbox from a Claude Code
session (no API key): `context`, `build`, `modify`, `suggest`, `rank`, `finalize`. The run in
`outputs_claude/` was produced this way; its `orchestration_log.md` holds Claude's rationale for
every move.

## Layout

```
gemini_design_agent/
  spec.py          fixed hackathon inputs and hard constraints
  demand.py        demand profile loading / statistics
  components.py    heating & cooling component models (ours)
  subsurface.py    GEMINI model wrapper: doublet evaluation at any flow
  system.py        system design, daily dispatch, constraint checks, costing
  agent.py         rule-based and Claude-driven design agents (shared toolbox)
  closed_loop.py   25-year closed-loop geothermal management
  report.py        Markdown report + figures
  cli.py           command line
tests/             unit tests
outputs/           generated report, figures, JSON, CSV
```

## Real-time ESP smart monitoring

`gemini_design_agent/esp_monitoring.py` compares hourly ESP telemetry with the twin and runs a
robust Mahalanobis detector, an Isolation Forest and a CUSUM on hydraulic efficiency; a signature
classifier names the fault and a health index / RUL feed the closed loop. `python run_monitoring.py`
runs the demo, `python report_monitoring.py` writes `outputs_monitoring/ESP_MONITORING_REPORT.md`,
the figure and the dashboard datasets. Tests: `tests/test_monitoring.py`.
