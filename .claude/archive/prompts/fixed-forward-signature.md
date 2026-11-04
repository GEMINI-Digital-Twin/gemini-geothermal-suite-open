# Task: One fixed signature for `forward`, `_compute_outputs` and hooks

## 0. Context and rules

Run this **after** `inputs-from-engine` and `outputs-compute`. Work on branch `refactor`; work directly on branch `refactor` (no new branch). Commit on `refactor`; at the end `git push origin refactor`. No PR, no other branches. Read `AGENTS.md`,
`.claude/docs/*`, `gemini/core/modules/module.py`, every module, the engine step code, the
examples and the tests first.

Goal: every module has exactly the same method signatures, forever:

```python
def forward(self, inlets: Ports) -> dict[str, Stream]: ...
def _compute_outputs(self, inlets: Ports, outlets: Ports) -> None: ...
def hook(module, inlets: Ports, outlets: Ports) -> None: ...      # forward hooks
def pre_hook(module, inlets: Ports) -> None: ...                  # forward pre-hooks
```

`__call__` converts whatever the caller passes into this fixed shape. The by-name argument
passing (`_call_by_name`, per-class signature inspection) is removed.

Rules:
- Layout and calling only: physics, numbers, names of ports/outputs/parameters, results,
  bindings and data files do not change. Golden values, e2e metrics and replay/simulate results
  must be **identical** to the baseline.
- No compatibility shims; the old signatures are removed everywhere.
- black / isort / flake8 clean, full `pytest` green. Commit per phase.

## 1. Target

### 1.1 `Ports`

New small class in `gemini/core/types/` (next to the flow types), exported from `gemini`:

- Read-only mapping of port name → `Stream` (implements `collections.abc.Mapping`: `[]`,
  `in`, `len`, iteration in declaration order, `.items()`, `.keys()`, `.values()`).
- Attribute access: `inlets.suction`. An unknown name raises `AttributeError`/`KeyError` with
  the module path, the bad name and the list of valid names (close-match suggestion).
- Immutable: assignment or deletion raises.
- Cheap: no copying beyond one dict; used on every call, so keep it light (`__slots__`).

### 1.2 `Module.__call__`

```python
def __call__(self, *args, **kwargs):
    inlets, inputs = self._split_call_args(args, kwargs)   # -> Ports, dict of controls/boundaries
    with self._apply_inputs(inputs):
        for hook in self._forward_pre_hooks.values():
            hook(self, inlets)
        outlets = self._check_outlets(self.forward(inlets))  # -> Ports
        if outputs_enabled():
            self._compute_outputs(inlets, outlets)
            self._compute_formula_outputs()
            for hook in self._forward_hooks.values():
                hook(self, inlets, outlets)
            self._check_outputs()
    ...  # result building unchanged
```

Accepted call forms (all equivalent):

```python
esp(suction=s)                       # keywords
esp({"suction": s})                  # one dict / mapping / Ports as the only positional arg
esp(s)                               # positional, in inlet declaration order
esp(suction=s, frequency="50 Hz")    # control/boundary keywords still allowed (per call)
```

- Mixing a dict with inlet keywords, an unknown name, a missing inlet or a wrong flow type
  raises `TypeError` with the module path, the name and the valid names.
- Inlet validation and `fluid=` handling stay as today; only the shape passed to `forward`
  changes.
- `_check_outlets`: `forward` must return a `dict` whose keys are exactly the declared outlets
  (missing or extra keys raise with the module path); values must be the declared flow types.
  It is wrapped into `Ports` for `_compute_outputs`, hooks and the result.

### 1.3 Module code

Leaf:

```python
def forward(self, inlets):
    """Raise the suction pressure by the pump head."""

    # Outlets
    suction = inlets.suction
    flow = suction.volumetric_flow()
    head = pumps.head(flow, self.frequency, self.no_stages, self.head_coeff)
    discharge = suction.with_(p=suction.p + head)

    outlets = dict(discharge=discharge)
    return outlets

def _compute_outputs(self, inlets, outlets):
    self.flow = inlets.suction.volumetric_flow()
    self.head = outlets.discharge.p - inlets.suction.p
    self.power = pumps.power(self.flow, self.frequency, self.no_stages, self.power_coeff)
    self.electricity = self.power / self.motor_efficiency
```

Composite:

```python
def forward(self, inlets):
    """Connect the doublet through the surface equipment."""

    # Modules
    ...
    exchanged = self.heat_exchanger(hot_in=hot.outlets.outlet, cold_in=inlets.secondary)
    ...

    # Outlets
    secondary_out = exchanged.outlets.cold_out
    gas = degassed.outlets.gas

    outlets = dict(secondary_out=secondary_out, gas=gas)
    return outlets
```

- Parameter names are exactly `inlets` and `outlets`; no other parameters, no defaults, no
  `*args`/`**kwargs`.
- Reading an inlet into a local (`suction = inlets.suction`) is allowed at the top of the
  section where it is first used; no other unpacking style.
- Child calls inside composites keep the keyword form (`self.heat_exchanger(hot_in=...)`) for
  readability.
- Result objects (`out.outlets`) become `Ports` too, so `out.outlets.discharge` and
  `out.outlets["discharge"]` both work.
- `Module.forward` base raises `NotImplementedError` with the class name.
- `_compute_outputs` base stays empty with the fixed signature.

### 1.4 Engine, examples, tests, legacy helpers

- Engine (`chained_step`, `twin_step`) calls modules with a mapping of inlets
  (`module(inlet_map)`) instead of building keyword arguments.
- Every module, the plant, example plants, test helper modules and `Doublet` helpers follow the
  fixed signatures. Helper methods that are not `forward`/`_compute_outputs` keep their own
  signatures.
- Remove `_call_by_name`, the per-class signature inspection and their tests; replace with
  tests for the fixed signatures.

## 2. Phases

0. **Baseline**: full `pytest`; save golden values, e2e metrics, replay/simulate result hashes
   and replay timing.
1. **`Ports`** with unit tests (mapping behaviour, attribute access, unknown name message,
   immutability, order).
2. **`Module.__call__`**: call forms, `_check_outlets`, fixed hook/pre-hook/`_compute_outputs`
   calls; remove `_call_by_name`. Unit tests for every call form and every error in 1.2.
3. **Modules**: rewrite every `forward` and `_compute_outputs` (package, plant, examples, test
   helpers); engine calls.
4. **Convention test** (`tests/unit/test_forward_structure.py`): every module class's
   `forward` has exactly `(self, inlets)`, `_compute_outputs` exactly `(self, inlets, outlets)`;
   every `inlets.<name>` / `inlets["<name>"]` and `outlets.<name>` used in them is a declared
   inlet/outlet of that class (AST check). Clear message with class and name.
5. **Docs and examples**: `.claude/docs/modules.md`, `conventions.md`, `AGENTS.md`, README,
   module template: the fixed signatures, the call forms, `Ports`, hooks.
6. Lint + full `pytest`; compare with the baseline (identical); replay timing before → after
   (must not be worse by more than 5%).

## 3. Acceptance script (run and paste output in the report)

```python
import gemini as gm

esp = ...                                    # an ESP from the shared plant
s = ...                                      # a suction stream
a = esp(suction=s, frequency=50.0)
b = esp({"suction": s}, frequency=50.0)
c = esp(s, frequency=50.0)
assert a.outputs.head == b.outputs.head == c.outputs.head
print(a.outlets.discharge.p, a.outlets["discharge"].p, list(a.outlets))

try:
    esp(suctoin=s, frequency=50.0)
except TypeError as e:
    print(e)                                 # path, bad name, valid names

def log(module, inlets, outlets):
    print(type(module).__name__, list(inlets), list(outlets))

h = esp.register_forward_hook(log)
esp(suction=s, frequency=50.0)
h.remove()
```

## 4. Final report (last message)

1. `Ports` API and the implemented `__call__` flow.
2. Rewritten methods (file and class).
3. Anything that did not fit the fixed signatures and what you did.
4. Baseline comparison (identical?) and replay timing before → after.
5. Acceptance script output.
6. Lint/test summary lines.
