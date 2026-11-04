# Task: core data types (quantities, fluids, energy ports) and hand-written plant Modules

## 0. Context and definition of done

You are in `<ROOT>` = the `gemini/` folder of the team repo. This task runs **after** the
"modules refactor" task: the package has `gemini/core/{base,physics,modules,config,data,engine,
modes}`, a PyTorch-style `Module` base class in `core/modules/module.py`, equipment modules in
`core/modules/<category>/<name>.py`, possibly a `GraphPlant`, a GEMINI loader in `core/config/`,
run modes, golden tests and an end-to-end test on `datasets/geothermal_example`. Read
`AGENTS.md`, `.claude/docs/*` (incl. `refactor-notes.md`), `core/**`, `tests/**`, `examples/**`
before changing anything. If the actual code differs from this description, adapt and record
the difference in the report.

Goals:
1. A `core/types/` package that defines the data types of the library, the way PyTorch has
   `Tensor`, `dtype` and `Parameter`:
   - **quantities**: typed physical quantities with unit and bounds, used for every numeric field;
   - **Fluid**: the "dtype" of a stream (brine, water, glycol + composition);
   - **flows**: `Stream` (fluid), `PowerFlow` (electricity), `FuelFlow`, `HeatFlow` (heat without
     mass), so energy crossing module and plant boundaries is explicit;
   - **Profile**: time series inputs (demand, weather, prices);
   - **results**: `ModuleResult`, `Health`, `ParamRef`;
   - **Cost**: capex/opex with currency and price year.
2. Plants are **hand-written `Module` subclasses**, exactly like a PyTorch model: children created
   in `__init__`, wiring written explicitly in `forward`. Remove any automatic graph plant;
   `diagram.json` is used only to verify the wiring.
3. Everything still works end to end.

Definition of done:
- black / isort / flake8 clean; `pytest tests` fully green; golden numbers unchanged.
- Every numeric field of every module's `Params`, `Inputs`, `Outputs` uses a quantity type
  (enforced by a test). `Module.schema()` shows the unit and bounds of every field.
- Every module that consumes electricity or fuel, or exchanges heat with the environment, has the
  corresponding energy port, and the example plant passes mass- and energy-balance checks.
- `GeothermalExamplePlant` (hand-written) loads from `datasets/geothermal_example`, its wiring
  matches `diagram.json`, and all end-to-end checks from the previous task still pass.
- Docs (`AGENTS.md`, `.claude/docs/*`) describe types, energy ports and hand-written plants.

Ground rules (unchanged): branch `refactor/types`, commit per phase, **no push, no PR**,
follow `.claude/docs/*`, SI inside, no silent numeric changes (`NOTE(refactor)` + report),
`git mv` for moves, smallest clear implementation, no compatibility shims for removed names.

---

## 1. Phase 1: `core/types/` package

Create `gemini/core/types/` and move `core/base/*` into it (`git mv`), then delete
`core/base/`. Update all imports.

```
core/types/
├── __init__.py      # re-exports the public types (this is the one allowed re-export module)
├── quantities.py
├── fluid.py
├── flows.py         # Stream, PowerFlow, FuelFlow, HeatFlow
├── profile.py
├── results.py       # ModuleResult, Health, ParamRef (moved from module.py / base)
└── cost.py
```

Dependency rule: `core.types` imports only `pydantic`, `numpy`/`pandas` (profile) and
`core.physics` (for fluid properties). Nothing in `core.types` imports `core.modules`.

## 2. Phase 2: quantities (`quantities.py`)

Typed aliases built with `typing.Annotated` + Pydantic metadata. Each carries its SI unit and a
physical lower/upper bound; the unit and a `quantity` name go into the JSON schema via
`json_schema_extra`. Fields keep their own human description.

```python
def quantity(name: str, unit: str, **bounds) -> Any:
    """Return Pydantic FieldInfo metadata for a physical quantity."""
    return Field(json_schema_extra={"quantity": name, "unit": unit}, **bounds)

Pressure = Annotated[float, quantity("pressure", "Pa", ge=0)]
PressureDifference = Annotated[float, quantity("pressure_difference", "Pa")]
Temperature = Annotated[float, quantity("temperature", "K", gt=0)]
TemperatureDifference = Annotated[float, quantity("temperature_difference", "K")]
MassFlow = Annotated[float, quantity("mass_flow", "kg/s")]          # signed: <0 = reverse
VolumeFlow = Annotated[float, quantity("volume_flow", "m3/s")]
Power = Annotated[float, quantity("power", "W")]
Energy = Annotated[float, quantity("energy", "J")]
Length = Annotated[float, quantity("length", "m", ge=0)]
Area = Annotated[float, quantity("area", "m2", ge=0)]
Volume = Annotated[float, quantity("volume", "m3", ge=0)]
Angle = Annotated[float, quantity("angle", "rad")]
Density = Annotated[float, quantity("density", "kg/m3", gt=0)]
Viscosity = Annotated[float, quantity("viscosity", "Pa.s", gt=0)]
SpecificHeat = Annotated[float, quantity("specific_heat", "J/kg/K", gt=0)]
ThermalConductivity = Annotated[float, quantity("thermal_conductivity", "W/m/K", gt=0)]
HeatTransferCoefficient = Annotated[float, quantity("heat_transfer_coefficient", "W/m2/K", ge=0)]
ThermalConductance = Annotated[float, quantity("thermal_conductance", "W/K", ge=0)]   # UA
Permeability = Annotated[float, quantity("permeability", "m2", gt=0)]
ProductivityIndex = Annotated[float, quantity("productivity_index", "m3/s/Pa", gt=0)]
Frequency = Annotated[float, quantity("frequency", "Hz", gt=0)]
Duration = Annotated[float, quantity("duration", "s", ge=0)]
Fraction = Annotated[float, quantity("fraction", "-", ge=0, le=1)]
Efficiency = Annotated[float, quantity("efficiency", "-", gt=0, le=1)]
Ratio = Annotated[float, quantity("ratio", "-", ge=0)]
Dimensionless = Annotated[float, quantity("dimensionless", "-")]
CorrosionRate = Annotated[float, quantity("corrosion_rate", "m/s", ge=0)]  # see note below
Money = Annotated[float, quantity("money", "currency")]
```
Add more only when a module needs one (e.g. `Roughness = Length`). Notes:
- Corrosion/erosion rates are mm/yr in the literature; keep the physics functions as they are
  and expose module outputs in SI (`m/s`) **or** decide on mm/yr as an explicit, documented
  exception. Pick one, apply it everywhere, NOTE it.
- Lists of quantities are allowed (`list[Length]`); polynomial coefficients stay
  `list[float]` and are listed in an explicit allow-list of non-quantity numeric fields with a
  reason (e.g. ESP `head_coeff`).

Apply the types to **every** `Params`, `Inputs`, `Outputs` field of every module, to `Stream`,
`Health.score`, `ParamRef.bounds` where relevant. Remove now-redundant `[unit]` from
descriptions only if `schema()` exposes the unit; descriptions stay.

Test `tests/core/types/test_quantities.py`: bounds enforced; schema contains `unit` and
`quantity`. Test `tests/core/modules/test_field_types.py`: walks every registered module and
fails on any numeric field (`float`, `int` that is a physical value) not typed with a quantity
and not in the allow-list.

`Module.schema()` output per field: `{name, quantity, unit, bounds, description, default}`.

## 3. Phase 3: `Fluid` as the stream dtype (`fluid.py`)

```python
class Fluid(BaseModel):
    """What a stream is made of (the 'dtype' of a Stream)."""
    model_config = ConfigDict(frozen=True)
    kind: Literal["brine", "water", "glycol_water"] = "brine"
    salinity: Fraction = 0.0              # mass fraction of dissolved salts [-]
    co2_mass_fraction: Fraction = 0.0     # dissolved CO2 [-]
    gas_mass_fraction: Fraction = 0.0     # free gas [-] (GMF in the old PVT model)
    glycol_fraction: Fraction = 0.0       # for glycol_water [-]
    property_model: Literal["constant_stp"] = "constant_stp"   # extend later (e.g. IAPWS)

    def properties(self, p: Pressure, T: Temperature) -> FluidProperties: ...
```
- `properties` dispatches to `core.physics.fluid` (`constant_stp` = the existing
  `ConstantWater`, so golden numbers do not change). Cache property-model instances.
- Predefined constants: `BRINE = Fluid()`, `WATER = Fluid(kind="water")`,
  `GLYCOL_30 = Fluid(kind="glycol_water", glycol_fraction=0.3)` (glycol uses constant
  properties from a cited source; NOTE the values).
- `Stream.fluid` becomes `Fluid` (default `BRINE`) instead of a string. Remove the old string
  registry `get_fluid` if nothing else needs it.
- Corrosion helpers in modules read CO2 and salinity from `stream.fluid` instead of separate
  inputs where the old code allowed it.
- The GEMINI loader sets the brine composition from `.param` data when present
  (`liquid_density`, `liquid_viscosity` overrides, CO2 if any), else defaults.

## 4. Phase 4: energy flows and ports (`flows.py`)

```python
class Stream(BaseModel):          # unchanged fields, fluid is now Fluid
    m_dot: MassFlow; T: Temperature; p: Pressure; fluid: Fluid = BRINE

class PowerFlow(BaseModel):       # electricity
    model_config = ConfigDict(frozen=True)
    P: Power                      # >0 = consumed by the module from the grid

class FuelFlow(BaseModel):
    model_config = ConfigDict(frozen=True)
    P: Power                      # chemical energy rate (LHV) consumed
    fuel: Literal["natural_gas", "hydrogen", "biogas"] = "natural_gas"

class HeatFlow(BaseModel):        # heat without mass
    model_config = ConfigDict(frozen=True)
    Q: Power                      # >0 = released by the module
    T: Temperature | None = None  # temperature level, when meaningful
```

Ports become typed. Change the class attributes from tuples to mappings:
```python
inlets: ClassVar[dict[str, type[Flow]]] = {"suction": Stream}
outlets: ClassVar[dict[str, type[Flow]]] = {"discharge": Stream, "electricity": PowerFlow}
```
`Flow = Stream | PowerFlow | FuelFlow | HeatFlow`. `Module.__call__` checks key sets **and
types**. Update `schema()` to list ports with their type.

Convention (write it in `.claude/docs/modules.md`):
- Energy ports are **outlets that report** what the module draws or releases; the module computes
  them in `forward`. Callers never have to supply electricity.
  - `electricity: PowerFlow` = electric power drawn from the grid.
  - `fuel: FuelFlow` = fuel drawn.
  - `heat_loss: HeatFlow` = heat released to the environment (ground, air).
- Fluid streams carry heat between modules; `HeatFlow` is only for exchanges with the
  environment or with modules that have no fluid on that side.

Add energy ports:
- `ESP`: `electricity` (= predicted power / motor efficiency param, default 1.0 so numbers stay;
  NOTE). Keep the `power` output too.
- `InjectionPump`, `BoosterPump` (if it has power), `Boiler` (`electricity` for electric fuel,
  `fuel` for gas; both declared, zero when unused, or declare per instance: choose the simpler
  valid option and NOTE it).
- `ProductionWell`, `InjectionWell`: `heat_loss` = m_dot·cp·(T_in − T_out) from the pipe-path
  temperature change.
- `HeatExchanger`: no energy port (both sides are streams); add `heat_loss` only if you model it
  (default 0, not needed).
- Filter, Degasser, Blowdown: none.

Plant-level helpers in `core/modules/module.py` (or a small `core/modules/balance.py`):
- `collect_flows(result_tree) -> {"electricity": W, "fuel": W, "heat_loss": W}` summed over all
  descendants of a composite result.
- `energy_balance(plant, result) -> dict` with: heat delivered, electricity, fuel, losses,
  and the residual `sum(in) − sum(out)`.
- `mass_balance(...)` per module and per plant.

Tests: every module conserves mass across fluid ports; energy residual of each module < 1e-6
relative; ESP electricity equals its `power` output with default motor efficiency.

## 5. Phase 5: `Profile` and `Cost`

### `profile.py`
```python
class Profile(BaseModel):
    """Time series input: demand, weather, prices."""
    name: str
    quantity: str            # e.g. "power", "temperature", "money_per_energy"
    unit: str                # SI unit of `values`
    index: list[datetime]    # strictly increasing
    values: list[float]

    @classmethod
    def from_csv(cls, path, column, unit_in, time_column="Timestamp", tz=None) -> "Profile": ...
    @classmethod
    def constant(cls, name, quantity, unit, value, start, periods, step: timedelta) -> "Profile": ...
    def at(self, t: datetime) -> float: ...           # step-wise (previous value), documented
    def resample(self, step: timedelta, how: Literal["mean", "sum", "first"]) -> "Profile": ...
    def to_series(self) -> pd.Series: ...
    def __len__(self): ...
```
Conversion from `unit_in` to SI uses `units.to_si`. `modes/scenario.py` accepts a dict of
profiles (`{"heating_demand": Profile, "ambient_T": Profile, ...}`) and builds the per-step
inputs from them. Update its test to use profiles.

### `cost.py`
```python
class Cost(BaseModel):
    capex: Money = 0.0                     # one-off investment
    opex_fixed: Money = 0.0                # per year
    opex_variable: float = 0.0             # money per J of output (document unit)
    currency: str = "EUR"
    price_year: int
    source: str                            # citation of the cost correlation
```
`Module.capex()` returns `Cost | None` (was `float | None`); a composite's `cost()` sums its
children (same currency and price year, else `ValueError`). No cost correlations need to exist
yet; add one test with a fake module.

## 6. Phase 6: hand-written plant Modules

Remove the automatic graph plant (`GraphPlant` / `core/modules/plant.py` or whatever the
previous task created) and replace it with explicit classes:

```
core/modules/plants/
├── __init__.py
├── doublet.py               # Doublet: reusable geothermal source block
└── geothermal_example.py    # GeothermalExamplePlant: the GEMINI example, hand-wired
```

Pattern (exactly like `torch.nn.Module` models):
```python
class Doublet(Module):
    """Production reservoir -> production well (+ ESP) -> surface; reinjection side."""
    name = "doublet"
    category = "plant"
    inlets = {"return": Stream}
    outlets = {"supply": Stream, "electricity": PowerFlow}

    class Params(BaseModel): ...              # composite: usually empty
    class Inputs(BaseModel):
        reservoir: ProductionReservoir.Inputs
        esp: ESP.Inputs

    def __init__(self, reservoir, well, esp, injector, sink):
        super().__init__()
        self.reservoir = reservoir            # children registered by __setattr__
        self.well = well
        self.esp = esp
        self.injector = injector
        self.sink = sink

    def forward(self, inputs, streams_in):
        s = self.reservoir(inputs.reservoir).streams["sandface"]
        s = self.well.intake_conditions(s)
        esp = self.esp(inputs.esp, suction=s)
        s = self.well.wellhead_from_discharge(esp.streams["discharge"])
        inj = self.injector(wellhead=streams_in["return"])
        self.sink(sandface=inj.streams["bottom"])
        return ModuleResult(self.Outputs(), {"supply": s, "electricity": esp.streams["electricity"]})
```
`GeothermalExamplePlant` wires the GEMINI example in code following `diagram.json`
(read it: reservoir → production well → ESP → filter → heat exchanger primary → filter →
injection pump → injection well → reservoir; place the degasser where the diagram puts it).
Its `Inputs` hold the production rate, ESP frequency, injection pump setpoint, secondary-side
inlet stream. Its `Outputs` hold thermal power delivered, total electricity, COP of the doublet
(heat / electricity).

Child construction from config:
- `PlantConfig` gets `plant_type: str` (registry name of the plant class) and keeps
  `modules: dict[child_path, ModuleConfig]` and `bindings` (keyed by child path, e.g.
  `"doublet.esp"`). Remove `links` (wiring lives in code).
- Each plant class has `@classmethod from_config(cls, config: PlantConfig, at=None)` that builds
  its children from `config.modules` with the registry (params valid at `at`).
- The GEMINI loader maps diagram node file stems to child paths with a table owned by the plant
  class: `GeothermalExamplePlant.GEMINI_NODES = {"reservoir_c1b5": "doublet.reservoir",
  "esp_1ee3": "doublet.esp", ...}` (fill it from `diagram.json`).

Wiring check (replaces the graph builder): `core/config/wiring.py`
- `trace_wiring(plant, inputs) -> set[(src_path, src_port, dst_path, dst_port)]`: run one
  `forward` with forward hooks that tag every output `Stream` object with its producer and record
  which module receives it (identity-based).
- `check_against_diagram(traced, diagram_json, node_map) -> list[str]` returns mismatches.
- Test: the example plant's traced wiring matches every `devs.Link` in `diagram.json` (after the
  port mapping table). Zero mismatches.

Update the run modes, examples and e2e test to use `GeothermalExamplePlant`. All previous
reconciliation thresholds still apply. Add to the e2e test:
- plant mass balance closes (|residual| < 1e-6 relative) on 100 sampled rows;
- energy balance closes;
- total electricity ≈ `ESP_PowerDraw + InjectorPump_PowerDraw` (median rel. error < 10% after
  the usual investigation rules).

Add `examples/10_custom_plant.py`: a 40-line example defining a small custom plant Module in user
code (doublet + heat exchanger + boiler) and running it for one step, to show the PyTorch-style
pattern.

## 7. Phase 7: docs

- New `.claude/docs/types.md`: the types table (PyTorch analogy: `Tensor` → `Stream`,
  `dtype` → `Fluid`, `Parameter` → quantity-typed `Params` fields), when to add a quantity,
  energy-port convention, `Profile`, `Cost`.
- `.claude/docs/modules.md`: typed ports, energy ports, hand-written plants
  (`__init__` builds children, `forward` wires them), `from_config`, `GEMINI_NODES`, wiring check.
- `conventions.md`: dependency rule
  `core.physics` ← `core.types` ← `core.modules` ← `core.config` / `core.modes` / `core.engine`
  ← `design` / `optim` ← `agentic`; numeric fields must use quantity types.
- `AGENTS.md`: tree and links updated. README quickstart updated.

## 8. Final report (last message)

1. Final tree of `gemini/core/` (two levels) and `tests/`.
2. Moved/deleted/renamed paths.
3. The quantity allow-list (numeric fields not typed) with reasons.
4. Energy ports per module, and the energy/mass balance results on the example.
5. E2E reconciliation table (previous metrics + electricity), before vs after this task.
6. Wiring check result; the `GEMINI_NODES` table.
7. All new `NOTE(refactor)`s and decisions not covered here.
8. Lint/test summary lines.
