# agentic_design: simulation core for the GEMINI GeoHackathon 2026

A design-evaluation engine for a geothermal district heating and cooling
plant, built on the GEMINI models. An agent can call one function, `evaluate(design)`,
and get back the annual performance, every constraint violation, and an independent
cross-check against the full GEMINI simulator.

## Install and run on a new computer (Windows)

Needs Python 3.12 or newer and Git. The folder only works inside a GEMINI clone: it imports GEMINI's models from
`src/`, plus our two new components in `src/gemini_model/chiller/`.

```
git clone -b development https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open.git gemini
cd gemini
:: unzip the package here, so that agentic_design\ and src\gemini_model\chiller\ land in this folder
tar -xf "%USERPROFILE%\Downloads\agentic_design_v8_2.zip"
python -m venv .venv
.venv\Scripts\activate
pip install -r agentic_design/requirements.txt
python -m pytest agentic_design/tests -q                      :: expect: all passed
python -m agentic_design.run_design --doublets 2 --depth 3000 --ec 10
python -m agentic_design.diagram --doublets 2 --depth 3500 --hp 1 --abs 7.5 --ec 5
```

No `PYTHONPATH` needed; the demand data is in `agentic_design/data/`. Results go to `agentic_design/results/<design>/`.

The agent additionally needs [Ollama](https://ollama.com) and the model (about 5 GB; a GPU makes it fast):

```
ollama pull qwen3:8b
python -m agentic_design.agent --demo
```

## What is in here

| File | Role |
|---|---|
| `config.py` | Challenge inputs (fixed, from the requirements document) and `Assumptions` (everything the challenge leaves open, each with a reason) |
| `wells.py` | Producer + ESP and injector at a set flow, using GEMINI `IPR` and `DPDT` per 100 m segment against the local geotherm |
| `annual.py` | 365-day simulation: per day, an exhaustive search over doublets-on and flow (1 m³/h steps) minimising CO₂; HX uses GEMINI's effectiveness-NTU equation at fixed size |
| `checks.py` | Every challenge constraint (C1–C8) and physical sanity checks (P1–P6), returned as structured findings |
| `plant_json.py` | Builds GEMINI simulator project files for 1–3 doublets, validates them before running, adds two components to the registry |
| `verify.py` | Rebuilds chosen days as full GEMINI projects, runs GEMINI's solver, compares with the fast model |
| `run_design.py` | Command-line entry point / the tool the agent calls |
| `tests/test_core.py` | 18 tests: hand calculations, constraint detection, GEMINI cross-check |

Speed: one full year ≈ 0.05 s per design, so the agent can compare hundreds of designs.

## Plant diagram

`python -m agentic_design.diagram --doublets 2 --depth 3500 --hp 1 --abs 7.5 --ec 5` draws the flowsheet from the
same GEMINI project file the simulator solves (components and connections), as Mermaid (renders on GitHub) and
Graphviz (`.svg`/`.png` if Graphviz is installed). Files go to `results/<design name>/plant_diagram.*`.

## The agent (`agent/`)

```
ollama pull qwen3:8b
python -m agentic_design.agent            # chat
python -m agentic_design.agent --demo     # scripted questions -> agentic_design/transcripts/demo_*.md
```

| File | Role |
|---|---|
| `agent/tools.py` | 10 tools: challenge inputs, demand, assumptions (list/set), model inventory, evaluate design, sweep designs, compare, one day's operation, record decision. Outputs are compact and already in report units |
| `agent/guard.py` | Before a tool runs: argument checks (types, bounds, enums; coerces "1500" -> 1500), provenance (a "user-given" value must appear in what the user wrote; nothing is attributed to the organisers), geometry lock (well diameter and ESP depth stay at defaults unless the user asks or a tool reported low ESP intake). After an answer: unit-aware claim check (every number must trace to a tool result, the fixed challenge facts or the user), per-design check (a number quoted for a design must be in that design's results; component sizes are read from names like `HP12`), component check (a component named for a design must be in it), compliance, ranking ("lowest CO2" must name the design the tools ranked lowest), attribution, unfinished-action, and no-tool-call checks (explanations and design figures need a tool call this turn), field citations (`cooling_unmet_GWh = 0.0` must be that design's value), peak-day dates, and recommending an oversized (P8) design. Two correction rounds, then a visible warning |
| `agent/memory.py` | Long-term memory: designs evaluated, assumption changes, decisions; persisted to JSON and summarised into the system prompt next session |
| `agent/core.py` | Loop: LLM -> tool calls -> guards -> tools -> answer -> claim check; records a transcript with tokens per turn. Token saving: after each turn its tool results are shortened to names, CO2 and constraint status (compare_designs re-fetches numbers when needed) |
| `agent/llm.py` | Ollama backend (qwen3:8b, thinking off: 7/7 tool-calling tasks at 1.6 s/task in our test) and a scripted stand-in for tests |
| `tests/test_agent.py` | Scripted-LLM scenarios plus one regression test per failure seen in the live demos (demos 1-5): invented numbers, organiser attribution, numbers from another design, wrong ranking, unrequested geometry change, explanation without a tool call, components not in the named design |

## Issues found in GEMINI (report these; they are fixed/avoided here)

1. **Injection friction sign.** `DPDT` with `direction="down"` always adds friction. For a producer walked
   top-down this is right; for brine flowing down an injector it is wrong, so `InjectorWell`
   underestimates the required injection pressure by 2 × friction (15.5 bar at 300 m³/h in a 0.2 m well;
   injection pump power about 33% too low at peak). Fix used here: pass a negative flow rate.
2. **Pipe roughness default** in `well_flow._build_dpdt` is 0.01 m (10 mm), about 100× steel casing;
   friction would be overstated several-fold. 0.1 mm used here.
3. **Fluid defaults** are fresh water (1,000 kg/m³, 1.0 mPa·s); the challenge brine is 1,030 kg/m³,
   0.40 mPa·s. Overridden here.
4. **Example ESP curve** cannot deliver the 300 m³/h cap (head goes negative above about 250 m³/h at
   65 Hz). Pump power here follows the challenge rule: Δp × Q / 0.70.
5. **Silent pressure clamp**: `DPDT` floors pressure at 0.001 Pa without warning; detected and reported here.
6. **Bootcamp figure**: reservoir temperature at 2,500 m is 12 + 30 × 2.5 = **87 °C**, not ~75 °C.
7. **Heat exchanger moves heat from cold to hot.** `HeatExchanger._effectiveness_ntu` uses `abs(T_secondary_in - T_primary_in)`,
   so with 47 °C brine and a 55 °C network it cools the brine further (to 45.2 °C) and heats the network (to 63 °C):
   a second-law violation. A real plant bypasses the exchanger; we do the same.
8. **HeatpumpBasic constrained branch returns nonsense.** When the source would fall below `Ts_in_minimum`, the
   fallback optimiser returns COP ≈ 1.0, an outlet of ~780–810 °C and ~45 MW of electricity.
9. **HeatpumpBasic optimiser is fragile.** It solves two equations with an unbounded Nelder-Mead from a fixed start
   (COP 3, Ts_in − 10). A 0.005 % change in an input can flip it into the broken branch of issue 8. Where this happens,
   `verify.py` checks our heat pump directly against GEMINI's two equations and says so in the report.
10. **HeatpumpBasic is not registered in the simulator** (`registry.py`), so project files could not use it; registered here.
12. **Well heat-loss coefficient hard-coded.** `DPDT.calculate_output` sets `Uvalue = 10` W/m²K regardless of the
    parameters, so heat-loss sensitivity was impossible (our U assumption silently did nothing). Fixed in
    `src/gemini_model/well/pressure_drop.py`: optional parameter `heat_transfer_coefficient`, default 10 (unchanged results).
11. **An idle HeatpumpBasic also breaks.** Asked to lift a stream that needs no lift (heat duty about 0), it returns COP 1.0
    and a ~900 °C outlet. Verification now leaves units that do not run on the verified day out of the plant file.

`sweep_designs` right-sizes the best feasible design (each oversized unit cut to its peak use or removed, re-evaluated)
and returns it as `recommended_design` when its CO2 is within 2 %. The checker also flags oversizing (`P8_OVERSIZED`): capital cost is not modelled, so without it the agent can add a 25 MW heat
pump that delivers 0.3 GWh/yr at 3,500 m and still call the design "lowest CO2".

Issues 7–9 have tests in `tests/test_components.py` that assert the faulty behaviour; they will fail once GEMINI is fixed.

## Assumptions (not given by the challenge; all in `config.Assumptions`)

Network return temperature 55 °C · brine cp 4,000 J/kgK · PI from steady radial Darcy (re = 1,000 m,
rw = 0.108 m, skin 0) → 13.3 m³/h/bar · vertical wells, 0.20 m ID · ESP at 650 m · producer wellhead
10 bar (gas kept in solution) · surface Δp 3 bar at design flow · HX sized for 3 °C approach on the peak
day · boiler efficiency 0.90 · associated gas: 80/20 CH₄/CO₂, all combusted (used or flared) ·
electricity 0.30 kg CO₂/kWh · "330 daily steps" read as max 330 operating days per doublet (35-day
maintenance each, placed automatically in the lowest-load window).

## New components (contributed to GEMINI: `src/gemini_model/chiller/`)

| Model | Basis | Notes |
|---|---|---|
| `AbsorptionChiller` | Characteristic equation (Kühn & Ziegler 2005), ΔΔt = t_G − 2.5 t_AC + 1.5 t_E | COP ≈ 0.7–0.75; with 20 °C chilled water it runs on ~60 °C drive water |
| `ElectricChiller` | Carnot fraction (η = 0.45), like GEMINI's heat pump | COP 7.3 at 20 °C supply vs 4.0 at 7 °C |
| Heat pump (annual model) | GEMINI `HeatpumpBasic` Lorenz equations, solved by fixed-point iteration | Verified against GEMINI's class (COP identical to 4 digits) |

The daily dispatch chooses, per day, the brine order (absorption first or heating first) and the absorption
load share (0, 50, 100 %), within the 40 °C brine-cooling cap shared by absorption, heat exchanger and heat pump.

## Design choice with costs and gas handling (3 Nov)

`economics.py` adds investment and yearly cost (ThermoGIS well and plant costs, Eurostat 2025 energy prices,
EU ETS price, N-1 backup boilers, gas reinjection) and `studies.py` runs the 216-design sweep and sensitivities.
Associated gas (80 % CH4, 20 % CO2) can be burned with the surplus flared, or burned only when the boilers need it with
the rest compressed and reinjected (`_RI`). Selection: lowest cost per MWh with CO2 valued at 450 EUR/t (EIB shadow
cost of carbon, plant-life average); within 1 % the simplest, then lowest CO2. Result: **2x3500m_ABS5_EC5_RI**
(2.37 kt CO2/yr, 99.5 % geothermal heating, 55.6 MEUR, 62.9 EUR/MWh). Without a CO2 value a single doublet is
cheapest (11 kt CO2); the reinjecting design beats the cheapest gas-burning two-doublet plant above about 284 EUR/t.

## Results (heating and cooling, all designs below meet every constraint)

| Design | Geothermal share | Purchased gas | Electricity | CO₂ base | CO₂ grid 0.10 kg/kWh |
|---|---|---|---|---|---|
| 2 × 2,500 m + electric chiller 10 MW | 64% | 25.7 GWh | 8.4 GWh | 12.1 kt | 10.3 kt |
| 2 × 2,500 m + heat pump 12 MW + electric chiller 10 MW | 83% | 0.1 GWh | 14.4 GWh | 7.6 kt | 4.7 kt |
| 2 × 3,000 m + electric chiller 10 MW | 89% | 0 | 7.3 GWh | 5.8 kt | 4.3 kt |
| 3 × 3,000 m + absorption 6 MW + electric chiller 10 MW | 88% | 0 | 6.0 GWh | 5.4 kt | 4.2 kt |

Findings: deeper wells beat the heat pump on CO₂ in every sensitivity case, but costs (drilling) are not modelled;
heat pumps above ~12 MW add nothing (limited by the 40 °C brine cap); absorption only helps when the brine budget
is not already used by heating; the associated gas (burned whether used or flared) sets a CO₂ floor of ~4–5 kt/yr.

## Earlier results (heating only, before cooling models)

| Design | Geothermal share | Purchased gas | CO₂ |
|---|---|---|---|
| 1 doublet, 2,500 m | 45% | 50.7 GWh | 15.1 kt |
| 2 doublets, 2,500 m | 64% | 25.7 GWh | 11.0 kt |
| 3 doublets, 2,500 m | 63% | 25.5 GWh | 10.9 kt |
| 2 doublets, 3,000 m | 89% | 0.03 GWh | 4.6 kt |

At 2,500 m the limit is temperature, not flow: 85 °C brine can only lift a 55 °C network to about 82 °C,
so a third doublet adds nothing. Going to 3,000 m (102 °C) or adding a heat pump changes the picture.
