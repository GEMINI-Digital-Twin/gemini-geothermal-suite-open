# Task: One classification for modules: the folder is the category

## 0. Context and rules

- Today gemini classifies modules twice: by folder (`heat/`, `piping/`, `treatment/`, ...) and by the `category` attribute (`heat_exchange`, `chiller`, `network`, ...), and the two do not match. Some categories are also wrong: `PIDController` is `network`, and `FlashTurbine` and `ORC` are `heat_exchange`. This step makes **one classification: each module's `category` is exactly the name of the folder it lives in.**
- Only this. The layout flatten (`gemini/core` removal), the plant-code rewrite, splitting `module.py`, formulas to physics and the naming glossary are **later prompts**. Do not start them.
- Start from the current local `refactor`. Read `AGENTS.md`, every file in `.claude/docs/` (especially `api.md`, `equipment.md`, `conventions.md`) and follow them.
- **Standing rules:** no concept has two implementations; behaviour is identical on every backend; physics and numbers do not change (every example and golden is bit-identical).
- Work directly on branch `refactor` (no new branch, no PR) and commit there. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working **inside `gemini/`**. Sessions in other folders do not block you.
- Workspace `/Users/sahand/Desktop/crust-team`. Change **only** `gemini/`. You may read `geomind/`, `backend/` and `frontend/` to find uses of category names, but never change them.
- Temporary files go to `.tmp/categories/` (git-ignored).
- One agent is enough. Subagents, if any, run on a lighter model and only for read-only searches.
- **Tests:** development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), in parallel, under 300 s. Never delete or shrink existing tests, datasets or goldens.
- **Quality bar** as in `.claude/docs/conventions.md`. No comments inside code; black, isort and flake8 clean.
- If something else is needed, say so in the report.

## 1. The categories (folder = category)

Folder names are one word, no underscores. Under `gemini/core/modules/`:

| Folder and category | Modules |
|---|---|
| `subsurface` | `ProductionReservoir`, `InjectionReservoir`, `BoreholeField`, `DownholeHeatExchanger`, `ThermalDecline` |
| `wells` | `ProductionWell`, `InjectionWell` (and the shared `well.py`) |
| `pumps` | `ESP`, `CentrifugalPump`, `LineShaftPump`, `InjectionPump`, `GasCompressor` |
| `treatment` | `Degasser`, `Filter`, `Desander`, `Blowdown`, `Vent`, `InhibitorDosing` |
| `exchangers` | `HeatExchanger`, `Cooler` |
| `heating` | `HeatPump`, `Boiler`, `CHP` |
| `cooling` | `AbsorptionUnit`, `AdsorptionChiller` (and the shared `_sorption.py`) |
| `power` | `FlashTurbine`, `ORC`, `Separator`, `GridConnection` |
| `storage` | `ThermalStorage`, `IceStorage`, `AquiferStorage` |
| `piping` | `Pipe`, `Valve`, `Mixer`, `Splitter`, `PressurizationTank` |
| `demand` | `HeatConsumer`, `CoolingConsumer` |
| `control` | `PIDController` |
| `plants` | every plant (`Plant` and the registered plants) |

- `gm.modules.categories()` returns these 13 names in this order (the display order: subsurface first, demand last). The old folder `heat/` disappears.
- If a module is not in this table, or one seems to belong elsewhere, place it by what it does, list it in the report, and do not invent a new category.

## 2. One source of truth

- The category is **derived from the folder** by the registry, in one place. Remove the `category = "..."` class attribute from every module, so the two can never disagree again. A module registered from outside (`gm.modules.register`, `gm.modules.load_file`) states its category explicitly, checked against the fixed list.
- Move the files with `git mv` so history is kept. Update every import inside `gemini/`, `tests/`, `examples/` and `scripts/`. Public names (`gm.modules.ESP`, ...) do not change.
- `describe()`, `gm.modules.names(category=...)`, the JSON Schemas and their samples, and the frontend's notes in the docs use the new names.
- Tests mirror the new folders (`tests/.../modules/<category>/test_<name>.py`).
- A test checks that every registered module's category equals its folder name, and that every category in the list has at least one module.

## 3. API version

The category list is a public return value, so raise `gm.API_VERSION` to 2, update the public-API snapshot, and add a line to the change log in `.claude/docs/api.md` with the old to new mapping (`heat_exchange` → `exchangers`, `heat_pump` and `boiler` → `heating`, `chiller` → `cooling`, `network` → `piping`, `well` → `wells`, `pump` → `pumps`, `separation` → `treatment`, `consumer` → `demand`, `plant` → `plants`, plus `power` and `control` new).

## 4. Docs

Update `api.md`, `equipment.md`, `modules.md` and anything else that names a folder or a category, in the same commit.

## 5. Report

Commits; the final table of modules per category; modules you placed differently from section 1 and why; every place in `geomind/`, `backend/` or `frontend/` that uses an old category name (read-only check, file and line), so I can update them.
