# Task: Remove `gemini/core`: move its folders up, data and legacy into utils

## 0. Context and rules

- `gemini/core` is a leftover layer: the agent code that once sat beside it has moved to the `geomind` repo. This step **only moves files**. No logic, no physics, no behaviour and no public name changes, except the one in section 3. Every number, example and golden stays bit-identical.
- Only this. The `Module` cleanup, the physics cleanup, the naming glossary and the plant-code rewrite (including the plant JSON files and templates) are **later prompts**. Do not start them.
- Start from the current local `refactor`, with the category commits pushed. Read `AGENTS.md` and every file in `.claude/docs/` and follow them.
- **Standing rules:** no concept has two implementations; behaviour is identical on every backend.
- Work directly on branch `refactor` (no new branch, no PR) and commit there. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working **inside `gemini/`**. Sessions in other folders do not block you. If their load makes a 1 s budget test fail, rerun that test alone before treating it as a failure, and say which tests you retimed.
- Workspace `/Users/sahand/Desktop/crust-team`. Change **only** `gemini/`. You may read `geomind/` and `backend/` to find imports of internal paths, but never change them.
- Temporary files go to `.tmp/flatten/` (git-ignored).
- One agent is enough. Subagents, if any, run on a lighter model and only for read-only searches.
- **Tests:** development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), in parallel, under 300 s; plus the e2e tier and all numbered examples once at the end, compared byte for byte with a baseline you take before the first move. Never run the slow dataset locally. Never delete or shrink existing tests, datasets or goldens.
- **Quality bar** as in `.claude/docs/conventions.md`. No comments inside code; black, isort and flake8 clean.
- If something else is needed, say so in the report.

## 1. Target layout

```text
gemini/
  analysis/  checks/  economics/  errors/  graph/  ops/  optim/  profiles/  testing/   (stay)
  modules/      ← core/modules
  physics/      ← core/physics
  types/        ← core/types
  engine/       ← core/engine
  backends/     (stays) + runtime.py ← core/runtime.py
  utils/        (stays) + data/ ← core/data, legacy/ ← core/legacy
docs/schemas/   ← gemini/schemas/*.json (no JSON files of schemas inside the package)
```

- `gemini/core/` no longer exists afterwards, not even as a compatibility shim. There are no re-export modules for old paths: one name per thing.
- Move with `git mv` so history is kept, in one commit of pure moves plus import updates. Then a second commit for everything else (docs, tests, section 3).
- Update every import in `gemini/`, `tests/`, `examples/` and `scripts/`, and every path in `pyproject.toml`, `Makefile`, `.claude/docs/`, `AGENTS.md`, `CLAUDE.md` and `CONTRIBUTING.md`.
- Tests mirror the new package layout (`tests/.../modules/...`, `tests/.../utils/data/...`). The category folders inside `modules/` stay exactly as the last step left them.
- `examples/core/`: if it only mirrors the old package name, rename it to match what it shows, and say what you chose.
- **Schemas:** the functions that build each schema stay in the package. `scripts/write_schemas.py` writes the files and samples to `docs/schemas/`, and the sample-up-to-date test reads them from there.
- The plant JSON files under `modules/plants/specs/` and `templates/` stay where they are in this step. The plant rewrite removes them later.
- Check the import cycle rules and the "implicit mechanisms" list in `conventions.md` still hold, and that the registry still derives each module's category from its folder.

## 2. Public names

Every `gm.*` name keeps working unchanged: `gm.runtime` (now from `backends/runtime.py`), `gm.Dataset`, `gm.Profile`, `gm.Clock`, `gm.modules.*`, `gm.plants.*`, `gm.units.*` and the rest. The public-API snapshot test must pass without changes, except section 3.

## 3. One public change: `gm.legacy`

`legacy` moves into `gm.utils`, which is not public. So `gm.legacy` leaves the public API; the old-project import stays public through `gm.plants.convert_legacy(folder)` only. Raise `gm.API_VERSION` to 3, update the snapshot, and add a change-log line in `.claude/docs/api.md`. If anything other than `convert_legacy` needs a legacy function publicly, list it in the report instead of keeping `gm.legacy`.

## 4. Report

- Commits.
- The final tree, two levels deep.
- What you did with `examples/core/`.
- Test, e2e and example results against the baseline.
- Every import of an internal gemini path in `geomind/` and `backend/` that this move breaks (read-only check, file and line). `backend/tests/core/gemini/test_plant.py:67` is a known one.
