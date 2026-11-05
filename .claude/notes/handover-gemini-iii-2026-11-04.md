# Handover to the next gemini session (2026-11-04, updated after 0.6.4)

## State
- (history) gemini 0.6.2 released (tag v0.6.2) at 70fa57e5; wheel verified in a clean venv, ghcr image pulled.
  If it is green: verify the wheel in a clean venv (curl the wheel from the GitHub release, then
  `pip install ./file.whl`; pip from a URL is refused by the permission check),
  `sg docker -c "docker pull ghcr.io/geomind-spe-geohackathon-2026/gemini-sandbox:0.6.2"`, then
  `git push origin <tag-sha>:refs/heads/main`. (See the end of this file for what was done.)
- Work only in /home/fatemec/geomind-spe-hackathon-2026/gemini-work (dev checked out). Worktrees only
  under gemini-work/.tmp/worktrees/<name>. Never touch ../gemini (the app's checkout).
- Python: gemini-work/.venv (3.12); its editable install points at gemini-work, so in another
  worktree use `PYTHONPATH=.`. e2e tests that run an example without PYTHONPATH import the shared
  venv: confirm such failures in a clean venv with the branch installed.
- Release procedure: as in GEMINI_II.md (version in pyproject, CHANGELOG section, api.md change-log
  row, hash in tests/unit/test_public_api.py via `python -m tests.fixtures.capture_public_api`,
  schemas via scripts/write_schemas.py with sample noise reverted). Gate: release tier, lint,
  `examples/hackathon.py` stdout identical (reference: 0.6.0 output, unchanged through 0.6.2).

## 0.6.4 (2026-11-04, after 0.6.3)
- Bug report from geomind (via Sahand): dissolved_gas.H2S passed set_case, then build/simulate failed
  ("gas composition: species = 'H2S'"). Fixed: gemini.physics.gas.SPECIES is the one list of gas species
  (H2S added: 34.081 g/mol, LHV 518.07 kJ/mol from NIST formation enthalpies, 0 carbon; SO2 not
  reported); kinds.GRID_GAS_SPECIES = all of it, kinds.GAS_SPECIES (CH4, CO2, N2, H2S) drawn from it,
  a test holds them together. Sour-gas chain test closes mass, energy and carbon.
- Also fixed a stale expected file left by 0.6.3: tests/e2e/expected/plant.txt "Filled: 8 left" (0.6.3's
  doublet check change gives 8, 0.6.2 gave 40). The e2e examples are only in the release tier: RUN IT
  before a release (`make test-release`, use -n 8 and nice).
- Release gotcha: capture_public_api also rewrites tests/fixtures/public_api.json; commit it.
- RELEASED: tag v0.6.4 = main = dev = 2e0862aa; wheel sha256 aaa89e16...a7b9 verified in a clean venv;
  ghcr image 0.6.4 pulled. (The Release run on 4663e6a0 failed only for the missing snapshot; 2e0862aa green.)

## 0.6.3 (2026-11-04, after 0.6.2)
- RELEASED: tag v0.6.3 = main = dev = d86040d5; wheel sha256 2fe06435...f023 verified in a clean venv; ghcr image 0.6.3 pulled. Owner's rule given during this task:
  gemini does NOT provide data/inputs on behalf of other packages (they source their own values);
  units, unclear errors and real gemini bugs are ours. Apply it to every future request.
- Fixed: 11+28 (doublet: check/run name the one missing design value, not every derived child),
  27 (gm.call control-in-parameters -> invalid_call, still a KeyError), 31/29 (degC/km, per-degC
  property units, kW/K MW/K GW/K), 30 (Plant.to_dict/to_json(units=)), 16 (capex.pipe EUR/MW/m with
  optional Pipe.nominal_capacity), 17 (docs/cost-sources paths are case keys + test), 26
  (gm.study.metrics()), 22 (every Case.schema() key described), 12 (time.end exclusive, documented).
- Rejected: 32 (site.air.pressure already exists; geomind sends it, computing it from elevation
  itself if needed; no elevation model in gemini).
- Release gotcha: capture the public API hash AFTER scripts/write_schemas.py (the snapshot hashes
  the schema files).

## Owner's working rules (Sahand)
- Fresh, small sessions: give implementation, tests and investigations to subagents with short
  briefs and short reports; the main session coordinates, merges, releases.
- CPU: at most ~75% of the Dell (32 cores): harness --processes <= 16, pytest -n 6-8, `nice -n 10`
  on long runs, never two heavy runs at once; tell subagents.
- Additive only (0.x patch), no hidden defaults, nothing sample-specific in gemini/, docs + CHANGELOG
  in the same commit, a fix starts with a failing test. No PRs: merge to dev locally, push, delete
  branches. Never contact other threads; report to the coordinator (@parent).

## What 0.6.2 holds
- Structure optimisation as a tool: Plant.set_bypass + file key `bypass` ({} = remove with
  connections), class `bypass` on every module where physical (audit table in equipment.md),
  gm.plants.union (merge concrete plants; a branch some plants lack is not merged: build by hand),
  evolve: untied alternatives, inactive genes normalised, no clones, repair of invalid children,
  adaptive local steps, lazy structure checks above 256 structures, batched trials per structure,
  crash-proof candidates, structural infeasibility (no unit for a service), stop={generations,
  seconds}, Evolution.structures/rejected/budget/objectives/to_frame()/explain(), hypervolume history.
- Acceptance harness scripts/validate_evolve.py (truth cache must be recomputed when the example
  changes; ~37 min at 30 procs, use <=16). Result at 256 sims, 10 seeds: hackathon success 90%,
  median gap 1.45% (random 0%, 65%); chain gap 3.05% (random 8.7%); pareto HV 0.934 (0.904);
  constrained 70%/0.65% (40%/2.2%).
- Requests 13-15: case reading collects every issue (one ValidationError.issues), list parameters
  shown as {"value": [..], "unit"}, unit mol% for gas fractions.
- Requests 16-21: economics basis chosen by unit (heat_exchanger EUR/W with nominal_duty, storages
  EUR/MWh with energy_capacity, production_pump EUR per unit, opex.fixed EUR/MW/yr, subsidy EUR/MWh
  with cap), opex.per_energy.<kind>, consumables listed (chemical, waste_disposal), a description
  per economics field; IceStorage priced as ice_storage only when capex.ice_storage is given.
- Also fixed: minimize's on_progress total (variables), evolve JSON reasons, study.json checks.

## Open items (owner decides)
- A non-raising "validate a case" call (request 13 asked one call; today try/except .issues).
- union cannot merge a whole branch (splitter + mixer) some plants lack.
- Scheduler gap: a plant with neither heat pump nor boiler (exchanger only) sets no consumer flow.
- Atmosphere keeps a name-pair bypass though turning it off is not physical.
- constrained synthetic at 64 sims a bit worse than before tuning; pareto HV at 256 within noise.
- Older: whole-plant suggest matching, supply/return role on ports, "day" unit alias, CI Python
  versions after the hackathon, is_unmet rounding (output only; not used by the verdict).
