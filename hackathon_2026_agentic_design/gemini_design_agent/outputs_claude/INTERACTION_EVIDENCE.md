# Agent interaction evidence

The committee asked for evidence that the agent can reason about a request: identify missing inputs, refuse what is out of scope, and flag inconsistencies. These six exchanges are produced by the agent's intake gate (`gemini_design_agent/intake.py`), which runs before any simulation in both orchestration modes. They are deterministic, so anyone can rerun `python demo_interactions.py` and get the same answers.

## 1. Complete request (the challenge as issued)

> **User:** Design a geothermal heating and cooling system for the district with the attached demand files.

**Agent status: ok**

Inputs are complete and consistent. Starting the propose - evaluate - diagnose - repair loop.

Assumptions I will use unless you object:
- max_flow_m3_h_per_doublet: defaults to the challenge cap of 300 m3/h
- max_brine_cooling_c: defaults to the challenge cap of 40 C
- operating_days_per_doublet: defaults to 330
- district_return_c: defaults to 60 C
- electricity_price_eur_mwh: defaults to the indicative cost model
- wellhead brine at 2500 m (~84 C) is below the 100 C supply + 3 C approach: direct heat exchange is impossible there, so I will size a heat pump and also test deeper wells (the brief allows other depths with hydrostatic pressure and the given gradient)
- GLR 0.8 Nm3/m3 implies a bubble point of roughly 29 bar; the ESP intake will be kept above it


## 2. Incomplete request: heating file only, no supply temperatures

> **User:** Here is the heating demand. Design the geothermal system.

**Agent status: incomplete**

I can start the design loop once the inputs below are supplied. Without the cooling profile I cannot size the chiller train or the brine split, and without supply temperatures I cannot decide whether direct heat exchange is possible or a heat pump is needed.

Missing inputs I need before I can size anything:
- cooling_demand_csv: daily cooling demand profile (date, MWcool)
- supply_temperature_heating_c: supply temperature to the heating network
- supply_temperature_cooling_c: supply temperature to the cooling network

Assumptions I will use unless you object:
- max_flow_m3_h_per_doublet: defaults to the challenge cap of 300 m3/h
- max_brine_cooling_c: defaults to the challenge cap of 40 C
- operating_days_per_doublet: defaults to 330
- district_return_c: defaults to 60 C
- electricity_price_eur_mwh: defaults to the indicative cost model

Questions back to you:
- Shall I proceed with the heating side only and report cooling as 'not sized'?


## 3. Irrelevant request

> **User:** Design a 50 MWe geothermal power plant with an ORC turbine for the same reservoir.

**Agent status: out_of_scope**

I cannot help with that request: electricity generation: this agent designs direct-use heating and cooling systems only. I design and validate deep-geothermal heating and cooling systems for a district using the GEMINI digital twin. If you have a heating and cooling demand profile and reservoir data, send those and I will start.


## 4. Off-topic question

> **User:** Which stock should I buy this week?

**Agent status: out_of_scope**

I cannot help with that request: not an engineering design question. I design and validate deep-geothermal heating and cooling systems for a district using the GEMINI digital twin. If you have a heating and cooling demand profile and reservoir data, send those and I will start.


## 5. Inconsistent inputs: a 140 C reservoir at 2,500 m with a 30 C/km gradient

> **User:** The reservoir at 2,500 m is 140 C. Design the system.

**Agent status: inconsistent**

I found inputs that contradict each other. I will not size the plant until they are resolved, because the design flips between a heat-pump and a direct-supply system depending on the answer.

Inconsistencies I found:
- stated reservoir temperature 140 C does not match 30 C/km x 2500 m + 12 C surface = 87 C; one of them is wrong

Assumptions I will use unless you object:
- max_flow_m3_h_per_doublet: defaults to the challenge cap of 300 m3/h
- max_brine_cooling_c: defaults to the challenge cap of 40 C
- operating_days_per_doublet: defaults to 330
- district_return_c: defaults to 60 C
- electricity_price_eur_mwh: defaults to the indicative cost model
- wellhead brine at 2500 m (~84 C) is below the 100 C supply + 3 C approach: direct heat exchange is impossible there, so I will size a heat pump and also test deeper wells (the brief allows other depths with hydrostatic pressure and the given gradient)
- GLR 0.8 Nm3/m3 implies a bubble point of roughly 29 bar; the ESP intake will be kept above it

Questions back to you:
- Which should I trust: the temperature log or the gradient? This decides whether a heat pump is needed.


## 6. Request with a wrong file path

> **User:** Design the system; cooling demand is in cooling_2027.csv.

**Agent status: incomplete**

I can start the design loop once the inputs below are supplied. Without the cooling profile I cannot size the chiller train or the brine split, and without supply temperatures I cannot decide whether direct heat exchange is possible or a heat pump is needed.

Missing inputs I need before I can size anything:
- cooling_demand_csv: file 'cooling_2027.csv' not found

Assumptions I will use unless you object:
- max_flow_m3_h_per_doublet: defaults to the challenge cap of 300 m3/h
- max_brine_cooling_c: defaults to the challenge cap of 40 C
- operating_days_per_doublet: defaults to 330
- district_return_c: defaults to 60 C
- electricity_price_eur_mwh: defaults to the indicative cost model

Questions back to you:
- Shall I proceed with the heating side only and report cooling as 'not sized'?


## 7. Reasoning transcript of the Claude-orchestrated design run

`outputs_claude/orchestration_log.md` holds the eight design moves Claude made, each with its stated hypothesis before the simulation and the twin's verdict after it (for example: 'two doublets at 3,500 m with a 15 MW heat pump' was proposed, failed on 16 peak days, and the log explains why the heat pump cannot help once the brine is at the 40 C cap). The rule-based run's equivalent is `outputs/agent_log.txt` (16 archetypes, 38 steps).

## 8. Number of used tokens

LLM: Claude Fable 5.1 (Anthropic, commercial), orchestrating from Claude Code through `claude_session.py`. 8 decision turns, 770 output tokens, 31,848 input tokens read across the turns, about 32,618 tokens in total. This is an estimate at 4 characters per token over the logged text, because the Claude Code session does not expose API usage; it is written to `outputs_claude/llm_usage.json`. Each twin answer is a compact JSON summary (feasibility, violations, 12 KPIs, cost), not the 365-day table, which is what keeps the run this small.

| Turn | Claude's move | Claude output (tokens) | Twin answer (tokens) | Context read (tokens) |
|---|---|---|---|---|
| 1 | build base-2dbl-2500m-abs | 70 | 638 | 1500 |
| 2 | build deep-3dbl-3500m-abs | 72 | 648 | 2208 |
| 3 | build mid-3dbl-3000m-abs | 44 | 643 | 2929 |
| 4 | build deeper-3dbl-4000m-abs | 46 | 642 | 3616 |
| 5 | modify two-2dbl-3500m-abs-hp15 | 54 | 720 | 4304 |
| 6 | modify deep-3dbl-3500m-electric | 36 | 649 | 5077 |
| 7 | modify final-3dbl-3500m-abs-trim | 96 | 594 | 5762 |
| 8 | finalize final-3dbl-3500m-abs-trim | 352 | 15 | 6452 |
| | **total** | **770** | **4549** | **31848** |

- API mode (`python -m gemini_design_agent.cli --mode claude` with `ANTHROPIC_API_KEY` set) meters `response.usage` on every turn, logs `[tokens] turn n: in/out`, and writes the exact totals to `<out>/llm_usage.json`.
- Rule-based run (`--mode rule`): zero LLM tokens; 38 twin evaluations, ~5 minutes; fully reproducible offline. Its `llm_usage.json` records that.
- Design-space screening for the optimisers used a fast evaluator (every 2nd/3rd day) with a cache keyed on the design signature, which cut the optimiser study from an estimated 6 hours to about 50 minutes; no LLM tokens.