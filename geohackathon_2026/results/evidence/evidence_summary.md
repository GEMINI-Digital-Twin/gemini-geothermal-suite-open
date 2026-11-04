# Agent evidence

## Final agent with CHP layouts (4 November)

The agent screens 54 designs (1-3 doublets x 3 depths x 6 layouts; deeper depths added if none is eligible), checks the peak point in GEMINI, and runs verify_design. A full design answer costs 55,000-65,000 tokens in 8-9 calls.

| # | Question | What the agent did | Result | Tokens in / out, LLM calls | Log |
|---|---|---|---|---|---|
| 1 | "Design the heating and cooling system for the district. Compare designs and recommend one." | 2 x 3,000 m, CHP on produced gas, absorption chillers: 71.2 EUR/MWh, 5.97 kt CO2, 0.3% bought. Fixed GEMINI flow (326.6 to 297.2 m3/h) and brine cooling (to 39.0 C) | Accepted after one review | 63,708 / 1,481, 9 | `session_20261104_203717.jsonl` |
| 2 | "Could shallower wells of about 2000 m with a heat pump be better than deep wells?" | Compared six layouts; best heat pump design 92.2 EUR/MWh against 71.2 for deep wells with CHP | Accepted after one review | 55,460 / 1,435, 8 | `session_20261104_204026.jsonl` |
| 3 | "The district now has a 50 MW heating peak. Design for that." | Passed 50 MW to every tool, including verify_design; 3 x 3,000 m CHP + absorption, 67.4 EUR/MWh, 8.77 kt | Accepted after one review | 64,208 / 1,494, 9 | `session_20261104_204744.jsonl` |
| 4 | "What is the best pizza place in Padova?" | Declined in one sentence, no tools | Correct | 3,325 / 10, 1 | `session_20261104_205108.jsonl` |
| 5 | "Design it." | Same design as 1 | Accepted after one review | 63,950 / 1,510, 9 | `session_20261104_205110.jsonl` |
| 6 | "Use 5 doublets at 2000 m with 400 m3/h each." | Screened 2000 m only; the tool went deeper because nothing was eligible; stated the 400 m3/h limit; same design as 1 | Accepted after one nudge and one review | 77,224 / 1,848, 11 | `session_20261104_210842.jsonl` |
| 7 | "What heating return temperature should we use?" | Compared 40, 50 and 60 C; chose 40 C, which costs the same as 50 C (the tool recommends 50 C) | Accepted, inconsistent with the tool | 84,066 / 2,018, 12 | `session_20261104_205658.jsonl` |

Fixes made while testing:

| Failure | Log | Fix |
|---|---|---|
| verify_design run at 30 MW while the screen used 50 MW; reviewer missed it | `session_20261104_204324.jsonl` | compare_designs passes the demand with the alternative; a verification at another demand is flagged and not counted |
| Screened only the user's 2000 m, where nothing is eligible; the agent looped | `session_20261104_205344.jsonl` | compare_designs adds deeper depths until a design is eligible, then one step more |
| Announced the next tool in text instead of calling it, using up review rounds | `session_20261104_210228.jsonl` | Up to two "call the next tool" nudges that do not count as reviews |

## Agent with layouts, uncertainty and GEMINI year (3 November)

Workflow: get_requirements, compare_designs (doublets x depths x 4 layouts, 36 designs), simulate_doublet until GEMINI passes, verify_design (return temperature, unplanned failure, uncertainty against the runner-up, every operating day in GEMINI plant files). The reviewer then checks the answer.

| # | Question | What the agent did | Result | Tokens in / out, LLM calls | Log |
|---|---|---|---|---|---|
| 1 | "Design the heating and cooling system for the district. Compare designs and recommend one." | 2 x 3,000 m, boiler + electric chillers, 79.3 EUR/MWh, 6.2 kt CO2. Fixed GEMINI flow 326.6 m3/h and brine cooling 42.9 C (final 297.2 m3/h, 39.0 C). Uncertainty P10-P90 77.1-87.2 EUR/MWh, rule met in 97.5% of samples; 365 GEMINI days, none failing | Accepted after one review | 49,115 / 1,314, 8 | `session_20261103_102657.jsonl` |
| 2 | "Could shallower wells of about 2000 m with a heat pump be better than deep wells?" | Compared all layouts; best heat pump design 2 x 2,500 m at 92.2 EUR/MWh and 8.28 kt against 79.3 EUR/MWh and 6.2 kt for deep wells; recommended deep wells | Accepted after one review | 49,056 / 1,313, 8 | `session_20261103_102302.jsonl` |
| 3 | "What is the best pizza place in Padova?" | Declined in one sentence, no tools | Correct | 3,183 / 10, 1 | `session_20261103_100400.jsonl` |
| 4 | "Design it." | Same as 1 | Accepted after one review | 47,956 / 1,205, 8 | `session_20261103_100408.jsonl` |
| 5 | "Use 5 doublets at 2000 m with 400 m3/h each." | Stated that 5 doublets and 400 m3/h break the limits, designed within them | Accepted after one review | 55,406 / 1,388, 9 | `session_20261103_100742.jsonl` |
| 6 | "The district now has a 50 MW heating peak. Design for that." | Passed heating_peak_mw=50 to every tool; 3 x 3,000 m, boiler + electric, 75.6 EUR/MWh, 9.7 kt CO2 | Accepted after one review | 51,620 / 1,224, 9 | `session_20261103_101216.jsonl` |
| 7 | "What heating return temperature should we use?" | Ran the design at 40 C return. The tool showed 40 and 50 C cost the same; the agent chose 40 C, while the tool's best_return_c is 50 C | Accepted, but inconsistent with the tool's recommendation | 79,836 / 1,558, 12 | `session_20261103_101707.jsonl` |

Token use: a full design answer now costs about 48,000-55,000 tokens in 8-9 calls, against 70,380 tokens for an incomplete answer in the first agent version. Two changes cut tokens: verify_design runs four checks in one call, and compare_designs rows are sent to the LLM as one short line each (4,891 instead of 9,544 characters), while the reviewer keeps the full rows.

Fixes made while testing:

| Failure | Log | Fix |
|---|---|---|
| Used the chosen design as its own uncertainty alternative | `session_20261103_094337.jsonl` | assess_uncertainty rejects an identical alternative; compare_designs returns the runner-up as data |
| Jumped to uncertainty and GEMINI year before checking the doublet | `session_20261103_094858.jsonl` | Four checks bundled in verify_design; numbered workflow a-d |
| 84,846 tokens for one answer | `session_20261103_094337.jsonl` | verify_design and short comparison lines (49,115 tokens after) |
| Ignored the heat pump question and gave the standard answer | `session_20261103_100003.jsonl` | trade_off lists the best design of each layout; prompt asks to answer the specific option first |

## Earlier agent (2 November)

## Final agent (late 2 November)

Same six questions, run with the final tools, workflow and reviewer.

| # | Question | What the agent did | Result | Tokens in / out, LLM calls | Log |
|---|---|---|---|---|---|
| 1 | "What is the best pizza place in Padova?" | Declined in one sentence, no tools | Correct | 2,009 / 20, 1 | `session_20261102_234350.jsonl` |
| 2 | "Design it." | Full workflow; 2 x 3,000 m, 79.4 EUR/MWh, 6.82 kt CO2; fixed GEMINI flow 326.6 m3/h and brine cooling 42.9 C using next_step hints (final 297.2 m3/h, 39.0 C); 50 C return; 15.45 MW backup for a 7-day failure | Accepted first time | 34,391 / 644, 8 | `session_20261102_234356.jsonl` |
| 3 | "What heating return temperature should we use?" | Ran the design and the return comparison; answered 50 C, the highest return with the lowest cost under the 40 C brine cooling limit | Correct, but ran the whole design for a narrow question | 34,431 / 639, 8 | `session_20261102_234442.jsonl` |
| 4 | "Use 5 doublets at 2000 m with 400 m3/h each." | Tools allow 1-3 doublets; reviewer made it state that 400 m3/h breaks the 300 m3/h limit; compare_designs added 3,500 m to bracket the best depth | Accepted after one review | 41,735 / 1,030, 9 | `session_20261102_234532.jsonl` |
| 5 | "The district now has a 50 MW heating peak. Design for that." | Passed heating_peak_mw=50 to every tool; 3 x 3,000 m, 75.8 EUR/MWh, 10.23 kt CO2; 20.91 MW backup for a failure | Accepted first time | 37,051 / 630, 9 | `session_20261102_234721.jsonl` |
| 6 | "Design the heating and cooling system for the district. Compare designs and recommend one." | Same as 2 | Accepted first time | 34,495 / 648, 8 | `session_20261102_234817.jsonl` |

Fixes made while testing the final agent:

| Failure | Log | Fix |
|---|---|---|
| Reported GEMINI flow 326.6 m3/h as within 50-300 and repeated the failing run | `session_20261102_232357.jsonl` | simulate_doublet returns passed and next_step with the exact input to change |
| Copied the answer-format instruction into its answer | `session_20261102_232357.jsonl` | Plain headings, answer only after the numbered workflow |
| Did not tell the user that 400 m3/h breaks the limit | `session_20261102_233043.jsonl` | Reviewer checks requested values against the limits |
| Claimed to have evaluated 3,500 m without running it; reviewer caught it | `session_20261102_233353.jsonl` | compare_designs adds the next depth when the best design is at the edge |
| 50 MW answer used cost and CO2 from a 30 MW run | `session_20261102_233900.jsonl` | Return comparison accepts the demand scenario; reviewer gives the expected numbers |
| Said the chosen design was cheaper than the cheaper ineligible one | `session_20261102_234234.jsonl` | compare_designs returns a computed trade_off sentence |

## Earlier agent

Model: qwen3:8b through Ollama, temperature 0, thinking off. Full logs are in `logs/`.

Some tests ran before later fixes; the "Code at the time" column says which.

| # | Question | What the agent did | Result | Tokens in / out, LLM calls | Log | Code at the time |
|---|---|---|---|---|---|---|
| 1 | "What is the best pizza place in Padova?" | Declined in one sentence, no tools | Correct | 1,186 / 10, 1 | `session_20261102_183417.jsonl` | Before return temperature and demand scenarios |
| 2 | "Design it." | Screened 9 designs, chose 2 x 3,000 m. GEMINI check failed on brine cooling 46.4 C and 43.0 C; it lowered district flow until 37.3 C passed. Reviewer made it add cost and CO2 | Correct | 29,116 / 629, 10 | `session_20261102_183418.jsonl` | Same |
| 3 | "What heating return temperature should we use?" | First version: asked the user instead of using tools. After the prompt change: said it is a design choice with a default of 50 C and offered to compare | Partly correct; it did not compare return temperatures by itself | 1,483 / 46, 1 | `session_20261102_184122.jsonl` | Final |
| 4 | "Use 5 doublets at 2000 m with 400 m3/h each." | Tools rejected 400 m3/h and 5 doublets. It used 250 m3/h after GEMINI gave 320.2 m3/h at a 300 design, moved to 3 doublets, then compared designs. Reviewer made it cost a deeper option; ended at 2 x 3,000 m | Correct; limits enforced by tools | 47,493 / 1,180, 15 | `session_20261102_183655.jsonl` | Before demand scenarios |
| 5 | "The district now has a 50 MW heating peak. Design for that." | First version: claimed a 50 MW design while simulating the 30 MW profile. After the fix, the reviewer caught the unsimulated 50 MW; the agent reran with heating_peak_mw=50 and chose 3 x 3,000 m (75.8 EUR/MWh, 10.23 kt CO2) after fixing two GEMINI violations | Correct after fix | 37,539 / 864, 11 | `session_20261102_184203.jsonl` (fixed), `session_20261102_183851.jsonl` (before) | Final |
| 6 | "Design the heating and cooling system for the district. Compare designs and recommend one." | Chose 2 x 3,000 m. Fixed GEMINI flow 326.6 m3/h, then brine cooling 43.0 C | Correct | 22,693 / 504, 8 | `session_20261102_183141.jsonl` | Before return temperature and demand scenarios |

## Failures found and fixed

| Failure | Where seen | Fix |
|---|---|---|
| Called a tool with 5 doublets despite the 1-3 rule | First tool-calling test | Python input checks in every tool |
| Could not search designs; one run used 70,380 tokens and recommended an ineligible design | `session_20261102_182817.jsonl` | `compare_designs` tool ranks designs in Python; reviewer rejects ineligible picks |
| Stopped after reading the requirements without designing | `session_20261102_182757.jsonl` | Reviewer runs whenever tools were used |
| Claimed a 50 MW design while simulating 30 MW | `session_20261102_183851.jsonl` | Demand scenario inputs, and a reviewer check for unsimulated demand |
| Answers without cost and CO2 | Several | Reviewer requires them |

## Still weak

- It does not compare return temperatures unless asked to run a design.
- Final answers are short on reasoning.
- The reviewer allows at most 3 rounds; after that the answer is marked NOT ACCEPTED.
