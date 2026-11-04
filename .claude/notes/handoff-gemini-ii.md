# GEMINI II handoff (from GEMINI 1, 2026-11-03 18:25 UTC)

## Who / where
- User: Sahand (writes Persian; reply in Persian, RTL rules: every line starts with a Persian word, RLM after inline English, code in code blocks, short grouped replies).
- Repo: github.com/geomind-spe-geohackathon-2026/gemini. Work runs ONLY on the NTNU Dell via Remote Control, folder "gemini-work" (environment env_016GdNnRFgDJDikcqrVDEN8i). Never the app's gemini checkout.
- Branches: dev = work, main = stable. Feature branch from dev, worktree ONLY under gemini-work/.tmp/worktrees/, merge to dev, push, delete branch. No PRs. Release from dev via GitHub Actions (wheel on GitHub Releases + ghcr gemini-sandbox image, ~3 min), then fast-forward main to the tag.
- CI tests py3.12 only during the hackathon.
- If the Dell permission system refuses a push/release, immediately ask Sahand in the thread for an explicit word ("push it 0.x.y"); never route around a refusal, never wait silently.

## Current state
- gemini 0.6.0 released, main = dev = 4f1d5f11. Everyone (geomind, backend, deploy, frontend) told to update.
- 0.6.0 = typed ports: Port(direction, *, fluid=Fluid.X | energy=Energy.X (exactly one), phase, level, generic, many, flow, required, temperature, pressure, offered, description); Fluid presets on gm.Fluid (WATER, BRINE, GLYCOL, STEAM, AIR, NATURAL_GAS, FLUE_GAS, CHEMICAL, WASTE, ANY); gm.streams.Energy (ELECTRICITY, HEAT, FUEL, ANY); Inlet/Outlet/Carrier/kind= removed; connect validation + generic inference; plant.check(results=None) -> Issues (stream_mismatch, generic_conflict, unconnected_port, out_of_range warnings); plant.suggest(port=None, *, free, loose, limit) -> Suggestion(port, match EXACT|LOOSE, exact, loose, closes_loop). hackathon.py byte-identical to 0.5.14.
- Learned/statistical ranking of suggestions belongs to geomind, NOT gemini.

## Standing rules for gemini
- gemini is the source of truth; other threads never request things from gemini directly (they make a list for Sahand). Don't relay gemini findings to other threads without Sahand's OK (exception: release announcements he approved).
- Everything general, nothing hackathon-specific inside gemini/ (hackathon only as example data).
- No default values for problem/case values (missing -> error). Method settings follow existing minimize style (required args). Port fields have defaults (approved exception).
- Backward compatible additions; breaking only with Sahand's explicit OK.
- No live LLM runs. Don't run benchmarks/tests Sahand didn't ask for beyond the normal test gates.
- Speed matters: work as parallel as possible (coordinator + subagents in separate worktrees with disjoint files).

## NEW TASK (Sahand 18:23 UTC): genetic algorithm for plant STRUCTURE
Sahand: "design it yourself, logical and consistent with our rules, and start implementing." Decisions made (by GEMINI 1 on his behalf):
- Superstructure on the existing Plant, next to set_range/set_options:
  - plant.set_optional("peak_boiler") — off = bypass (stream inlet joined to matching outlet by port name pairs fluid_in->fluid_out, hot_in->hot_out...; power ports dropped; zero capex; a module may declare its bypass pairs explicitly where ambiguous).
  - plant.set_choice("chiller", {"absorption": [modules...], "compression": [...], "none": []}) — exactly one group on.
  - plant.structures() -> all valid structure dicts; plant.with_structure(dict) -> ordinary concrete Plant (simulate, to_json).
  - Plant file keys: "optional": [...], "choices": {...}. plant.check() reports impossible structures; with_structure output must pass plant.check() (typed ports from 0.6.0 reject invalid wiring before any simulation).
- Search: gm.study.evolve(plant, case, objectives, evaluations, seed, *, population, plan=None, on_progress=None) — required args like minimize. Mixed single-level GA: genes = structure (optional/choices) + existing ranges/options (capacities, doublet count). objectives "lcts" (single) or ["lcts","co2"] (NSGA-II Pareto). Own small deterministic GA/NSGA-II, no new dependency. Generation-parallel via gm.runtime.settings(processes=n). Cache by structure+genes; invalid structures rejected without simulation. Optional polish of the top 3 with minimize.
- Result: Evolution (dict-compatible like Search, to_dict()): front [Design], best Design, history, evaluations. Design = {structure, plant, metrics, feasible, reason}.
- study.json: "method": "evolve", "objectives", "evaluations", "population", "seed". Study.run/StudyResult unchanged; gm.study.kinds() lists "evolve" with its settings.
- Example: hackathon superstructure = union of the 6 existing hackathon plants (example data only, outside gemini/).
- Version: additive -> release as 0.6.1 (Sahand's long-standing preference for patch bumps; 0.6.0 was his explicit breaking exception).
- Tests + docs + CHANGELOG; release when green, ff main, then tell Sahand and ask before announcing to other threads.
- Parked/not doing: free wiring search (connections only via set_choice groups), learned ranking (geomind).

## Post-hackathon watch
- Re-enable other Python versions in CI; old py3.11 lowest-direct failure on main (unknown cause); is_unmet flips on rounding error.
