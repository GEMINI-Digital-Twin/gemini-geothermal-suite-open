# Stated-objective agent runs on the new defaults (max reasoning)

Scenario `10_design_with_objective`, measured KNMI weather (Schiphol, 2025), code at
`origin/development` 5cebfa1 (after PR #30 and #31). Settings: reasoning effort `max`,
`max_tokens` and step limit at the defaults, `GEMINI_AGENT_SCREEN_WORKERS=2`,
`OPENBLAS_NUM_THREADS=1`. CO2 priced at 180 EUR/t (80 + the client's 100) in every run.

| run | model | pick | LCOE EUR/MWh | CO2 t/yr | trip-at-peak test on pick | LLM / tool calls | gate rejections | reasoning tok | cost | wall |
|---|---|---|---|---|---|---|---|---|---|---|
| r1 | DeepSeek V4.1 Flash | R0418: 2 x 3000 m, gas boiler 15 MW (3 units), CHP 1 MWe, 10 MW screw dry-cooler + free cooling, cooling return 30 °C | 38.71 | 4872 | yes, R0488: 0 unmet (42.43 in that year) | 87 / 133 | 1 | 87,610 | USD 0.093 | 44 min |
| r2 | DeepSeek V4.1 Flash | R0368: 2 x 2850 m, gas boiler 16 MW (2 units), 10 MW screw dry-cooler + free cooling, cooling return 30 °C, operating rules | 39.71 | 5174 | yes, R0405: 0 unmet (43.20) | 55 / 95 | 0 | 41,151 | USD 0.038 | 51 min |
| r3 | DeepSeek V4.1 Flash | R0118: 2 x 2900 m, gas boiler 30 MW (2 units), 10 MW screw dry-cooler, cooling return 28 °C, operating rules | 41.68 | 5526 | yes, R0127: 0 unmet (45.18) | 30 / 59 | 2 | 15,789 | USD 0.019 | 20 min |
| sol_r1 | GPT-6.1 Sol (Codex) | no final answer: ended with a question (grid capacity for a 30 MW electric boiler). Candidates R0564 (electric boiler 30 MW) and R0514 (gas boiler 30 MW), both 2 x 3075 m, CHP 0.85 MWe, ORC 0.05 MWe, ESP 220 m3/h VSD, returns 45/30 °C | 37.51 / 37.56 | 4366 / 4409 | no (only on early run R0018) | 13 / 37 | 0 | 23,809 | ChatGPT plan: 643,781 in (219,520 cached), 27,890 out | 80 min |

LCOE and CO2 are for the normal year (each doublet stops in its own lowest-load window).
The coldest-day trip is a separate run and is not in that basis. No LLM call was
truncated in any run.

Note: r1's answer states "18 MW boiler" and "2 MWe CHP" for R0418; the ledger shows
15 MW and 1 MWe. Its R0413 is 14 MW, not the stated 15 MW.

Logs: the r1-r3 console logs were not saved (wrong log path in the wrapper script); the
transcripts hold the full record. `logs/` has the wrapper output and the Sol console log.
The per-run `runs/` folders (daily CSV files) are not copied.
