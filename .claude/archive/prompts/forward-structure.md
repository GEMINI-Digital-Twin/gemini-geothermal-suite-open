# Task: One fixed structure for every `forward`

## 0. Context and rules

You are in the team repo, on the newest refactor branch (the one with the module API where
everything is declared in `__init__` with `Parameter`, `Inlet`, `Control`, `Boundary`, `Output`,
`Outlet`, outputs are assigned inside `forward`, and `forward` returns the outlets). Create
branch `refactor/forward-structure` from it. **No push, no PR.** Read `AGENTS.md`,
`.claude/docs/modules.md`, `.claude/docs/conventions.md` and every module first.

This task changes **layout only**: no physics, no numbers, no API, no names of ports, outputs or
parameters. Golden numbers, e2e metrics and replay/simulate results must stay identical.

## 1. The structure

Every `forward` (and `step` for stateful modules) in `gemini/`, `examples/` and `tests/` follows
exactly this shape, with plain comments (no dashes), in this order, empty sections omitted:

```python
def forward(self, <inlets, controls, boundaries>):
    """One-line docstring."""

    # Modules
    <calls to child modules, in flow order; only composites have this section>

    # Outputs
    self.<output> = ...
    <every declared Output is assigned here and only here>

    # Outlets
    <name> = ...
    <one local variable per declared Outlet, named exactly like the Outlet>

    outlets = dict(<name>=<name>, ...)
    return outlets
```

Rules:
1. **Section order is fixed**: `# Modules`, `# Outputs`, `# Outlets`, then the return block.
   Empty sections are omitted (leaf modules have no `# Modules`).
2. **`# Modules`** contains only calls to child modules and unpacking of their results. No
   output assignments, no outlet construction here.
3. **`# Outputs`** assigns every declared `Output` (`self.x = ...`). Intermediate helper
   variables needed only for outputs may live here. All output assignments happen in this
   section; none elsewhere in `forward`.
4. **`# Outlets`** creates one local variable per declared `Outlet`, with exactly the outlet's
   name. No output assignments here.
5. **Return block**: `outlets = dict(name=name, ...)` with the keys in the same order as the
   `Outlet` declarations in `__init__`, then `return outlets`. Nothing else after it.
6. **Always a dict**, also for modules with a single outlet (`outlets = dict(outlet=outlet)`).
   Remove the "single outlet returns the flow itself" behaviour from `Module` and its tests and
   docs, so every module returns the same shape.
7. A calculation needed by both outputs and outlets is done once in `# Outputs` (stored in an
   output or a local variable) and reused in `# Outlets`; never computed twice.
8. Small private helper methods are fine when `forward` gets long; the sections stay in
   `forward`.

Example (composite):
```python
def forward(self, secondary, m_dot, esp_frequency, injection_pressure, injection_frequency):
    """Connect the doublet limbs through the modeled surface equipment."""

    # Modules
    supply, esp_power, production_heat = self.doublet.produce(m_dot, esp_frequency)
    degassed = self.degasser(inlet=supply)
    filtered = self.filters.hot(inlet=degassed.outlets.liquid)
    exchanged = self.heat_exchanger(hot_in=filtered.outlets.outlet, cold_in=secondary)
    returned = self.filters.cold(inlet=exchanged.outlets.hot_out)
    pumped = self.injection_pump(
        suction=returned.outlets.outlet,
        pressure_setpoint=injection_pressure,
        frequency=injection_frequency,
    )
    injection_heat = self.doublet.inject(pumped.outlets.discharge)

    # Outputs
    self.electricity_use = esp_power.P + pumped.outlets.electricity.P
    self.thermal_power = exchanged.outputs.duty
    self.cop = self.thermal_power / self.electricity_use if self.electricity_use else None

    # Outlets
    secondary_out = exchanged.outlets.cold_out
    gas = degassed.outlets.gas
    electricity = PowerFlow(P=self.electricity_use)
    heat_loss = HeatFlow(Q=production_heat.Q + injection_heat.Q)

    outlets = dict(
        secondary_out=secondary_out,
        gas=gas,
        electricity=electricity,
        heat_loss=heat_loss,
    )
    return outlets
```

Example (leaf):
```python
def forward(self, suction, frequency):
    """Compute pump head and power and raise the suction pressure."""

    # Outputs
    self.flow = suction.volumetric_flow()
    self.head = pumps.head(self.flow, frequency, self.no_stages, self.head_coeff)
    self.power = pumps.power(self.flow, frequency, self.no_stages, self.power_coeff)
    self.discharge_pressure = suction.p + self.head
    ...

    # Outlets
    discharge = suction.with_(p=self.discharge_pressure)
    electricity = PowerFlow(P=self.power / self.motor_efficiency)

    outlets = dict(discharge=discharge, electricity=electricity)
    return outlets
```

Helper methods that return several flows (e.g. `Doublet.produce` / `Doublet.inject`) keep their
return shape; only `forward`/`step` follow this structure.

## 2. Steps

1. Baseline: run full `pytest`; save golden values, e2e metrics and replay/simulate result
   hashes to compare at the end.
2. Rewrite every `forward`/`step` to the structure (package modules, `Doublet`, `Sequential` if
   it has a `forward`, `DoubletHeatPlant`, example plants, test helper modules).
3. Remove the single-outlet shortcut from `Module` (rule 6); update its tests.
4. Add a convention test `tests/unit/test_forward_structure.py` that, for every registered
   module class with its own `forward`, parses the source (`ast` + comments via `tokenize`) and
   checks: section comments present in the right order (only allowed ones, no dashes);
   `# Modules` only in composites; all `self.<output> =` assignments inside `# Outputs`; one
   local per declared outlet inside `# Outlets`; the final two statements are
   `outlets = dict(...)` with keys in declaration order and `return outlets`. Clear failure
   message naming the class and the broken rule.
5. Update `.claude/docs/modules.md` and `conventions.md` with the structure, the rules and the two
   examples; update the module template/examples in docs and README if they show `forward`.
6. Lint (black/isort/flake8) and full `pytest`; compare with the baseline (identical).

Commit per step. 

## 3. Final report (last message)

1. List of rewritten `forward`/`step` methods (file and class).
2. Any module where the structure did not fit cleanly and what you did.
3. Baseline comparison (identical?).
4. Lint/test summary lines.
