# Task: Controls and boundaries leave `forward`; the module sets them before each call

## 0. Context and rules

You are in the team repo, on branch `refactor` (which has the PyTorch-style module
API and the fixed `forward` structure: `# Modules` / `# Outputs` / `# Outlets`, then
`outlets = dict(...)` and `return outlets`). Work directly on branch `refactor` (no new branch).
Commit on `refactor`; at the end `git push origin refactor`. No PR, no other branches. Read `AGENTS.md`, `.claude/docs/*`, `gemini/core/modules/module.py`, the
declaration classes (`Parameter`, `Inlet`, `Control`, `Boundary`, `Output`, `Outlet`), every
module, the engine step code (`chained_step`, `twin_step`), the bindings, `gemini/legacy/`,
`gemini/optim/calibrate.py`, the examples and the tests before changing anything.

Goal: `forward` looks like PyTorch's `forward(x)`: it receives **only inlets**. Controls and
boundaries are declared in `__init__` (as today) and read inside `forward` as plain attributes
(`self.frequency`), exactly like parameters. The base class sets them before every `forward`,
from the engine or from the call. This matches FMI too (`setReal` for inputs, then `doStep`).

Rules:
- Physics and numbers do not change. Golden values, e2e metrics, replay/simulate results must be
  identical to the baseline (only column/path renames listed in the report).
- No compatibility shims: the old way (controls in the `forward` signature) is removed, not kept
  beside the new one.
- No new concepts beyond what this prompt lists. No public `setup` method.
- black / isort / flake8 clean, full `pytest` green. Commit per phase.

## 1. Target behaviour

### 1.1 Module author

```python
class ESP(Module):
    def __init__(self):
        super().__init__()

        # Parameters
        self.no_stages = Parameter(Count)
        ...

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.frequency = Control(Frequency)

        # Outputs
        self.head = Output(Pressure)
        ...

        # Outlets
        self.discharge = Outlet(Stream)
        self.electricity = Outlet(PowerFlow)

    def forward(self, suction):
        """Compute pump head and power and raise the suction pressure."""

        # Outputs
        self.flow = suction.volumetric_flow()
        self.head = pumps.head(self.flow, self.frequency, self.no_stages, self.head_coeff)
        ...

        # Outlets
        discharge = suction.with_(p=suction.p + self.head)
        electricity = PowerFlow(P=self.power / self.motor_efficiency)

        outlets = dict(discharge=discharge, electricity=electricity)
        return outlets
```

- `forward`'s parameters are exactly the declared inlets, in declaration order, nothing else.
- Reading `self.frequency` returns the plain SI value for the current call (same as reading a
  parameter). The declaration object stays reachable through the existing accessor style
  (follow how `get_parameter()` works; add the matching accessor for controls/boundaries if it
  does not exist yet).
- A class author who needs a helper value from controls computes it at the top of `forward`
  (inside `# Outputs` or as a local); there is no separate hook method for authors.

### 1.2 Using a module

```python
esp = ESP(no_stages=120, ...)

# 1) per call (standalone use, tests, notebooks): wins for this call only
out = esp(suction=s, frequency="50 Hz")

# 2) set a value that stays until changed (what the engine does every step)
esp.frequency = 50.0
out = esp(suction=s)

# 3) a whole plant by path (what the engine does in simulate)
plant.set_inputs({"doublet.production_well.esp.frequency": 50.0,
                  "heat_exchanger.cold_in_temperature": 313.15})
out = plant(secondary=s)
```

Resolution order when `forward` reads a control/boundary:
1. value passed to this call as a keyword;
2. value set by assignment or `set_inputs` (persistent until changed);
3. the declaration `default=`;
4. otherwise `__call__` raises **before** `forward` runs, with the full module path, the input
   name, its kind (control/boundary) and its unit.

### 1.3 What `Module.__call__` does

```python
def __call__(self, *args, **kwargs):
    inlets, inputs = self._split_call_args(args, kwargs)   # inlets vs controls/boundaries
    with self._apply_inputs(inputs):                        # private, always runs
        for hook in self._forward_pre_hooks.values():
            hook(self)
        outlets = self.forward(**inlets)
        for hook in self._forward_hooks.values():
            result = hook(self, outlets)
            if result is not None:
                outlets = result
        ...  # existing validation of outlets and building of the result, unchanged
```

- `_split_call_args`: positional args map to inlets in declaration order. Keywords that are
  inlets go to `forward`; keywords that are this module's own controls/boundaries become
  per-call values; anything else raises `TypeError` listing the valid inlet, control and
  boundary names. Keep the existing inlet validation (flow types, `fluid=` handling).
- `_apply_inputs` (private context manager): converts values to SI (accept quantities/strings
  like `"50 Hz"` exactly as parameters already do), checks bounds the same way parameters do,
  resolves every control/boundary by the order above, raises on missing, and stores the
  resolved values in the per-call record (the same `contextvars` mechanism already used for
  the per-call outputs record), so nested and repeated calls never mix values. On exit the
  per-call values are dropped; persistent values are untouched.
- Assignment to a control/boundary attribute:
  - outside a call: sets the persistent value (converted and checked);
  - inside a call (in a pre-hook or in `forward`): changes the value for the current call only.
- Only the module's **own** controls/boundaries can be passed as call keywords. Children are set
  by path with `set_inputs` (or by assigning on the child).

### 1.4 Hooks (PyTorch names and semantics)

```python
handle = module.register_forward_pre_hook(hook)   # hook(module) -> None
handle = module.register_forward_hook(hook)       # hook(module, outlets) -> None or new outlets
handle.remove()
```

- Pre-hooks run after inputs are applied, so they can read and change controls (per call).
- Stored in ordered dicts on the module, run in registration order, removable through a handle
  (a small `RemovableHandle` like PyTorch's). Not part of `state_dict`, not copied by
  `load_state_dict`.
- Example in docs: clamp a control, log inputs, inject a fault.

### 1.5 Plant-wide inputs

- `set_inputs(mapping)` on any module: keys are dotted paths relative to that module
  (`"<child path>.<input name>"`, or just `"<input name>"` for its own); unknown paths or names
  raise with a close-match suggestion; values are converted and checked.
- The existing declaration listings (controls / boundaries, recursive with paths) are the
  single source for which inputs exist. Use them; do not add a second listing.

### 1.6 No duplicate controls in composites

Today composites (e.g. `DoubletHeatPlant`) declare controls only to pass them down
(`m_dot`, `esp_frequency`, `injection_pressure`, `injection_frequency`). Remove those
pass-through declarations: each control is declared once, on the leaf that uses it, and the
engine/user sets it there by path. A composite declares a control only when the composite
itself uses it in its own logic. If you find a composite control that is genuinely the
composite's own and drives children, keep it, set the children inside the composite's
`forward` through call keywords, and list the case in the report.

Inside composites, child calls pass only inlets:

```python
# Modules
exchanged = self.heat_exchanger(hot_in=filtered.outlets.outlet, cold_in=secondary)
pumped = self.injection_pump(suction=returned.outlets.outlet)
```

The legacy helper methods (`Doublet.produce` / `inject`) lose their control arguments the same
way (they read the children's controls).

## 2. Engine, bindings, data

- `chained_step` (simulate): each step, build the mapping path → value for **every** control and
  boundary in the plant from the step's data, call `plant.set_inputs(mapping)`, then
  `plant(**inlets)`. A control/boundary with no data column and no default is an error before
  the run starts (checked once, listing every missing path), not mid-run.
- `twin_step` (replay/live): for each bound module, set its controls/boundaries from its
  binding, then call it with its inlets only. Measured handling unchanged.
- Bindings keep the keys `controls`, `boundaries`, `inlets`, `measured`, `state`; control and
  boundary entries now point to the leaf paths.
- Data columns use `<module path>.<field>`; paths of moved controls change (e.g. plant-level
  `m_dot` → the leaf that uses it). Regenerate `examples/shared/doublet_heat/` (`plant.json`
  and the CSV) **through the legacy bridge example** so the bridge stays the only converter;
  update `gemini/legacy/` mapping accordingly. List every old → new path.
- Checkpoints: current input values are per-step data, not module state; they are not saved.
  Checkpoint/resume results must stay identical.
- `optim/calibrate.py`: unchanged API; make sure it calls modules the new way.

## 3. Phases

0. **Baseline**: full `pytest`; save golden values, e2e metrics, replay/simulate result hashes and
   replay timing.
1. **Module core**: `_split_call_args`, `_apply_inputs`, per-call values via contextvars,
   persistent values, attribute read/assign rules, `set_inputs`, hooks + `RemovableHandle`.
   Unit tests for each rule in 1.2–1.5 (resolution order, missing error message, unit strings,
   bounds, nested calls don't leak, assignment inside vs outside a call, unknown keyword
   `TypeError`, hook order, hook removal, forward hook replacing outlets, `set_inputs` unknown
   path suggestion).
2. **Leaves**: every leaf `forward` takes only inlets and reads controls/boundaries from `self`.
3. **Composites**: remove pass-through controls (1.6), child calls pass only inlets, legacy
   helpers updated.
4. **Engine/bindings/legacy/data**: section 2; regenerate the shared example via the bridge.
5. **Convention test**: extend `tests/unit/test_forward_structure.py`: every `forward`'s
   parameters equal the declared inlets in declaration order; no composite calls a child with a
   keyword that is not an inlet unless the composite's own control drives it (1.6 exception).
6. **Docs and examples**: `.claude/docs/modules.md`, `conventions.md`, `AGENTS.md`, README,
   module template, all examples: new `forward` signature, the three ways to set inputs, the
   resolution order, hooks with one example. Remove every mention of controls in `forward`.
7. Lint + full `pytest`; compare with the baseline.

## 4. Acceptance script (run and paste output in the report)

```python
import gemini as gm
from gemini.core.modules.pumps import ESP

esp = ESP(...)                                   # values from the shared plant
s = ...                                          # a suction stream
a = esp(suction=s, frequency="50 Hz")
esp.frequency = 50.0
b = esp(suction=s)
assert a.outputs.head == b.outputs.head

def clamp(m): m.frequency = min(m.frequency, 45.0)
h = esp.register_forward_pre_hook(clamp)
c = esp(suction=s)
h.remove()
assert esp.frequency == 50.0                     # per-call change did not persist
assert c.outputs.head < b.outputs.head

try:
    ESP(...)(suction=s)                          # no frequency anywhere
except Exception as e:
    print(e)                                     # path, name, kind, unit

plant = ...                                      # load the shared doublet plant
print([p for p, _ in plant.named_controls()])    # or the existing listing name
```

## 5. Final report (last message)

1. New `Module.__call__` flow and the resolution order, as implemented.
2. Rewritten `forward` methods (file and class).
3. Removed pass-through controls and every path/column/binding rename (old → new).
4. Any composite control kept as the composite's own (1.6) and why.
5. Baseline comparison (identical?), replay timing before → after.
6. Acceptance script output.
7. Lint/test summary lines.
