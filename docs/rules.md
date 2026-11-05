# Project rules

Every rule of this repository, in one place, for whoever changes it. Where a test enforces a rule,
the rule names it. Reasons and worked detail are in the docs for agents under `.claude/docs/`.

## Numbers

- Preserve captured numerical behaviour. A number changes only on purpose, with the reason in the
  changelog and in the commit.
- A bug fix starts with a test that fails without the fix.

## Freeze

From 0.6.0 gemini is frozen: only bug fixes go in, each released as a new 0.6.x patch. No new
name, feature or speed work without the owner's decision.

## The public API

- **Backward compatible from 0.5.0.** Nothing that exists in 0.5.0 may break: no public name
  (`gm.*`, `gm.<folder>.*`) is renamed or removed, no signature loses or reorders a parameter or
  changes a default or a kind, no output field or behaviour changes, no key of the case, economics,
  plant or study JSON schemas disappears or becomes required, and the module-author contract
  (`forward`, `update`, `State`) stays. Additions that break nothing are allowed, and the owner
  decides them. What the competition runs (`examples/hackathon.py`, `examples/hackathon_2026`) stays
  exactly the same. `tests/unit/test_api_compatibility.py` compares with the stored
  `tests/fixtures/public_api_0_5_0.json`, a file written once and never regenerated, and
  `tests/e2e/test_competition_surface.py` pins the competition.
- **Reading and writing.** Every reader is `from_<format>` and every writer `to_<format>`: `from_csv`,
  `from_json`, `from_dict`, `from_values`, `from_bytes`, ... and `to_csv`, `to_json`, `to_dict`,
  `to_bytes`, .... A reader is a classmethod on the class it returns (`gm.Case.from_json(path)`); a
  writer is a method of the object (`case.to_json(path)`). Only a reader that returns no gemini
  class (a demand frame) is a plain function in its folder (`gm.case.from_csv`). There are no
  `read_*`, `write_*`, `load_*`, `save_*`, `parse_*` or `dump_*` names;
  `tests/unit/test_code_quality.py` rejects those prefixes.
- **Return shapes and errors.** Every public return uses one of three shapes, value, problem (the
  shape of an error) or check, built by `gemini/units/shapes.py`. Every public call raises by
  default; `on_error="record"` reports instead.

## Values

- **One unit format.** A value with a unit is a `gm.units.Quantity` with a unit of the
  `gm.units.Unit` enum, or its dict `{"value": 150, "unit": "m3/h"}`; a string such as `"150 m3/h"`
  is never accepted, and nothing in the package parses unit text. A dimensionless value is a number.
  A bare number with a dimension raises `invalid_value` at every public door (`set_params`,
  `Plant.set_inputs`, `gm.Stream`, `Stream.with_`, attribute assignment outside a call, `gm.Fluid`,
  `gm.call`); `gemini` itself uses the private SI path (`_set_si_params`, `Stream._si`, `Fluid._si`,
  `Stream._with_si`, `Module._assign_si`).
- **No defaults.** Nothing a user must decide has a default value in gemini: not a price, a
  temperature, a limit, a factor or an efficiency. Such a field is required, or absent (`None`), and
  a call that needs an absent value raises `missing_value` (`missing_assumption` below `economics`)
  naming its path. `gm.case` has no default at all, and a module or plant declaration keeps a default
  only if it is in `DECLARED_DEFAULTS` (a sourced constant or the zero of an accumulator).
  `tests/unit/test_code_quality.py` checks this.
- **The input is a case, never a problem.** The word `problem` is only the return shape of an error;
  `tests/unit/test_code_quality.py` rejects it as a name in `gemini/`.
- **One owner for an input.** Before adding or moving an input, apply the placement test: one owner,
  one file, and the reason is written there.

## Code

- **A general package.** gemini knows no sample. `examples/<name>/` holds a sample project and only
  `examples/` and `tests/` read it; no number, default or name in `gemini/` comes from one. gemini
  holds no data file.
- **Update the code, never wrap it.** When a refactor changes a name or a shape, every caller is
  changed in the same task, and no wrapper, alias or shim is written.
- **A leaf computes and a plant connects**; no class does both. A leaf has physics calls and one pure
  method, `forward`, and a pure `update` when it has states. Every composite is a `Plant`: it declares
  children, ports and connections in `__init__` and never writes `forward`. The engine closes loops
  and solves constraints.
- **Pure modules.** Modules declare parameters and ports in `__init__`.
  `forward(self, inputs, inlets, state)` reads only parameters on `self` (never a control, boundary,
  state or output), writes nothing and returns `(outputs, outlets)`. A per-step value is never
  `None`: an output that is empty when off is NaN, shown as `None` in results. `update(self, inputs,
  inlets, outlets, state, dt)` returns the next state.
- **Everything is a module and a port.** Everything in the plant's energy and mass flow is a module,
  everything that crosses between modules goes through a port, and a plant total is read from the
  ports of the modules at the plant's edge. Every port of a module is connected or named as a plant
  port; there are no automatic plant ports.
- **Where code goes.** Physics lives in `gemini/physics/`, and in a `_physics.py` beside a category
  only when it needs streams. Machinery goes in an `_utils/` folder, code of one category in a
  private file of its folder. Public names are flat, `gm.<folder>.<Name>`, exported by the folder's
  `__init__`; inner files are private. The run folders (`modules`, `plants`, `case`, `physics`, `ops`,
  `runtime`, `engine`, `streams`, `units`, `errors`, `_utils`) import none of `compiler`, `study`,
  `evaluate`, `analysis`; `tests/unit/test_package_boundaries.py` checks it.
- **Plants and engine.** No engine loop sleeps or schedules itself. Keep the public API small and
  examples outside the package. The application, not the package, reads CSV, databases or APIs.

## Documents

- `.claude/`, with `.claude/docs/`, is for agents. `README.md` and `docs/` are for people. The README
  is short and links only to `docs/`; it never links `.claude/docs/`.
- This file holds every rule. `AGENTS.md` holds orientation and sends the reader here.
- When a commit changes behaviour, structure or conventions, update the relevant document in the same
  commit, and note a user-visible change in [CHANGELOG.md](CHANGELOG.md).

## Branches

- `main` is the stable line (competition delivery, releases). Change it only on the user's request.
- `dev` is the development line, and a new version that reaches it is published
  ([VERSIONING.md](../VERSIONING.md)).
- `feature/<name>`, `fix/<name>` and `docs/<name>` hold one task each, with a short lowercase name
  joined by hyphens (`feature/study-speed`, `fix/budget-tests`). Branch from `dev`, merge back into
  `dev`, then delete the branch locally and on `origin`.
- Temporary worker branches and worktrees of a coordinator session stay local, are never pushed, and
  are removed at the end of the task.
- Never name a branch `dev/...`: git cannot hold both `dev` and `dev/<name>`.
- Open a pull request only when asked.

## Worktrees and `.tmp/`

- Every git worktree goes under the repository's own `.tmp/` (for example
  `.tmp/worktrees/<name>`), never beside the repository.
- `.tmp/` is in `.gitignore` and nothing under it is tracked; `tests/unit/test_repository.py` fails
  otherwise.

## Tests

- Run `make test` and `make lint` before every commit: always test what changed and everything that
  imports it. `make test-release` is the release profile.
- A test call of the fast tier may take at most one second of CPU time.
