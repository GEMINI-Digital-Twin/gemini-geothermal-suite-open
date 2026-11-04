# Decisions log

Minor decisions taken without asking, per the instruction of 2026-11-04 ("decide minor things yourself and
log them"). Major decisions (ranking rule, tolerances, physical inputs) stay in `CLAUDE.md` and were made by
the user. Newest first.

## 2026-11-04

| # | Decision | Why | Where |
|---|---|---|---|
| 1 | Option (c) compression set to the DERIVED 0.197 kWh/kg; (b) kept at the ASSUMED 0.1 kWh/kg CO₂. | User decision. Recorded here only to note the scope: the 0.197 value is the minimum at n2 / 3 500 m (61.5 bar(g) bubble point) and is applied as a constant to every depth (3 250 m would give 0.195). | `projects/candidates_2027.json` |
| 2 | Re-ran the agent (fresh cache) and the sensitivity study after the change; did not re-run the C1–C3 comparison. | Every agent run and every sensitivity case evaluates option (c). C1–C3 use CHP, so their results cannot change. | `outputs/agent/`, `outputs/sensitivity/` |
| 3 | Read "C (dashboard upgrades)" and "D (final consistency pass)" as: C = make the dashboard show this round's results correctly; D = check that code, docs, provenance and outputs agree. | Neither item is defined anywhere in the repo or in the session. Following the instruction not to stop, I chose the narrowest reading that fits the names. | this file |
| 4 | Panel 5 (depth ladder) redrawn as one segment per step, coloured kept / marginal / rejected, with a dotted connector where a gas-handling option is accepted at a depth and the ladder re-opens; step labels to 1 decimal. | The old chart joined 3 250 m CHP (5 148 t) to 3 500 m CO₂ reinjection (3 983 t) and labelled the line −6.3%, but −6.3% is measured from 3 250 m with CO₂ reinjection (4 252 t). It also printed −0.829 % next to one-decimal labels. | `make_dashboard.py` (`renderAgent`) |
| 5 | Panel 8 (hard constraints) gains a "Reinjected gas dissolves" row from the `gas_dissolution` check. | The check is a hard annual check since 2026-11-03, but the panel listed only the original ten. | `make_dashboard.py` (`constraints`) |
| 6 | `sensitivity.py` records, for each case, the agent's verdict on the base pick (`base_pick_verdict`), and `sensitivity.md` lists it for the cases where the pick changes. Panel 10 states the reason in words. | Shows why each pick changes (depth threshold, extra doublet, ladder path) rather than only that it changes. | `sensitivity.py`, `make_dashboard.py` (`renderTornado`) |
| 7 | Panel 11 made taller (470 → 530) so the note under the gas table is not clipped in the PNG. | The 300 dpi export cut off the note's last line. | `make_dashboard.py` |
| 8 | Kept the README's original starter text and added a short "Current state" block at the top. | The README is the organizer's starter note. Rewriting it would lose that, but on its own it describes only the first step. | `README.md` |
| 9 | Compared `src/`, `simulator_examples/` and `unit_test/` against `development`, not `main`. | The branch is based on `development`, which already differs from `main` in those folders. Against `development` they are unchanged. | git |
| 10 | Added a provenance entry for the `sensitivities` settings block (HP η 0.5, no COP cap: an ASSUMED what-if for the C1–C3 comparison). | It was the only settings block with no provenance entry. | `projects/candidates_2027.json` |
| 11 | Left the `interactive` and `claude_cli` agent outputs as they are (not re-run). | They show the human-in-the-loop and LLM-backend runs at an earlier model state. Re-running claude_cli needs paid API calls, and the dashboard and STRONG_POINTS already say they predate gas handling. | `outputs/agent/interactive/`, `outputs/agent/claude_cli/` |
| 12 | Panel 10 prints near-zero deltas as "0 t" (was "−0 t") and adds a sentence for any input with no effect. CLAUDE.md records why HP η has no effect: at 3 500 m the heat pump runs at the COP 6 cap on all 145 days it operates. | A reader would otherwise take the empty bars for a bug. | `make_dashboard.py`, `CLAUDE.md` |
| 13 | Stopped the first post-change sensitivity run partway through and restarted it with the new `base_pick_verdict` field. The restart reused cached annual evaluations that the stopped run had already computed with the same settings. | Same inputs, same cache key, so the results are identical. It saved about a minute. | `outputs/sensitivity/` |
| 14 | Re-ran the agent once more after adding the `sensitivities` provenance entry (#10). | The settings file is part of the evaluation cache key, so the committed outputs now match the committed settings exactly. The pick and all numbers are unchanged. | `outputs/agent/` |
