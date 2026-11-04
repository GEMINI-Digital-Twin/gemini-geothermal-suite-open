# Task: restructure the GEMINI suite into the `gemini` Python package

## 0. Context and ground rules

You are working in the GEMINI Geothermal Suite (TNO's open-source geothermal digital twin). In the
team repo it lives under `gemini/`; call that folder `<ROOT>` and run everything from there. If the
suite sits at the repo root instead, the root is `<ROOT>`.

Today the code is split into `src/gemini_model` (physics models), `src/gemini_framework` (a
time-series monitoring runtime: plant, units, calculation modules, database drivers),
`src/gemini_application` (analysis apps), `src/gemini_interface` (Flask web app) and
`src/gemini_documentation` (Sphinx). We are turning it into one clean, installable Python package
named `gemini`, organised around **components** (one file per piece of plant equipment) on top of a
shared **core** (base classes, generic physics, plant, data, engine).

Ground rules:
- Work on a new branch, e.g. `refactor/gemini-package`. Commit at the end of every phase with a
  descriptive message. **Do not push, do not open a PR.** Stop at the end and write the report
  described in section 9.
- Keep the repo style: black (line length 100), isort (profile black), flake8 with
  flake8-docstrings. Every public module, class and function has a docstring; numpy-style
  "Parameters / Returns" sections with units, like the existing code.
- Use `git mv` for every move so history follows the files.
- **Do not silently change numerical behaviour.** If you find something that looks like a bug,
  keep the current behaviour, add a `# NOTE(refactor): ...` comment, and list it in the report.
- SI units everywhere inside the package: K, Pa, kg/s, m³/s, m, W, J. Conversions happen only at
  the edges (reading `.param`/CSV data, plots, examples), always through
  `gemini/core/physics/units.py`.
- Python 3.11, Pydantic v2.
- When something in this prompt conflicts with what the code actually does, trust the code, make
  the smallest sensible decision, and record it in the report.

Read before starting: `pyproject.toml`, all of `src/gemini_model/`, all of `src/gemini_framework/`,
`src/gemini_application/wims/` and the other `src/gemini_application/*` files that import
`gemini_model`, all of `unit_test/`, `gemini-project/geothermal_example/` (every `.param`,
`plant.conf`, `diagram.json`, `well_trajectory.csv`), and the header of
`dataset/geothermal_example_dataset.csv`.

---

## 1. Target layout

```
<ROOT>/
├── gemini/
│   ├── __init__.py                 # version + short package docstring
│   ├── core/
│   │   ├── __init__.py
│   │   ├── base/
│   │   │   ├── component.py        # Component base class, Health
│   │   │   ├── stream.py           # Stream
│   │   │   ├── unit.py             # from gemini_framework/abstract/unit_abstract.py
│   │   │   └── unit_module.py      # from gemini_framework/abstract/unit_module_abstract.py
│   │   ├── physics/
│   │   │   ├── constants.py
│   │   │   ├── units.py
│   │   │   ├── fluid.py
│   │   │   ├── hydraulics.py
│   │   │   ├── heat_transfer.py
│   │   │   ├── geometry.py
│   │   │   ├── chemistry.py
│   │   │   ├── corrosion.py
│   │   │   └── erosion.py
│   │   ├── plant/
│   │   │   ├── plant.py            # from gemini_framework/framework/plant.py
│   │   │   ├── loader.py           # from gemini_framework/framework/boot_plant.py
│   │   │   └── param_mapping.py    # new: GEMINI .param keys -> component Params
│   │   ├── data/                   # gemini_framework/database/** + database abstracts
│   │   ├── engine/
│   │   │   ├── loop.py             # from gemini_framework/framework/loop.py
│   │   │   ├── mainmodule.py       # from gemini_framework/framework/mainmodule.py
│   │   │   ├── runner.py           # from gemini_framework/app.py (no __main__ env magic)
│   │   │   ├── registry.py         # new, phase 7
│   │   │   └── twin_modules/       # old framework calculation modules, rewritten (phase 6)
│   │   └── modes/__init__.py       # empty for now: live / history / scenario come later
│   ├── components/
│   │   ├── __init__.py
│   │   ├── subsurface/  reservoir.py  productionwell.py  injectionwell.py
│   │   ├── pumps/       esp.py  injectionpump.py  boosterpump.py
│   │   ├── treatment/   degasser.py  filter.py  blowdown.py
│   │   └── heat/        heatexchanger.py  boiler.py
│   ├── design/__init__.py          # docstring only: "Design alternatives, sizing, economics."
│   ├── optim/__init__.py           # docstring only: "Optimisation on top of the engine."
│   └── agentic/__init__.py         # docstring only: "LLM agents that drive design, optim, core."
├── tests/                          # mirrors gemini/
├── datasets/geothermal_example/    # csv + .param + plant.conf + diagram.json + trajectory
├── examples/
├── docs/                           # Sphinx API reference only
├── pyproject.toml
├── README.md
├── CHANGELOG.md
└── LICENSE
```

Hard rules for `components/`:
- Exactly **one `.py` file per component** at `components/<category>/<name>.py`. No per-component
  folders, no `physics.py`/`twin.py` split. Each category folder has an `__init__.py` that
  re-exports its component classes.
- Only the components listed above. Do **not** create files for future components (heat pump,
  chillers, storage, network, demand); they come in a later task.
- A component file contains only physics and twin hooks specific to that equipment. Anything that
  could apply to another component (pipe flow, heat loss, corrosion, fluid properties, unit
  conversion) lives in `core/physics/` and is imported.
- Component code never contains sensor tag names (`ESP_freq`, `esp_flow`, ...). Tag mapping is
  plant configuration.

---

## 1b. Phase −1: write the conventions first

Before any code change, create the convention docs below **with exactly this content** (fix only
paths/names that turn out different in the code), then follow them for the rest of the task.
Commit them as the first commit.

Files:
- `<ROOT>/.claude/docs/conventions.md` — general implementation conventions.
- `<ROOT>/.claude/docs/components.md` — how to write and change a component.
- `<ROOT>/.claude/docs/physics.md` — rules for `core/physics`, units and references.
- `<ROOT>/.claude/docs/testing.md` — tests and validation commands.
- `<ROOT>/AGENTS.md` — short entry point for coding agents (create it; if one exists, add to it).
  It must contain a one-paragraph description of the package, the layout tree from section 1
  (two levels), and a "Read before coding" list linking every file in `.claude/docs/` with
  relative links (e.g. `[Conventions](.claude/docs/conventions.md)`).
- `<ROOT>/CLAUDE.md` — a single line: `See [AGENTS.md](AGENTS.md).`

### `.claude/docs/conventions.md`

````markdown
# Implementation Conventions

## General rules

- Solve the requested task with the smallest clear implementation.
- Do not add abstractions, base classes, factories, configuration, or layers for hypothetical
  future needs. The only shared base classes are the ones in `gemini/core/base`.
- Prefer direct, readable code over clever or generic code.
- Keep functions focused, but do not split a short calculation into unnecessary wrappers.
- Reuse an existing pattern before introducing a new one. A new component looks like the
  existing ones.
- Add comments only when they explain a decision, an assumption, or a reference that the code
  cannot express. Physics formulas get the reference (paper, standard, page) in the docstring.
- Keep code compatible with black, isort (profile black) and flake8 with docstrings, line length
  100, as configured in `pyproject.toml`.
- Never change numerical behaviour silently. If you change a result, say why in the commit and
  update the affected test values on purpose.

## Package layout

- `gemini/core` holds what every part uses: `base` (Component, Stream, Unit, UnitModule),
  `physics` (generic physics and units), `plant`, `data`, `engine`, `modes`.
- `gemini/components/<category>/<name>.py` holds exactly one component per file. No
  per-component folders, no helper files next to components.
- `gemini/design`, `gemini/optim`, `gemini/agentic` build on `core` and `components`.
- Dependencies flow one way: `core` ← `components` ← `design` / `optim` ← `agentic`.
  `core` never imports `components` except through the registry's discovery;
  a component never imports another component.

## Imports

- Order imports as standard library, third-party packages, then local modules.
- Import physics modules and qualify their members: `hydraulics.darcy_weisbach_dp(...)`,
  `units.bar_to_pa(...)`, instead of importing many names.
- Direct symbol imports are fine for small, stable names: `Component`, `Stream`, `Health`,
  Pydantic's `BaseModel` and `Field`.
- Do not create re-export modules only to shorten imports. Category `__init__.py` files only
  re-export the component classes of that category.

Example:

```python
from pydantic import BaseModel, Field

from gemini.core.base.component import Component
from gemini.core.base.stream import Stream
from gemini.core.physics import hydraulics, units
```

## Units

- Everything inside the package is SI: K, Pa, kg/s, m³/s, m, W, J, s.
- Convert only at the edges (reading `.param` files or CSV data, examples, plots), always with
  `gemini.core.physics.units`. No inline magic numbers such as `* 1e5`, `+ 273.15`, `/ 3600`.
- Every Pydantic field states its unit in `description`, e.g. `"Wellhead pressure [Pa]"`; use
  `[-]` for dimensionless values.

## Errors

- Validate inputs with Pydantic models; do not write manual `if key not in dict` checks.
- Raise `ValueError` for invalid physical states (negative flow where not allowed, unknown
  correlation name) with a message naming the component and the value.
- Raise `NotImplementedError` only for declared placeholder components.
- Never `print` errors and continue; never swallow exceptions in physics code.

## Data and configuration

- Sensor tag names and plant-specific settings live in plant configuration (`.param`,
  `plant.conf`), never in component code.
- Conversion from GEMINI `.param` keys to component parameters lives only in
  `gemini/core/plant/param_mapping.py`.

## Validation

Run after every change:

```bash
poetry run black --check gemini tests
poetry run isort --check-only gemini tests
poetry run flake8 gemini tests
poetry run pytest tests
```
````

### `.claude/docs/components.md`

````markdown
# Writing a Component

A component is one piece of plant equipment (pump, well, heat exchanger, ...). It lives in
`gemini/components/<category>/<name>.py` and contains only physics and monitoring logic specific
to that equipment.

## Checklist

1. Subclass `gemini.core.base.component.Component`.
2. Set `name` (unique snake_case), `category` (folder name) and a one-sentence `description`.
   The registry and the AI agent read these.
3. Declare ports: `inlets` and `outlets` as tuples of port names. Ports carry `Stream` objects.
   Flow, temperature and pressure arrive through inlet streams, not as separate inputs.
4. Define three nested Pydantic models:
   - `Params`: fixed design data (stages, curves, UA, geometry). Validated once at construction.
   - `Inputs`: per-step operating inputs that are not streams (frequency, setpoints).
   - `Outputs`: per-step results.
   Every field has `description="... [unit]"` and constraints (`gt`, `ge`, `min_length`) where
   physics demands them.
5. Implement `compute(inputs, streams_in) -> (outputs, streams_out)`. It must be pure: no I/O,
   no database, no global state, same inputs give the same outputs.
6. Stateful equipment (storage, slowly depleting reservoir) sets `stateful = True` and
   implements `initial_state()` and `step(state, inputs, streams_in, dt)`.
7. Twin hooks, when meaningful:
   - `soft_sensors`: `Outputs` fields that replace missing measurements.
   - `calibratable`: `Params` fields history matching may fit.
   - `health(predicted, measured) -> Health`: compare prediction with measurement, return a
     score in [0, 1], an alarm flag and a short message. Thresholds are `Params` fields with
     sensible defaults, not constants in the code.
8. Optional `capex()` when a cost correlation exists; cite the source.
9. Generic physics (pipe flow, heat loss, heat-exchanger effectiveness, corrosion, erosion,
   fluid properties, unit conversion) is imported from `gemini.core.physics`, never copied into
   the component.
10. Add a mapper in `core/plant/param_mapping.py` if the component appears in GEMINI `.param`
    files.
11. Add `tests/components/<category>/test_<name>.py` (see testing.md).

## Do not

- Import another component. Chains of components are built by the engine or by the caller.
- Put sensor tag names, file paths or database access in a component.
- Create a component file before the equipment is actually modelled or placed in a plant.
- Add helper modules next to a component; shared code belongs in `core/physics`.

## Skeleton

```python
"""Heat pump component.

Raises the temperature of the secondary loop using electricity.
Reference: <source>.
"""

from pydantic import BaseModel, Field

from gemini.core.base.component import Component
from gemini.core.base.stream import Stream


class HeatPump(Component):
    """Electric compression heat pump."""

    name = "heatpump"
    category = "heat"
    description = "Electric heat pump that lifts low-temperature heat to supply temperature."
    inlets = ("source_in", "sink_in")
    outlets = ("source_out", "sink_out")
    soft_sensors = ("cop",)
    calibratable = ("carnot_efficiency",)

    class Params(BaseModel):
        capacity: float = Field(..., gt=0, description="Nominal heating capacity [W]")
        carnot_efficiency: float = Field(0.5, gt=0, le=1, description="Fraction of Carnot COP [-]")

    class Inputs(BaseModel):
        supply_T: float = Field(..., gt=0, description="Sink outlet setpoint [K]")

    class Outputs(BaseModel):
        heat: float = Field(..., description="Heat delivered to the sink [W]")
        power: float = Field(..., description="Electric power [W]")
        cop: float = Field(..., description="Coefficient of performance [-]")

    def compute(self, inputs, streams_in):
        ...
```
````

### `.claude/docs/physics.md`

````markdown
# Core Physics Rules

`gemini/core/physics` holds physics that more than one component can use.

- One module per topic: `units`, `constants`, `fluid`, `geometry`, `hydraulics`,
  `heat_transfer`, `chemistry`, `corrosion`, `erosion` (add `thermodynamics` when needed).
- Plain typed functions, SI in and out. Use small Pydantic models or frozen dataclasses only for
  structured results (`PathResult`, `FluidProperties`, `PipeSection`).
- Every function docstring lists parameters and returns with units and gives the reference
  (author, year, title or standard, page/equation).
- Correlations that need non-SI units internally (Beggs–Brill, ESP curves, erosion) convert at the
  function boundary with `units`.
- Selecting between correlations uses a `Literal[...]` argument and raises `ValueError` on an
  unknown name.
- No state, no I/O, no logging inside physics functions.
- Do not add standalone `utils.py` or `helpers.py`; a function belongs to a topic module.
````

### `.claude/docs/testing.md`

````markdown
# Testing

- Tests mirror the package: `tests/core/physics/test_hydraulics.py`,
  `tests/components/pumps/test_esp.py`.
- Test behaviour, physical limits and failure handling. Do not add tests that only repeat the
  implementation.
- Every component has tests for: parameter validation (valid example, missing field, wrong type,
  out-of-range value), port contract, `schema()` serialisation, reference numbers, and `health`
  thresholds when implemented.
- Reference numbers come from a documented source: golden values captured from the original
  GEMINI models (`tests/golden/golden_values.json`), a textbook example, or measured data in
  `datasets/`. Write the source next to the expected value.
- Physics functions get at least one energy- or mass-balance or limiting-case check (zero flow,
  equal temperatures, infinite UA).
- Tests that need external services (InfluxDB, AVEVA) are skipped when credentials are missing.
- Examples in `examples/` are run by `tests/test_examples.py`.

Validation commands:

```bash
poetry run black --check gemini tests
poetry run isort --check-only gemini tests
poetry run flake8 gemini tests
poetry run pytest tests
```
````

---

## 2. Phase 0: golden numbers (before touching anything)

Write a throw-away script `tests/golden/capture_golden.py` that imports the **old** modules and
records outputs for a fixed set of inputs into `tests/golden/golden_values.json`:
- `ESP.calculate_output` for 3 (flow, frequency) points using the parameters in
  `gemini-project/geothermal_example/esp_1ee3.param`.
- `IPR` (production and injection), `injectivity_index`, `reservoir_pressure_estimation` (a small
  synthetic array), `reservoir_pressuredrop`.
- `DPDT` for the production well (direction "up") and injection well ("down") built from the
  example trajectory/tally, with `PVTConstantSTP`.
- `DarcyWeisbach.calculate_dp`, `BeggsBrill.calculate_dp`, `TemperatureDrop.calculate_dt`.
- `CO2Corrosion` for NORSOK, DLM, DLD (and the `_opt` variants), the CO2 partial-pressure model.
- `ErosionModel` for DNV, OKA, TULSA and API.

Commit the JSON and a test `tests/golden/test_golden.py` that later phases will point at the new
API. Every phase after this must keep these numbers within `rel=1e-9` (or exactly, for strings).

## 3. Phase 1: move, salvage, delete

1. `git mv` the code into the layout above (old files can stay temporarily as they are inside the
   new folders; phases 2–6 rewrite them).
2. **Salvage hidden physics** from `src/gemini_application` before deleting it:
   - `wims/common.py`: `build_trajectory_geometry`, `get_tally_from_well_parameters`,
     `get_esp_joint_start_idx`, `get_esp_depth_m` → pure functions in `core/physics/geometry.py`
     (strip anything that reads a `unit` object: take plain tables/numbers instead).
   - `wims/corrosion_from_prod_data.py`: the per-interval wall-loss integration
     (rate [mm/yr] × duration [s] / seconds-per-year, cumulated) → `wall_loss()` in
     `core/physics/corrosion.py`. Drop pandas plumbing, change-point detection, plotting, I/O.
   - `wims/corrosion_model.py`, `wims/erosion_model.py`, `wims/erosion_from_*.py`: copy any formula
     that is not already in `gemini_model` into `core/physics/corrosion.py` / `erosion.py`.
   - `esp/esp.py` (`calibrate_esp_head_simple`, `calculate_pump_head_curve`): keep the head-curve
     calibration logic as a classmethod `ESP.fit_head_coefficients(...)` stub with the algorithm
     ported (phase 5), since history matching will use it.
3. Delete: `src/gemini_application/`, `src/gemini_interface/`, `ci/`, `docker-compose.yml`,
   `.env.template`, `gemini-project/_template` (unless the loader needs it), and every page of
   `src/gemini_documentation/source/` that is not API/source-code reference (installation, login,
   applications, grafana, RAG, about/overview, glossary, animations/images used only by those).
   Move what remains to `docs/` and make `docs/conf.py` autodoc `gemini`.
4. `unit_test/` → `tests/`, mirroring the package. `dataset/*.csv` and
   `gemini-project/geothermal_example/*` → `datasets/geothermal_example/`.
5. `pyproject.toml`:
   - make the package installable: `packages = [{ include = "gemini" }]`, remove
     `package-mode = false`;
   - remove dependencies used only by deleted code. Check each with grep before removing. Expected
     candidates: Flask*, werkzeug, flask-admin, celery, flower, redis, pymongo, pymysql,
     langchain*, ollama, chromadb, GitPython, openpyxl, langid, pypdf, scikit-learn, joblib,
     matplotlib, ruptures, lasio, cryptography, python-dotenv, requests;
   - keep numpy, scipy, pandas, pytz, influxdb-client, adh-sample-library-preview (data drivers);
   - add `pydantic = "^2"`.
6. `.github/workflows/`: inline the old `ci/linux` commands (`pip install poetry`,
   `poetry install`, `poetry run flake8 gemini tests`, `poetry run black --check gemini tests`,
   `poetry run isort --check-only gemini tests`, `poetry run pytest tests`). Docs workflow builds
   `docs/` and deploys only on `main`.
7. Fix imports so the old classes still import from their new locations; run lint + tests
   (including golden). Commit.

## 4. Phase 2: `core/physics/` (generic physics)

Every function: pure, typed, SI in/out, docstring with units and reference (keep the references
already in the code: Swamee–Jain 1976, Shoham p.59, NORSOK M-506, de Waard–Lotz 1991/1995,
DNV RP O501, Tarek Ahmed, TNO 2022 R11363...).

### `units.py`
Named conversions replacing every inline magic number in the package. grep for `1e5`, `273.15`,
`3600`, `9.869233e-16`, `3.048e-1`, `1.601846e1`, `1e-3`, `543439`, `2988.3`, `745.7`, `31536000`,
`365.25`. At least:
`bar_to_pa`, `pa_to_bar`, `c_to_k`, `k_to_c`, `m3h_to_m3s`, `m3s_to_m3h`, `md_to_m2`,
`m3s_to_bbl_per_day`, `ft_head_to_pa`, `bhp_to_w`, `m_to_ft`, `ft_to_m`, `kgm3_to_lbmft3`,
`pas_to_cp`, `nm_to_dyne_cm`, `SECONDS_PER_YEAR`. Each with a one-line docstring and a unit test
(round trips).

### `constants.py`
`G = 9.81` (m/s²; this is what the code uses today), `G_FT = 32.17405` (Beggs–Brill), and any other
constant you find duplicated.

### `fluid.py`
- `FluidProperties` (Pydantic or frozen dataclass): `rho_l, rho_g, gmf, mu_l, mu_g, cp_l, cp_g,
  k_l, k_g, sigma` with units in field descriptions.
- `ConstantWater`: port of `PVTConstantSTP` with identical defaults and the same override keys
  (`RHOL`, `VISL`, ...), method `properties(p, T) -> FluidProperties`.
- `get_fluid(name: str = "brine", **overrides)`: tiny registry mapping `Stream.fluid` names to a
  property model (`"brine"` and `"water"` → `ConstantWater` for now). Temperature-dependent
  properties come later; design the API so they can be added without touching components.

### `geometry.py`
- `PipeSection`: `length [m]`, `inclination [rad]`, `inner_diameter [m]`, `roughness [m]`
  (note: the old DPDT comment says roughness is "mm"; check what the example `.param` actually
  stores and convert at the edge if needed, NOTE it).
- `PipePath`: ordered list of sections + helpers (`total_length`, `true_vertical_depth`,
  `index_at_measured_depth(md)`).
- `build_path(trajectory_table, tally_table) -> PipePath` and `esp_section_index(path, esp_depth)`
  ported from `wims/common.py`, plus `load_trajectory_csv(path)` for `well_trajectory.csv`.

### `hydraulics.py`
- `darcy_weisbach_dp(velocity, rho, inclination, mu, diameter, roughness, length) -> (dp_fric, dp_grav)`
  (port, Swamee–Jain friction factor).
- `beggs_brill_dp(us_g, us_l, rho_g, rho_l, inclination, mu_g, mu_l, sigma, diameter, roughness,
  length) -> (dp_fric, dp_grav)` (port; internal US-unit conversions via `units.py`).
- `hydrostatic_dp(rho, height)`.
- `pipe_path_profile(path, stream, fluid, direction: Literal["up","down"], u_value,
  t_ambient, correlation="darcy_weisbach", correlation_2p="BeggsBrill") -> PathResult` — the
  generic port of `DPDT.calculate_output`: march section by section, pick single/two-phase,
  apply `heat_transfer.pipe_temperature_change`, return `p_out, T_out, dp_fric, dp_grav,
  section_p: list, section_T: list`. Correction factors are **not** applied here (the well does
  it). Keep the `max(0.001, p)` floor and the current `us_g` formula exactly (NOTE it: it uses
  `gmf` where `mg` looks intended). Unknown correlation names raise `ValueError` instead of
  `print`.

### `heat_transfer.py`
- `pipe_temperature_change(t_in, u_value, area, m_l, m_g, cp_l, cp_g, t_ambient)` (port of
  `TemperatureDrop`).
- For phase 8: `lmtd(dt1, dt2)`, `ntu(ua, c_min)`, `effectiveness_counterflow(ntu, c_ratio)`,
  `effectiveness_parallel(ntu, c_ratio)`.

### `chemistry.py`
Port of `co2_partial_pressure_model.py` as functions: `henry_constant(T)`,
`co2_solubility_liquid(...)`, `co2_solubility_gas(...)`, `co2_partial_pressure(...)`.

### `corrosion.py`
- `co2_corrosion_rate(model: Literal["NORSOK","DLM","DLD"], *, fitted: bool = False, temperature,
  pressure, water_flow_rate, water_density, water_viscosity, diameter, roughness,
  co2_fraction | co2_partial_pressure, bicarb_concentration, ionic_strength) -> float  # mm/yr`
  `fitted=True` selects the `correlations_opt` variants. Keep each correlation as a private
  function or small class in this file.
- `wall_loss(rates_mm_per_year, durations_s) -> cumulative mm` (salvaged).
- Inputs at the boundary are SI; if a correlation needs other units internally, convert inside
  with `units.py`.

### `erosion.py`
- `erosion_rate(model: Literal["DNV","OKA","TULSA"], *, flow_rate [m³/s], rho_fluid, diameter,
  particle/material inputs...) -> float  # mm/yr`, `api_erosional_velocity(rho_fluid) -> m/s`,
  the alias normalisation (`normalize_model_name`), and the shared `_common` helper. Today the
  correlations take m³/h; convert at the function boundary.

Rewire the old classes to call these functions (temporarily) and keep golden tests green. Commit.

## 5. Phase 3: `Stream`, `Component`, `Health`

### `core/base/stream.py`
```python
class Stream(BaseModel):
    """Fluid stream passed between component ports (SI units)."""
    model_config = ConfigDict(frozen=True)
    m_dot: float = Field(..., description="Mass flow [kg/s]; negative = reverse")
    T: float = Field(..., gt=0, description="Temperature [K]")
    p: float = Field(..., ge=0, description="Absolute pressure [Pa]")
    fluid: str = Field("brine", description="Fluid model name, see core.physics.fluid")

    def volumetric_flow(self) -> float: ...   # m³/s using get_fluid(fluid).properties(p, T)
    def with_(self, **changes) -> "Stream": ...  # thin wrapper over model_copy(update=...)
```

### `core/base/component.py`
```python
class Health(BaseModel):
    score: float      # 0..1, 1 = as designed
    alarm: bool
    message: str
    metrics: dict[str, float] = {}

class Component(ABC):
    """Base class for every plant component (one file per component)."""
    name: ClassVar[str]           # unique, snake_case, e.g. "esp"
    category: ClassVar[str]       # folder name, e.g. "pumps"
    description: ClassVar[str]    # one sentence, used by the registry and the agent
    Params: ClassVar[type[BaseModel]]
    Inputs: ClassVar[type[BaseModel]]
    Outputs: ClassVar[type[BaseModel]]
    inlets: ClassVar[tuple[str, ...]] = ()
    outlets: ClassVar[tuple[str, ...]] = ()
    soft_sensors: ClassVar[tuple[str, ...]] = ()   # Outputs fields that replace missing sensors
    calibratable: ClassVar[tuple[str, ...]] = ()   # Params fields history matching may fit
    stateful: ClassVar[bool] = False

    def __init__(self, params: dict | BaseModel, *, fluid: str = "brine"): ...
    def update_params(self, **changes) -> None: ...      # re-validate
    @abstractmethod
    def compute(self, inputs: BaseModel | dict, streams_in: dict[str, Stream]
                ) -> tuple[BaseModel, dict[str, Stream]]: ...
    def initial_state(self) -> Any: return None
    def step(self, state, inputs, streams_in, dt: float) -> tuple[Any, BaseModel, dict[str, Stream]]:
        # default for stateless components: delegate to compute, state unchanged
    def health(self, predicted: BaseModel, measured: dict[str, float]) -> Health | None: return None
    def capex(self) -> float | None: return None
    @classmethod
    def schema(cls) -> dict: ...  # {"name","category","description","inlets","outlets",
                                  #  "params": JSON schema, "inputs": ..., "outputs": ...,
                                  #  "soft_sensors", "calibratable", "stateful"}
```
Base-class behaviour to implement and test:
- `__init__` validates params with `Params.model_validate`, stores `self.params`, resolves the
  fluid model once.
- `compute` wrappers (implement in the base via `__init_subclass__` or a public `run()` method that
  subclasses do not override): validate `inputs` with `Inputs`; check `streams_in` keys equal
  `inlets` exactly (clear error naming the component and missing/extra ports); check the returned
  outputs are an `Outputs` instance and returned stream keys equal `outlets`.
- `__init_subclass__` checks that concrete subclasses define `name`, `category`, `description`,
  `Params`, `Inputs`, `Outputs`, and that every name in `soft_sensors` exists in `Outputs` and
  every name in `calibratable` exists in `Params`.
- Every Pydantic field in every component has `description="... [unit]"`; add a test that walks
  all registered components and fails if a field has no description or no `[unit]` / `[-]`.

Remove `gemini_model/model_abstract.py` (`Model`, `StaticModel`, `DynamicModel`) once phase 5 is
done. Commit.

## 6. Phase 4–5: the components (most important part)

General pattern for every component file:
```python
"""<Equipment> component.

<What it is in a geothermal plant, what it computes, references.>
"""

class <Name>(Component):
    name = "..."; category = "..."; description = "..."
    inlets = (...); outlets = (...)
    soft_sensors = (...); calibratable = (...)

    class Params(BaseModel): ...   # design data, SI, Field(description="... [unit]")
    class Inputs(BaseModel): ...   # per-step operating inputs
    class Outputs(BaseModel): ...  # per-step results

    def compute(self, inputs, streams_in): ...
    def health(self, predicted, measured): ...   # where meaningful
    # component-specific helper methods (classmethods for fitting/estimation)
```

For each component also add, in `core/plant/param_mapping.py`, a function
`<name>_params_from_gemini(property: dict) -> dict` that converts the GEMINI `.param` "property"
block (bar, °C, m³/h, mD, prefixed keys like `esp_no_stage`) into the component's SI `Params`. Use
the example `.param` files to test every mapper.

### 6.1 `components/pumps/esp.py` — `ESP`
Electrical submersible pump installed in the production well.
- `inlets = ("suction",)`, `outlets = ("discharge",)`.
- Params: `no_stages: int > 0`; `head_coeff: list[float]` (len 6) and `power_coeff: list[float]`
  (len 6) in the **same polynomial order and US-unit basis as today** (ft head / bhp per stage vs
  bbl/d at 60 Hz); `pump_type: str | None`; `setting_depth [m]` (from `esp_depth`);
  `min_flow`, `max_flow`, `bep_flow [m³/s]` (from `esp_min_flow`, `esp_max_flow`,
  `esp_bep_flow`, which are m³/h in the `.param`); `correction_factor` (read how
  `esp_correction_factor` is used in the old modules and document it); `tubing` if used.
- Inputs: `frequency [Hz] > 0`.
- compute: `Q = suction.volumetric_flow()`; `head [Pa]`, `power [W]`, `efficiency [-]` using the
  ported `head_function`, `power_function`, `efficiency_function` (unit conversions from
  `units.py`). The old efficiency is returned ×100 (percent); return a **fraction 0–1** and convert
  in the golden test (NOTE it). Discharge stream = suction with `p + head`, same `m_dot`, same `T`.
- Outputs: `head`, `power`, `efficiency`, `discharge_pressure`, `flow [m³/s]`,
  `in_operating_window: bool` (min_flow ≤ Q ≤ max_flow; if the old code scales the window with
  frequency, e.g. by f/60 as in `calculate_pump_head_curve`, replicate that), `bep_ratio [-]`
  (Q / bep_flow, frequency-scaled the same way).
- `soft_sensors = ("head", "power", "efficiency", "discharge_pressure")`,
  `calibratable = ("head_coeff", "power_coeff")`.
- `health(predicted, measured)`: `measured` may contain `power`, `head`, `discharge_pressure`.
  Compute relative drift per available metric; `score = 1 - max(|drift|)` clipped to [0,1];
  `alarm` if any |drift| > 0.10 or not in operating window; message names the worst metric.
- `@classmethod fit_head_coefficients(flows, frequencies, heads, no_stages) -> list[float]`:
  port of `calibrate_esp_head_simple` / head-curve logic from `gemini_application/esp/esp.py`.
- `head_curve(frequency, n_points=50) -> list[tuple[Q, head]]` helper for plots/agent (port of
  `calculate_pump_head_curve`, without plotting).

### 6.2 `components/subsurface/reservoir.py` — `Reservoir`
The aquifer seen from one well (production or injection side).
- Params: `role: Literal["production", "injection"]`; `pressure [Pa]` (static reservoir pressure);
  `temperature [K]`; `permeability [m²]`; `thickness [m]`; `drainage_radius [m]`;
  `top_depth [m]`; `productivity_index` and `injectivity_index` in **[m³/s/Pa]** (today they live
  in the well `.param` in m³/h/bar: the mapper moves them here); `skin: float = 0 [-]`;
  `wellbore_radius [m]` (from the well `.param`); optional `liquid_density`, `liquid_viscosity`
  overrides passed to the fluid model.
- Ports: production → `outlets = ("sandface",)`, no inlets; injection → `inlets = ("sandface",)`,
  no outlets. Implement with two subclasses `ProductionReservoir` and `InjectionReservoir` sharing
  a private base in the same file (`name = "production_reservoir"` / `"injection_reservoir"`), so
  ports stay static class attributes.
- Inputs: production: `m_dot [kg/s]` (rate imposed by the plant); injection: none.
- compute (production): `q = m_dot / rho`; `p_bh = pressure - q / productivity_index` (IPR port);
  outlet stream `T = temperature`, `p = p_bh`. (injection): from the inlet stream,
  `p_bh_required = pressure + q / injectivity_index`.
- Outputs: `bottomhole_pressure`, `drawdown` (or `overpressure`), `flow_dp`, `skin_dp`,
  `hydrostatic_dp` (port of `reservoir_pressuredrop`, hydrostatic via `hydraulics.hydrostatic_dp`),
  `radial_bottomhole_pressure` (reservoir_dp of the old model).
- Static helpers (used by history mode later):
  `estimate_pressure(flows, bottomhole_pressures) -> (pressure, r_squared)` (port of
  `reservoir_pressure_estimation`), `injectivity_from_measurements(flow, p_bh)` (port of
  `injectivity_index`), `productivity_from_measurements(flow, p_bh)`.
- `soft_sensors = ("bottomhole_pressure",)`,
  `calibratable = ("productivity_index", "injectivity_index", "pressure", "skin")`.
- `health`: compare measured PI/II (from measured flow + bottomhole pressure) with the parameter;
  alarm on > 15% decline (scaling/plugging indicator).

### 6.3 `components/subsurface/productionwell.py` — `ProductionWell`
Flow path from reservoir sandface up to the wellhead, with an optional ESP inside.
- `inlets = ("bottom",)`, `outlets = ("wellhead",)`.
- Params: `path: PipePath` (built by the mapper from `productionwell_trajectory_table` /
  `_trajectory_file` + `_tally_table` via `geometry.build_path`); `friction_correlation:
  Literal["darcy_weisbach"]`; `friction_correlation_2p: Literal["BeggsBrill"]`;
  `correction_factors: tuple[float, float] = (1, 0)` (p_out = a·p + b, as today);
  `soil_temperature [K]`; `u_value [W/m²/K] = 10` (hard-coded in DPDT today, now a param);
  `esp_depth [m] | None`.
- Inputs: none (flow and conditions come from the inlet stream).
- compute: `pipe_path_profile(path, bottom_stream, fluid, "up", ...)`, apply correction factors,
  outlet stream at wellhead. If `esp_depth` is set, `compute` only traverses the full path when the
  caller passes the ESP-boosted stream explicitly; provide public helpers:
  - `traverse(stream, from_md, to_md, direction) -> PathResult` (any sub-path),
  - `intake_conditions(bottom_stream) -> Stream` (bottom → ESP depth),
  - `wellhead_from_discharge(discharge_stream) -> Stream` (ESP depth → wellhead),
  - `discharge_from_wellhead(wellhead_stream) -> Stream` (wellhead → ESP depth, "down" direction,
    used by the twin to infer ESP discharge pressure from wellhead measurements; this is what
    `calculate_vlp_outlet_pressure` does today).
- Outputs: `wellhead_pressure`, `wellhead_temperature`, `dp_friction`, `dp_gravity`,
  `section_pressure: list[float]`, `section_temperature: list[float]`.
- Integrity helpers using core physics: `corrosion_profile(stream, chemistry: dict, model="NORSOK")
  -> list[mm/yr]` per section, `erosion_check(stream) -> dict` (API erosional velocity vs actual
  velocity per section).
- `soft_sensors = ("wellhead_pressure", "wellhead_temperature")` and expose
  `bottomhole_from_wellhead(...)` for the twin.
- `calibratable = ("correction_factors", "u_value")`.

### 6.4 `components/subsurface/injectionwell.py` — `InjectionWell`
Same structure as the production well, direction "down".
- `inlets = ("wellhead",)`, `outlets = ("bottom",)`.
- Params: same as production well minus `esp_depth` (mapper reads `injectionwell_*` keys).
- compute: wellhead stream → bottom stream (`calculate_bottomhole_pressure` today; note it passes
  a negative flow, `-1 * flow / 3600`: reproduce via the stream sign convention and NOTE it).
- Outputs: `bottomhole_pressure`, `bottomhole_temperature`, `dp_friction`, `dp_gravity`, section
  profiles.
- `soft_sensors = ("bottomhole_pressure",)`, `calibratable = ("correction_factors", "u_value")`.
- Same integrity helpers as the production well (put shared well logic in a small private mixin in
  `core/physics/` or duplicate minimal glue; do not import one component file from another).

### 6.5 Placeholders (exist in GEMINI as empty units)
Each gets a real file with: docstring explaining the equipment's role in a geothermal doublet;
identity; ports; Params with whatever the example `.param` has (mapped to SI); empty `Inputs`;
`Outputs` with the obvious future fields declared but `compute` raising
`NotImplementedError(f"{self.name} is not modelled yet")`.
- `pumps/injectionpump.py` — `InjectionPump`: `inlets=("suction",)`, `outlets=("discharge",)`;
  Params `no_stages`, `pump_type` (from `injection_pump_*.param`). Dataset has
  `InjectorPump_Pin/Pout/PowerDraw`: declare Outputs `head`, `power`.
- `pumps/boosterpump.py` — `BoosterPump`: same ports, no params yet.
- `treatment/degasser.py` — `Degasser`: `inlets=("inlet",)`, `outlets=("liquid", "gas")`;
  Params `heat_transfer_coeff` (from `.param`; document that its meaning is unclear).
- `treatment/filter.py` — `Filter`: `inlets=("inlet",)`, `outlets=("outlet",)`; Outputs
  `pressure_drop`; `health` already implementable: alarm when measured ΔP exceeds a
  `clogging_dp [Pa]` param (default 0.5 bar). Implement just this `health` (no compute).
- `treatment/blowdown.py` — `Blowdown`: `inlets=("inlet",)`, `outlets=("outlet",)`.
- `heat/boiler.py` — `Boiler`: merge `electricboiler` + `gasboiler`; Params `fuel:
  Literal["gas", "electric"]`, `capacity [W]`, `efficiency [-]`; `inlets=("inlet",)`,
  `outlets=("outlet",)`. Implement compute (it is trivial and we need it soon): heat the stream to
  `Inputs.setpoint_T [K]`, `duty = m_dot·cp·ΔT` capped at capacity, `fuel_or_power = duty /
  efficiency`; Outputs `duty [W]`, `fuel_or_power [W]`, `outlet_T [K]`, `capped: bool`.
- `heat/heatexchanger.py` — see phase 8.

### 6.6 Tests for components (`tests/components/<category>/test_<name>.py`)
For every component:
- parameter validation: valid example params load; wrong type, missing field, out-of-range value
  each raise `ValidationError`;
- `schema()` returns all keys and is JSON-serialisable;
- port contract: wrong/missing stream keys raise a clear error;
- golden numbers: implemented components reproduce phase-0 values (through the new API);
- `health` behaviour for ESP, Reservoir, Filter (no alarm at nominal, alarm past threshold);
- mapper test: the example `.param` file maps to valid `Params`.

Commit after phase 4 (core helpers used by components) and after phase 5 (all components).

## 7. Phase 6: twin modules on top of components

Rewrite the framework calculation modules into `core/engine/twin_modules/` so they **call
components** instead of building old models:
- `esp_theoretical.py`: replaces `calculate_theoretical_head`, `_power`, `_outlet_pressure` (one
  module producing the three tags from one `ESP.compute`).
- `esp_vlp.py`: replaces `calculate_vlp_ipr_inlet_pressure` (Reservoir → ProductionWell
  `intake_conditions`), `calculate_vlp_outlet_pressure` (ProductionWell
  `discharge_from_wellhead`) and `calculate_vlp_head` (difference).
- `injectionwell.py`: replaces `calculate_bottomhole_pressure` and `calculate_injectivity_index`.
Keep the existing tag names, `link()` wiring, loop handling and output tags identical so existing
plants and dashboards keep working. Unit classes (`ESPUnit`, `InjectionWellUnit`, empty units) move
to `core/plant/units/` (or stay next to the twin modules; choose the cleaner import graph and
explain). Build component instances from unit parameters via `param_mapping`. If there is an
integration path you can test without InfluxDB (the CSV driver), add one test that runs one engine
step on `datasets/geothermal_example` and checks the ESP theoretical power tag is produced. Commit.

## 8. Phase 7–8: registry, heat exchanger, examples

### Registry (`core/engine/registry.py`)
- Auto-discover all concrete `Component` subclasses under `gemini.components` (import the
  category packages; no manual list).
- `list_components() -> list[dict]` (each = `cls.schema()`), `get_component(name) -> type`,
  `create(name, params) -> Component`. Duplicate names raise at import.
- Tests: every file in `components/` is registered; names unique; schemas serialisable.

### `components/heat/heatexchanger.py` — `HeatExchanger` (first real new physics)
Plate heat exchanger separating geothermal brine (primary) from the clean secondary loop.
- `inlets = ("hot_in", "cold_in")`, `outlets = ("hot_out", "cold_out")`.
- Params: `ua [W/K]`, `arrangement: Literal["counterflow", "parallel"] = "counterflow"`,
  `dp_hot_nominal [Pa]`, `dp_cold_nominal [Pa]`, `m_dot_hot_nominal [kg/s]`,
  `m_dot_cold_nominal [kg/s]` (pressure drop scales with (m_dot/nominal)²).
  Mapper: the example `.param` only has `heat_transfer_coeff`; map it to `ua` if the magnitude
  fits, otherwise document what it is.
- compute: ε-NTU with `heat_transfer.effectiveness_*`; `duty = ε·C_min·(T_hot_in − T_cold_in)`;
  outlet temperatures from energy balance; pressure drops as above.
- Outputs: `duty [W]`, `effectiveness [-]`, `ntu [-]`, `lmtd [K]`, `hot_out_T`, `cold_out_T`,
  `dp_hot`, `dp_cold`, `approach_T [K]`.
- `soft_sensors = ("duty", "effectiveness")`, `calibratable = ("ua",)`.
- `health`: compute apparent UA from measured temperatures/flows (`ua_from_measurements(...)`
  classmethod); alarm when apparent UA < 85% of `ua` (fouling/scaling).
- Validation test against the dataset: first rows have `Qp ≈ 149.2 m³/h`, `T_p_in = 80 °C`,
  `T_p_out ≈ 20.31 °C`, `Qs = 160 m³/h`, `T_s_in = 20 °C`, `T_s_out ≈ 75.66 °C`,
  `Thermal_PowerGen ≈ 10.91 MW`. Fit `ua` with `ua_from_measurements` on those rows, then check
  `compute` reproduces the outlet temperatures within 0.5 K and duty within 2%. Also check
  `HEX_PDrop` order of magnitude for the dp params.

### `examples/`
Short, commented scripts that read `datasets/geothermal_example/` through the mappers:
`01_esp_operating_point.py` (head/power/efficiency at 3 frequencies, print a table),
`02_reservoir_ipr.py`, `03_well_pressure_profile.py` (section pressures/temperatures),
`04_doublet_chain.py` (reservoir → production well to ESP intake → ESP → wellhead → heat
exchanger → injection well → injection reservoir, passing `Stream`s by hand, printing every stream),
`05_list_components.py` (registry dump as JSON). `tests/test_examples.py` runs each one with
`runpy` and asserts it exits cleanly. Commit.

## 9. Final report (your last message)

1. Final tree of `gemini/` (two levels) and `tests/`; confirm `.claude/docs/*`, `AGENTS.md` and
   `CLAUDE.md` exist and still match the final code (update them if the code diverged).
2. Every deleted path; every dependency removed/added.
3. Every `NOTE(refactor)` (suspected bugs, unit ambiguities) with file:line.
4. Decisions you made that this prompt did not cover.
5. Test, lint and golden results (paste the summary lines).
6. What is not finished, and what you recommend next (heat pump, chillers, storage, demand,
   engine solver/modes).
