# Agent backend comparison

| backend | runs | gated answers | behaviour ok | A1 design match | gate rejections (fixed) | invalid tool calls | prompt tok | completion tok | wall s | cost USD |
|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 1 | 0 | 0 | 0/1 | 0 (0) | 1 | 169766 | 6874 | 547 | 0.004 |

Per case (mean over repeats):

| backend | case | behaviour ok | prompt tok | completion tok | tool calls | wall s |
|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | A1 | 0/1 | 169766 | 6874 | 27.0 | 547 |

## Physics gate on the agents' simulation runs

Gate passed = integrity verdict (energy balance and sanity). A design that fails a hard rule (for example cooling demand not met) is still a valid run, but it cannot be recommended.

| backend | runs in ledger | gate passed | gate failed | meets all hard rules | solver re-run agrees | steps not passed |
|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 84 | 84 | 0 | 72 | 82 | 2_hard_rules x10 |

## A1 design found (reference: 2D-3100m-boiler-electric-chp, 36.88 EUR/MWh)

| backend | repeat | final reply | asked first | design | LCOE EUR/MWh | matches reference | tool calls | wall s |
|---|---|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 1 | failed | no | - | - | no | 27 | 546.8 |

## Failed behaviour checks

| backend | case | repeat | failure |
|---|---|---|---|
| deepseek-v4.1-flash | A1 | 1 | first reply should be a question, was failed; final reply should be an answer, was failed |

Cases: A1 = 01_design_brief_incomplete, A2 = 03_incomplete_whatif, A3 = 02_offtopic_weather, A4 = 04_hallucination_caught, A5 = 06_write_missing_model, A6 = 05_uncertainty_permeability.
