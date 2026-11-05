# Open design with the objective stated, with ORC power and the pit store (3 Nov 2026)

Author: Sa'eed Telvari

The same scenario as `../2026-11-03-objective` (`10_design_with_objective`, KNMI Schiphol
2025, 30-step limit, 2 screen workers), rerun after the ORC power option was added
(`orc_capacity_mw_el` in run_design and screen, listed neutrally in list_models, prompt
unchanged). DeepSeek V4.1 Flash x3 (OpenRouter) and GPT-6.1 Sol x1 (Codex CLI, ChatGPT plan).

**Code:** plain `origin/development` at c22747b (merge of PR #24, which follows PR #21 and
PR #23), so the pit store is also present. The ORC tests passed (14). Standard
`run_agent_transcripts.py` with the same flags as PR #21, with no hint about ORC or storage.
Sol did not ask about the weather. `logs/` holds the console log of each run.

## Results (all costs with CO2 at 180 EUR/t)

| run | outcome | LLM / tool calls | gate rejections | pick | LCOE | t CO2/yr | ORC use | pit store use |
|---|---|---|---|---|---|---|---|---|
| r1 | answer | 22 / 36 | 1 | 1 doublet, 3.0 km, boiler, CHP, screw chiller + free cooling, 250,000 m3 pit store at 25 MW (R0111), priced with a common stop from day 28 | 49.15 | 9,701 | screens with 0, 1 and 2 MWe. Verdict: "ORC on the brine ... cost more than they save" | 9 runs, 150,000-400,000 m3. Picked |
| r2 | answer (text cut off) | 26 / 30 | 0 | 2 doublets, 3.0 km, boiler, CHP, wet-tower chiller (R0140), priced with a common stop from day 28 | 50.67 | 8,539 | screens with 0 and 1 MWe. Not used | 1 run, 100,000 m3 |
| r3 | answer (text cut off) | 20 / 52 | 0 | 2 doublets, 3.0 km, boiler, CHP, wet-tower chiller, operating rules on (R0082), no stop in the headline | 38.38 | 4,479 | screens with 0, 1 and 2 MWe. Not used | 1 run, 100,000 m3 |
| Sol | answer | 18 / 50 | 1 | 1 doublet, 3.0 km, boiler, CHP, screw chiller, **0.1 MWe ORC**, operating rules on (R0152), priced with a common stop from day 1 | 47.17 | 11,770 | 18 runs, 0-0.5 MWe. Picked 0.1 MWe | 1 run, 100,000 m3 |

No run wrote its own model (no `write_model` call).

Gate rejections: r1 used four numbers that matched no result of the same quantity
(1.27 EUR/MWh, 0.172 and 0.209 MEUR, 0.3 K). Sol used the number 180, which is in no
tool result. Both rewrote the answer and passed.

## How the agents judged the ORC

- **DeepSeek rejects it.** In DeepSeek's runs, 1 MWe of ORC adds about 2.05 EUR/MWh (2 MWe:
  4.1) and often changes CO2 by 0 t. In those runs the ORC produced 0 MWh: its capex
  (3 MEUR per MWe) is counted, but it gets no brine above what the district heating takes.
  In other runs it did produce power (up to 5.8 GWh_e/yr in r2), but it never paid back.
- **Sol keeps a very small one.** On Sol's basis (1 doublet, both wells down from day 1), a
  0.1-0.25 MWe ORC runs on spare summer brine (for example 0.25 MWe: 19.5 GWh of heat in,
  0.93 GWh_e out, about 4.8 %) and lowers the LCOE by 0.18 EUR/MWh. 0.5 MWe already costs
  more. Its pick has 0.1 MWe.
- **Conclusion:** at 102 degC brine, the ORC is worth at most a few tenths of a EUR/MWh,
  and only for a 1-doublet plant with summer spare capacity. The agents found and tested it
  without a hint, and judged it consistently with the numbers.

## Issues found

1. **The final answers of r2 and r3 are cut off.** Both hit the 1,200-token output limit
   (`truncated: true` in the transcript): r2 stops in a table cell, r3 in a sentence. The
   pick and run id are in the first lines, so the result is clear, but the gate accepted a
   truncated answer. A truncated final answer must be retried or rejected.
2. **`geothermal_share_of_heat` exceeds 100 % in ORC designs** (up to 192 % in r2, 142 %
   in r3; DeepSeek r3 called it "an odd metric" in its reasoning). The ORC heat seems to
   be counted in the geothermal heat but not in the delivered heat. The ORC KPIs need a
   check.
3. **The ORC produces 0 MWh in many designs** (for example 2 doublets at 3.0 km), but its
   capex is charged. That can be correct (no brine is left above the district-heating
   need), but the agents get no message that the ORC never ran.
4. **The cost basis varies between runs again.** Three of four runs priced a common winter
   stop into the headline (r1, r2, Sol), and r3 did not. Thus r3's 38.38 is not comparable
   with the others. r1 also chose the pit store because "at your CO2 price the store is the
   better trade", but CO2 at 180 EUR/t is already in the LCOE, and the store design has the
   higher LCOE (49.15 against 47.88). The gate does not check this reasoning.

## Reasoning settings used

These runs predate the change to run every model at its highest reasoning setting.

- **DeepSeek V4.1 Flash (OpenRouter):** the runner sent no reasoning or effort parameter. The
  request had only `temperature: 0.1` and `max_tokens: 1200` (`reasoning_model: false`), so
  OpenRouter's default for the model applied. Reasoning tokens: r1 11,034 of 18,380
  completion tokens, r2 18,088 of 21,957, r3 11,688 of 18,497. These reasoning tokens count
  against the 1,200-token limit. Truncated LLM calls: r1 2, r2 8, r3 1. This is the likely
  cause of the cut-off final answers of r2 and r3. With a higher reasoning setting,
  `max_tokens` must be raised, or more answers will be cut off.
- **GPT-6.1 Sol (Codex CLI 0.166.0):** the runner passed no effort flag to `codex exec`, so
  the CLI used `model_reasoning_effort = "high"` from `~/.codex/config.toml` on this PC
  (unchanged since 30 Oct). Reasoning tokens: 5,747 of 9,969 completion tokens.
