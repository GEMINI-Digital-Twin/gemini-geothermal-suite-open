---
name: reporting-and-evidence
description: How to write the final design answer - structure, citations of fact IDs, assumptions, verification. Read before writing the final recommendation.
---
# Final answer format

1. **Recommended system** - one line (doublets, depth, flow, heat pump, chillers, boiler, gas handling).
2. **Why** - 3-5 bullets comparing against the main alternatives (deeper wells vs heat pump, absorption vs electric cooling, gas burned vs reinjected), each with numbers and [F#].
3. **Performance** - demand met (days), geothermal share, LCOE, CO2, CAPEX, max brine cooling, operating days [F#].
4. **Robustness** - N-1 peak-day test, demand growth, Monte Carlo P10/P50/P90 [F#].
5. **Assumptions** - inputs not in the brief and the values used.
6. **Verification** - constraint checks passed; numbers checked with `check_numbers`.
Rules: every number carries a fact ID; never round a number into something different; if a number is not in a tool result, do not write it.
