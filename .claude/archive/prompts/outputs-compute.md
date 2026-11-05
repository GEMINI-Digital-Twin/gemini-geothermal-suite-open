# Task: `forward` handles fluid only; outputs are computed after it

## 0. Context and rules

Run this **after** `inputs-from-engine` (controls/boundaries are set by the base class and
`forward` takes only inlets). Work on branch `refactor`; work directly on branch `refactor` (no new branch). Commit on `refactor`; at the end `git push origin refactor`. No PR, no other branches. Read `AGENTS.md`, `.claude/docs/*`,
`gemini/core/modules/module.py`, the declaration classes, every module, the engine/results code,
`gemini/legacy/`, `gemini/optim/calibrate.py`, the examples and the tests first.

Goal:
- `forward` only moves fluid: inlets in, fluid outlets out. No outputs in `forward`.
- Leaf modules compute their outputs in one method, `_compute_outputs`, defined (empty) on
  `Module` and called automatically by the base class after `forward`.
- Composite modules never compute outputs by hand; they declare them with formulas
  (`Output.of`, `Output.total`, `Output.ratio`) and the base class evaluates them.
- Inlets and outlets carry fluid streams only. Non-fluid flows (electricity, heat loss) become
  outputs.

Rules:
- Physics does not change. Numbers must match the baseline; the only allowed differences are
  floating-point re-association (e.g. `head` now computed as `discharge.p - suction.p`).
  Compare with `rel=1e-9`, report the largest relative difference per quantity; anything
  larger is a bug to fix, not a tolerance to widen.
- No compatibility shims; the old way is removed. No new concepts beyond this prompt.
- black / isort / flake8 clean, full `pytest` green. Commit per phase.

## 1. Target

### 1.1 Base class

```python
class Module:
    def _compute_outputs(self):
        """Compute this module's outputs after forward. Override in leaf modules.

        Arguments are requested by name: any of this module's inlets and outlets.
        Composite modules do not override this; they declare formula outputs.
        """

    def __call__(self, *args, **kwargs):
        inlets, inputs = self._split_call_args(args, kwargs)
        with self._apply_inputs(inputs):
            for hook in self._forward_pre_hooks.values():
                hook(self)
            outlets = self.forward(**inlets)
            if outputs_enabled():
                self._call_by_name(self._compute_outputs, inlets, outlets)
                self._compute_formula_outputs()
                for hook in self._forward_hooks.values():
                    self._call_by_name(hook, inlets, outlets, module=self)
                self._check_outputs()
            ...  # existing outlet validation and result building
```

- `_call_by_name`: passes only the inlets/outlets named in the callable's signature. Signatures
  of `_compute_outputs` are inspected **once per class** (in `__init_subclass__`) and validated:
  every parameter name must be an inlet or outlet of that class, otherwise raise at class
  definition with class name, bad name and valid names. Cache the result; no per-call
  `inspect`.
- Order after `forward` is fixed: `_compute_outputs` → formula outputs → user forward hooks →
  `_check_outputs`.
- `_check_outputs`: every declared output has a value for this call; otherwise raise with the
  module path and the missing output names.
- Overrides never need `super()._compute_outputs()` (the base is empty); document this.
- Outputs keep the existing per-call record (contextvars); reading `module.head` and
  `out.outputs.head` work as before.

### 1.2 Forward hooks (update from the previous task)

`register_forward_hook(hook)` now calls hooks by name like `_compute_outputs`:
`hook(module, <inlets/outlets it names>)`, return value ignored (hooks no longer replace
outlets). Validate hook signatures at registration. Pre-hooks unchanged. Update tests and docs
from the previous task accordingly.

### 1.3 `gm.no_outputs()`

Context manager like `torch.no_grad()` (contextvars-based, nestable, thread-safe): inside it the
whole output step is skipped (no `_compute_outputs`, no formulas, no forward hooks, no check);
results carry outlets only and `out.outputs` is empty. Also a decorator form. Export from
`gemini`.

### 1.4 Leaf module

```python
class ESP(Module):
    def __init__(self):
        super().__init__()

        # Parameters
        ...

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.frequency = Control(Frequency)

        # Outputs
        self.flow = Output(VolumeFlow)
        self.head = Output(Pressure)
        self.power = Output(Power)
        self.electricity = Output(Power)

        # Outlets
        self.discharge = Outlet(Stream)

    def forward(self, suction):
        """Raise the suction pressure by the pump head."""

        # Outlets
        flow = suction.volumetric_flow()
        head = pumps.head(flow, self.frequency, self.no_stages, self.head_coeff)
        discharge = suction.with_(p=suction.p + head)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, suction, discharge):
        self.flow = suction.volumetric_flow()
        self.head = discharge.p - suction.p
        self.power = pumps.power(self.flow, self.frequency, self.no_stages, self.power_coeff)
        self.electricity = self.power / self.motor_efficiency
```

Guidelines for leaves:
- Derive outputs from the inlet/outlet states where physically equivalent (pressure rise, duty
  from enthalpy difference, temperature drop) instead of repeating the physics.
- Recompute only what cannot be derived from fluid states (e.g. pump power from the curve).
- If a shared intermediate is expensive, put it in a small private helper used by both
  `forward` and `_compute_outputs`; do not cache it on `self`.

### 1.5 Composite module

```python
# Outputs
self.thermal_power = Output.of("heat_exchanger.duty")
self.electricity_use = Output.total("electricity")
self.cop = Output.ratio("thermal_power", "electricity_use")
```

```python
def forward(self, secondary):
    # Modules
    ...
    exchanged = self.heat_exchanger(hot_in=hot.outlets.outlet, cold_in=secondary)
    ...

    # Outlets
    secondary_out = exchanged.outlets.cold_out
    gas = degassed.outlets.gas

    outlets = dict(secondary_out=secondary_out, gas=gas)
    return outlets
```

Formula outputs (`gemini/core/modules/` next to `Output`; they are `Output` declarations, unit
and quantity inferred or given):
- `Output.of("child.path.name")`: the named output (or outlet field, e.g.
  `"degasser.gas.m_dot"`) of a descendant **from this call**. The descendant must have been
  called exactly once during this call; otherwise raise with the path and the call count.
- `Output.total("name")`: sum of the output `name` over **all descendant leaf calls** during
  this call (a child called twice contributes twice). Raise if no descendant declares `name`
  or the units differ. Only for additive quantities (power, heat flow, mass flow); validate at
  declaration.
- `Output.ratio("a", "b")`: `a / b` of this module's own outputs; `None` when `b` is zero.
- Evaluated in declaration order; a formula may reference earlier formula outputs of the same
  module. Paths are validated when the module tree is complete (first call or an explicit
  check), with a close-match suggestion on typos.
- Implement the per-call bookkeeping on top of the existing per-call record (each module call
  records its outputs in the record of its parent call). No global state.

### 1.6 Fluid-only ports

- `Inlet` and `Outlet` accept fluid stream kinds only. Raise at declaration otherwise.
- Every current non-fluid outlet/inlet (e.g. `electricity` `PowerFlow`, `heat_loss`
  `HeatFlow`) becomes an `Output` with the same name and SI unit, computed in
  `_compute_outputs` (leaves) or with `Output.total` (composites).
- If `PowerFlow`/`HeatFlow` types are then unused, delete them.
- Results/data columns, bindings and the legacy mapping follow (`<path>.<name>` stays the
  scheme; only the kind changes). Regenerate `examples/shared/doublet_heat/` through the legacy
  bridge example if any column changes. List every rename.

### 1.7 Leaf vs composite

`module.is_leaf` is `True` when the module has no child modules. Rules (enforced by tests,
section 2 phase 5):
- Leaf: plain `Output(kind)` declarations; overrides `_compute_outputs` if it has outputs; no
  formula outputs.
- Composite: formula outputs only; does not override `_compute_outputs`.

## 2. Phases

0. **Baseline**: full `pytest`; save golden values, e2e metrics, replay/simulate results
   (full arrays, not only hashes, so relative differences can be measured) and replay timing.
1. **Base class**: `_compute_outputs`, `_call_by_name` with class-time signature validation,
   ordering, `_check_outputs`, hook signature change, `gm.no_outputs()`. Unit tests: argument
   selection by name, bad name at class definition, missing output error, ordering (formula sees
   `_compute_outputs` values, hook sees both), `no_outputs` skips everything and nests, hooks by
   name.
2. **Formula outputs**: `Output.of/total/ratio` with validation and tests (called-once rule,
   twice-called child in `total`, unit mismatch, zero denominator, typo suggestion).
3. **Leaves**: move every output out of `forward` into `_compute_outputs`; non-fluid outlets
   become outputs (1.6).
4. **Composites**: remove all output code from `forward` (plant, doublet, examples); declare
   formula outputs; `forward` keeps `# Modules` / `# Outlets` / return only. Engine, results,
   bindings, legacy and data follow; regenerate the shared example via the bridge if needed.
5. **Convention test** (`tests/unit/test_forward_structure.py`): `forward` allows only
   `# Modules` (composites) and `# Outlets` sections and contains no `self.<x> =`; every
   returned outlet is a fluid outlet; leaf/composite rules of 1.7; method order in classes:
   `__init__`, `forward`, `_compute_outputs`, then private helpers. In `__init__`, section order
   stays `# Modules`, `# Parameters`, `# Inlets`, `# Controls`, `# Boundaries`, `# States`,
   `# Outputs`, `# Outlets` (empty ones omitted).
6. **Docs and examples**: `.claude/docs/modules.md`, `conventions.md`, `AGENTS.md`, README,
   module template, examples: the new leaf and composite shapes (1.4, 1.5), the call order,
   `no_outputs`, fluid-only ports.
7. Lint + full `pytest`; compare with the baseline (1e-9 rule); replay timing before → after,
   and replay timing with `gm.no_outputs()`.

## 3. Acceptance script (run and paste output in the report)

```python
import gemini as gm

plant = ...                                  # load the shared doublet plant
s = ...                                      # a secondary stream
out = plant(secondary=s)
print(out.outputs.thermal_power, out.outputs.electricity_use, out.outputs.cop)
print(list(out.outlets))                     # fluid outlets only

esp = plant.get_submodule("...esp")          # the ESP path in the plant
print(esp.is_leaf, plant.is_leaf)            # True False
print(list(esp.outputs()))                   # listing still works

with gm.no_outputs():
    fast = plant(secondary=s)
print(dict(fast.outputs))                    # {}
assert fast.outlets.secondary_out.T == out.outlets.secondary_out.T
```

## 4. Final report (last message)

1. Implemented call order and the `_call_by_name` rules.
2. Leaf modules changed (file, class, outputs moved), and which outputs are now derived from
   fluid states vs recomputed.
3. Composite formula outputs declared (module, output, formula).
4. Non-fluid ports turned into outputs; every path/column/binding rename (old → new).
5. Any module where the structure did not fit cleanly and what you did (e.g. a child called
   more than once with `Output.of`).
6. Baseline comparison: largest relative difference per quantity; replay timing with and
   without `no_outputs`.
7. Acceptance script output.
8. Lint/test summary lines.
