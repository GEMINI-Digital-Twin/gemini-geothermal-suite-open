# Task: what geomind needs from gemini, part A (runs beside the redesign)

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- geomind (the agent package) sent a list of gemini names it needs that are missing or still raise `NotImplementedYet`. This prompt builds the ones that do **not** touch the Module/Plant code. Another session is running the Module/Plant redesign (`prompts/gemini-module-plant-redesign.md`) on branch `refactor` in `gemini/` at the same time. Part B (after the redesign) builds the rest.
- **Work in a separate worktree, never in `gemini/`:**
  ```bash
  cd /Users/sahand/Desktop/crust-team/gemini
  git worktree add ../gemini-gaps -b gaps refactor
  cd ../gemini-gaps
  ```
  Work only in `/Users/sahand/Desktop/crust-team/gemini-gaps`. Never run git commands that change `gemini/` or branch `refactor` (no checkout, reset, rebase, stash or commit there).
- **Imports:** check that `python -c "import gemini; print(gemini.__file__)"` run from the worktree points into `gemini-gaps/`. If it points into `gemini/` (editable install), make a venv in the worktree (`.venv`, git-ignored) with `pip install -e ".[dev]"` and use it for every command.
- **Stay out of the redesign's files.** Do not change `gemini/modules/`, `gemini/engine/` (except what section 3 names), `gemini/graph/`, `gemini/backends/`, `gemini/checks/limits.py` or the plant dict code. If a section needs one of them, stop that section and say so in the report; it goes to part B.
- **Version:** do not change it. Add change-log lines under "unreleased changes" in `api.md`.
- **Git:** branch `gaps`, one commit per section below, in order. **Do not push and do not merge.** Part B merges `gaps` into `refactor` after the redesign.
- **Load:** the redesign session runs tests at the same time. If a 1 s budget test fails, rerun it alone before treating it as a failure, and say which tests you retimed.
- **Scope:** change only `gemini-gaps/`. You may read `geomind/` and `backend/`, never change them.
- **Temporary files** go to `.tmp/gaps/` (git-ignored).
- **Agents:** one agent is enough. Subagents, if any, run on a lighter model and only do read-only searches.
- **Tests:**
  - Use the development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), run in parallel, under 300 s.
  - New tests go in the fast tier, reuse the session fixtures and the short-window data, and each stays under about 1 s.
  - Existing numbers stay identical. Never run the slow dataset locally. Never delete or shrink goldens or `inputs/` data.
- **Quality bar** as in `.claude/docs/conventions.md`:
  - simple, readable, just enough code;
  - nesting at most 3, functions about 40 lines at most, guard clauses;
  - explicit `gm.errors` with codes;
  - no comments inside code (docstrings only; the fixed section headers stay);
  - black, isort and flake8 clean;
  - write a failing test before each bug fix.
- Every result is one of the three shapes in the docs (value `{value, unit}`, problem, check). If something else is needed, say so in the report.

## 1. `operating_days` in `gm.schedule`

Today `rules["operating_days"]` raises `NotImplementedYet` (`gemini/analysis/schedule.py`). The organisers say each doublet runs 330 daily steps. Decided meaning:

- `rules["operating_days"]` is `None` (every doublet every day, as today), an `int`, or a list of dates.
- **An `int` `n`:** each doublet runs exactly `n` days of the demand. Its outage days are the days of lowest total demand (heating plus cooling, in W). Outages are spread over the doublets: the first doublet (plant order) takes the lowest-demand days, the next doublet the lowest-demand days not already taken, and so on, so at most one doublet is off on a day. If the doublets need more outage days than the demand has, raise `ValidationError` (code `invalid_value`) saying so.
- **A list of dates:** every doublet is off on those dates (UTC days of the demand index). A date outside the demand raises `ValidationError` with the date.
- **On an outage day** a doublet's `flow` is zero and `is_running` is false. Its heat goes to the next sources in `rules["order"]`. A heat pump whose source is only that doublet's brine also stops that day (follow the plant's wiring). Unmet demand is no error, as today.
- A fixed count of 330 on a 365-day demand gives 35 outage days per doublet. Give the number of days off as `outage_days` in `attrs` of the plan (`{doublet path: [dates]}`), so geomind can show it.
- Update the docstring of `schedule` (remove the `NotImplementedYet` sentence) and the rule list in the docs.

**A check that counts the days:**
- Add `gm.checks.operating_days(plant, results, days)`: for each doublet, a check `{name, passed, value, limit}` with the number of days it ran (`value`, unit `day`) against `days` (`limit`). Choose the column it reads (the doublet's `operating` column or its flow) and say which. A doublet runs on a day when it carried flow on that day.
- Add it to `gm.checks.run_all` (or the suite) if that is how checks are grouped today.
- **Tests:** two doublets with 330 days on a short demand window scaled to the rule (choose a small window and an `int` that fits it); the list-of-dates form; too many outage days; and the check on a finished run.

## 2. Annualised cost and LCTS

The team's design metric is LCTS: annualised total system cost over the annual heat plus annual cold.

- Add `gm.economics.annualised_cost(plant, results, discount_rate=None, lifetime=None, assumptions=None, on_error="raise")`: `capex / A + opex` per year, with `A` the same annuity factor `lcoh` uses (`economics/levelised.py`, `annuity`). Return a value in `currency/year` with parts `capex`, `opex`, `annuity_factor`, `discount_rate`, `lifetime_years`.
- Add `gm.economics.lcts(plant, results, ...)` with the same arguments: `annualised_cost / (annual heat + annual cold)` in `currency/J`, parts `annualised_cost`, `heat`, `cold` (each `J/year`). It needs no `heat_cost_share`. No delivered energy gives no value with a reason, as `lcoh` does.
- Reuse `annual_energies`, `capex`, `opex` and `discounting`. Do not duplicate the formula: make `lcoh` / `lcoc` use `annualised_cost` if that keeps their numbers identical.
- **Tests:** `lcts` equals `lcoh.value * lcoh.energy / (heat + cold)` with `heat_cost_share = 1` on a plant that delivers both; no energy; no capex.

## 3. A volume flow in `gm.evaluate`

geomind passed `{"m_dot": "150 m3/h"}` and got "expected a unit of 'kg/s'". The docstring of `gm.evaluate` (`gemini/engine/evaluate.py`) says an inlet takes `flow` for a volume flow.

- Check that `{"flow": "150 m3/h", "T": ..., "p": ...}` works for an inlet whose fluid is known, and add a test for it.
- When `m_dot` gets a volume unit, the error keeps code `invalid_unit` (or the code used today) and adds a suggestion: give it as `flow`. Write the failing test first.
- If `flow` does not work, make it work inside `evaluate.py` only (convert with the inlet's fluid density at the given T and p), or stop and report if that needs `modules/`.
- Document `flow` in `api.md` next to `m_dot`.

## 4. `gm.optim.minimize` and `gm.optim.sample` (bonus)

Both are declared in `gemini/optim/search.py` and raise `NotImplementedYet`. Build them as declared.

- **`minimize`:** each trial copies the plant, sets the variables with `set_params`, simulates `profile` with `gm.simulate` and reads the objective. Use a bounded optimiser from scipy that respects `evaluations` (for example `scipy.optimize.differential_evolution` with `maxiter`/`popsize` set from it, or a Latin hypercube start plus a bounded local search). Choose one, keep it short, and say which. A trial that fails or breaks a constraint is recorded in `history` with its reason and is never `best`.
- **`sample`:** draws with `numpy.random.default_rng(seed)`, the three declared distributions, one simulation each; `summary` per metric with `mean`, `p5`, `p50`, `p95`, `unit`.
- **Objective and metric names** as declared: a name of `gm.kpi.names()` or `lcoh`, `lcoc`, `co2`, plus `lcts` and `annualised_cost` from section 2.
- **`profile` default:** geomind's tool takes no `profile`. Make `profile` optional: `None` means the run input of the hackathon demand year, the way `gm.schedule` builds it from `gm.profiles` (heating and cooling demand). If that needs rules the call does not have, keep `profile` required and say what is missing.
- Plain JSON results, values with units. Each call is reproducible with the same seed.
- **Tests:** a tiny plant and a two-day profile: `minimize` on one bounded variable finds a known optimum within the budget; `sample` with a fixed seed gives the same summary twice. Keep each test under 1 s; use a smaller budget in tests if needed.

## 5. Docs

- `api.md`: the new names and signatures, unreleased changes, and `NotImplementedYet` removed from these four.
- The doc that lists rules of `gm.schedule`, the checks doc and the economics doc (LCTS and annualised cost with their formulas).
- `AGENTS.md` "Start here" if it lists what is not built.
- Every docstring touched.

## 6. Report

- Commits on `gaps`, one per section.
- How outage days are chosen, with the outage days per doublet for 2 doublets at 330 days on the hackathon demand year (`inputs/hackathon/`), and the heat moved to other sources on those days.
- The column the operating-days check reads.
- `lcts` on one example plant, and whether `lcoh` / `lcoc` now use `annualised_cost`.
- The optimiser chosen for `minimize`, and whether `profile` became optional.
- Anything stopped because it touched the redesign's files.
- Files of `gaps` that the redesign also changed on `refactor` so far (run `git diff --stat refactor...gaps` and `git log refactor --since=<start time>`), so part B knows the merge conflicts to expect.
