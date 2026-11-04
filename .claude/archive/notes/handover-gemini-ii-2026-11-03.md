# Handover from GEMINI I to GEMINI II (2026-11-03 18:25)

## Where things stand
- gemini 0.6.0 released (tag v0.6.0); main = dev = 4f1d5f11. Origin branches: dev, main, gh-pages only.
- Work in /home/fatemec/geomind-spe-hackathon-2026/gemini-work (dev checked out). New worktrees go under gemini-work/.tmp/worktrees/<name>.
  Never touch /home/fatemec/geomind-spe-hackathon-2026/gemini (the app's checkout).
- Python: gemini-work/.venv (3.12). Its editable install points at gemini-work, so in another worktree run
  `python -m pytest` from that worktree (cwd first) and `PYTHONPATH=. python scripts/...` for scripts.
- Release: bump `version` in pyproject.toml, add docs/CHANGELOG.md section, add a row to the change log in
  .claude/docs/api.md, add the version hash in tests/unit/test_public_api.py (python -m tests.fixtures.capture_public_api),
  regenerate schemas with `PYTHONPATH=. python scripts/write_schemas.py` (revert results_summary/value sample last-bit noise).
  Fast rule for urgent work: fast tier + lint locally, merge to dev, push; the Release workflow (Python 3.12 only during the
  hackathon) tests, builds wheel + ghcr image, tags. Then verify the wheel in a clean venv, `sg docker -c "docker pull ..."`,
  fast-forward main to the tag (`git push origin <tag-sha>:refs/heads/main`).
- Pushing to dev needs the owner's direct OK in the thread ("push it"); the permission check refuses relayed approvals.
- Rules: docs/rules.md (no hidden defaults for what a user decides, general package, no aliases/wrappers, 0.x versioning:
  additive = PATCH). The freeze was lifted by the owner for the port work and for structure optimisation.

## Task: structure optimisation with a genetic algorithm (owner: "design it yourself, consistent with our rules, then implement")
Decided design (GEMINI I proposal, owner said go):
1. Superstructure on a plant, beside set_range/set_options:
   - plant.set_optional("peak_boiler"): the module may be absent; absent = bypassed (stream inlet joined to the outlet of the
     same path: fluid_in->fluid_out, hot_in->hot_out, cold_in->cold_out, source_in->source_out, sink_in->sink_out, ...; power and
     gas side ports dropped). A module whose pairs are ambiguous declares its bypass pairs.
   - plant.set_choice("chiller", {"absorption": [...modules], "compression": [...], "none": []}): exactly one group present.
   - plant.structures() -> every valid structure as a dict; plant.with_structure({...}) -> an ordinary Plant (bypassed), which
     passes plant.check() (0.6.0 typed ports) or is rejected.
   - Plant file keys "optional": [...], "choices": {...}; plant.check() reports bad structure declarations.
2. gm.study.evolve(plant, case, objectives, evaluations, seed, *, population, plan=None, on_progress=None)
   - objectives "lcts" or ["lcts", "co2"] (NSGA-II front); evaluations, seed, population required (no defaults).
   - one mixed genome: structure genes + existing ranges/options (capacities, doublet count). Generational, so each
     generation runs in parallel with gm.runtime.settings(processes=n). Deterministic with the seed. In-house GA/NSGA-II,
     no new dependency.
   - Fitness/ranking as minimize: feasible before infeasible, infeasible by violation (gemini.study.minimize._ranked).
   - Returns Evolution (dict + to_dict): {front: [Design], best: Design, history, evaluations}; Design = {structure, plant,
     metrics, feasible, reason}.
3. study.json method "evolve" with objectives, evaluations, population, seed; gm.study.kinds() lists it.
4. First example: a hackathon superstructure combining the six candidate plants of examples/hackathon_2026.
5. Version 0.6.1 (additive). Tests for each piece, fast tier + release tier, hackathon.py output unchanged.

## Other open items (owner decides)
- Whole-plant matching for plant.suggest; a supply/return role field on ports; gm.Energy at top level.
- "five paths with no inlet stream", "type check in with_value": titles only, no description.
- "day" unit alias: waiting for approval.
- After the hackathon: re-enable other Python versions in CI; Python 3.11 lowest-direct failed on main for 0.5.13 (cause
  unknown); is_unmet flips on rounding.
- Learning/statistics for connection suggestions belongs in geomind, not gemini.
- Speed log: gemini-work/.tmp/speed/log.md. Port table: gemini-work/.tmp/port-types/ports.md.
