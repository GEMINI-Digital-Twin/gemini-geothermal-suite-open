# Data

Readers are `from_<format>` and writers `to_<format>`. A reader is a classmethod of the class it
returns (`gm.Case.from_json(path)`, `gm.Plant.from_json(path)`, `gm.Results.from_npz(path)`,
`Dataset.from_frame(...)`); a writer is a method of the object (`case.to_json(path)`,
`results.to_npz(path)`, `plant.to_dict()`). Only a reader that returns no gemini class, a demand
frame, is a plain function in its folder: `gm.data.from_csv` and `gm.data.from_values`. No name
starts with `read_`, `write_`, `load_`, `save_`, `parse_` or `dump_`.

## In-memory data

`gm.Dataset` (`gemini/run/dataset.py`) owns one pandas-backed, sorted, unique, timezone-aware UTC
table of raw values; units are metadata. `Dataset` and the engine contain no file readers, database
clients, network calls, or source handles. The user or backend reads files/services and passes the
resulting in-memory values to one of:

- `Dataset.from_frame(df, time_column=None, units=None, tz="UTC")`
- `Dataset.from_dict(data, time, units=None, tz="UTC")`
- `Dataset.from_records(rows, time_column, units=None, tz="UTC")`
- `Dataset.from_numpy(time, values, columns, units=None, tz="UTC")`
- `Dataset.from_profiles(profiles)`
- `Dataset(frame, units=None)` for a frame that already has a time index

The time axis may be any timestamp sequence: datetimes, ISO text or values with UTC offsets.
Naive timestamps are local times in `tz` and fail when ambiguous or nonexistent at a DST switch;
values with offsets keep their own offsets, which may change at DST switches. The index may have
any resolution (s, ms, us or ns; pandas 3 parses text as microseconds); spacing, gaps and sampling
are computed in nanoseconds. `units` maps column names to a unit string or a
`{"unit": ..., "quantity": ...}` mapping. `from_profiles` takes a mapping of column names to
profiles that share one index and records their SI units. Invalid input (no time column, repeated
or missing timestamps, repeated or empty column names, unit metadata for unknown columns, a wrong
array shape) raises `gm.errors.RunError`.

`read(start, end, columns=None)` and `window(start, end)` use inclusive bounds; `after(t)` is
strict. `names` lists the columns, `start`/`end` the first and last timestamps, and
`native_step` is the median spacing (`None` for fewer than two rows). `unit(column, default)`
returns the unit recorded for a column, or `default` without metadata: during a run a column's
recorded unit replaces the unit in the plant binding, and the binding unit applies otherwise.
`fingerprint()` hashes timestamps, values, dtypes and unit metadata; checkpoints store it for
information only and nothing compares it on resume. Text flags are retained. Missing bound
columns are reported together, as one `ValidationError` (code `missing_column`), before a run begins.

**Run input.** `simulate`, `replay` and `live` take one format: a `Dataset`, or a pandas DataFrame
with a timezone-aware `DatetimeIndex` and columns named by the binding `column`, in the units of
the bindings (a unit recorded in the `Dataset` metadata replaces the binding's, as above).
`gemini.run.dataset.as_dataset(data)` is the one wrapper: a `Dataset` passes through, a
DataFrame becomes a `Dataset` (any zone is converted to UTC), and a naive index, a non-time index
or another type raises `RunError`, because a local time without a zone is ambiguous. Rows with
NaN in a bound column are skipped for the twin that needs them and reported as `missing_value`
rows by `Results.errors()`; the run continues ([engine.md](engine.md#run-input)).

`Loader(dataset, ticks, columns=None, align="previous", max_gap=None, chunk=7 days,
durations=None)` is the internal sampler. It accepts any finite tick iterable and never imports
engine code. It yields `Sample(t, dt, row)`: the tick, the seconds to the next tick and a dict of
raw column values. `durations` gives those seconds per tick; by default they are the tick spacing
followed by the native cadence. `previous` alignment holds the latest row at or before the tick,
`exact` requires a row at the tick and `mean` averages numeric values over `[tick, next_tick)` and
keeps the final text flag. A hold older than `max_gap` (by default twice the native cadence, or
twice `DEFAULT_STEP` for fewer than two rows) and an empty mean bin give a row of NaN, which the
engine reports as missing measurements. The dataset is read one `chunk` of ticks at a time.
`Loader.arrays()` is the one alignment: `Aligned(times, durations, columns)` with one array per
column, for every `align` (gaps are NaN; a column is `float64`, or `object` when the dataset holds
text). Iterating yields the `Sample` of each tick built from those arrays, one chunk at a time.
`Aligned.numbers(column)` converts a column to floats (what `float()` refuses is NaN) and
`Aligned.present(column)` is the "missing" rule: a row holds a value when it is a finite number.
Tests assert that iteration equals the arrays, gaps, `max_gap` and chunk borders included.
Normal users do not construct loaders.

A frame may state units in `attrs["units"]`, as a `gm.schedule` plan does; they are the metadata of
its `Dataset`, so they replace a binding's unit, and a unit of a column the frame no longer has is
dropped.

`Profile.constant(value, unit=..., clock=...)` and `Profile.from_series(series, unit=...)`
convert in-memory raw values to SI. Profiles combined into a dataset must share a clock.

## Demand profiles

`gm.data` ships no profile: a demand is the caller's. The code is `gemini/case/_utils/demand.py`,
which `gm.data` exports, because a `gm.Case` holds a demand and `run` imports no `data`.
`from_csv(path, columns, unit)` reads a file whose first column is named `time`, and `columns` maps its columns to the quantities of gemini, so a
file adapts to gemini and gemini takes no name or unit from it. `from_values(values, unit, start,
step, quantity)` takes numbers. A quantity is `heating_demand` or `cooling_demand`. Both return a
DataFrame in the run-input format, the form of a case's `demand.frame`: a UTC `DatetimeIndex` called `time`
at any constant step and of any length, one column per quantity in W, and `frame.attrs` with `units`
and `quantities`. Both validate through one check: a monotonic index with no gaps or repeats, a
constant step, no negative or missing value, a known quantity. `profile_schema()` is the JSON Schema
of the same frame as a document: `columns` (unit and quantity), `time` and `values`.
A profile column becomes a run input when a plant binding names it as
its `column`.

The committed CSVs under `inputs/doublet_heat/` are immutable source data. Two
of their naming choices predate the naming rule and stay: columns named `*.m_dot` hold volumetric
flow in m3/s (their bindings declare `"unit": "m3/s"`), and the unbound status columns
(`esp_status`, `hex_status`, `filterA_status`, `filterB_status`) and
`production_wellhead_pressure` keep their old names.

## The case

`gm.Case` is the strict entry boundary of every run: the outside conditions over one period and the
rules of third parties, in a `case.json` with CSV files and an `economics.json` next to it. The
rule of each field is [inputs.md](inputs.md); this page says how the code reads and holds them.
Every file starts with the header `{"format": 1, "kind": "case", "name": "..."}`. Every leaf is read
by `gemini/types/inputs.py` (the one reader), every value is stored in SI as a plain number or an
array on `case.time.index`, and the case keeps each leaf as it was given, so `to_dict`/`to_json`
write the unit and the numbers back unchanged (a series in kW stays kW in its CSV). Objects are
immutable (`case.with_value("site.ground.gradient", 0.03)` returns a copy with an SI value).
Nothing has a default: an absent value is `None` and the call that needs it raises `missing_value`
(`missing_assumption` below `economics`) naming its path.

`Case.from_json(path)` reads the file, its CSV files and the economics file it names;
`Case.from_dict(data, files={name: bytes}, folder=None)` reads a dict and takes the files from the
mapping, then from the folder. Both raise one `ValidationError` carrying every issue
(`error.issues`). `case.check()` and `economics.check()` return the same issues for an object and
never raise. `case.to_json(path)` writes the file and its files back, so that `Case.from_json(path)
== case`. A key of an older shape (`environment`, `constraints`, `assumptions`, `time_column`,
`equals`, a demand `file`/`column`) is refused with code `old_format`, naming the new form.

**The unit format.** A value with a unit is `{"value": 150, "unit": "m3/h"}` in the file and a
`gm.units.Quantity` in Python (a `Quantity` in the data given to `from_dict` is turned into that
object). A dimensionless value is `{"value": 0.7}`; a bare number or text such as `"150 m3/h"` is an
issue. A time series is `{"file": "data/demand.csv", "column": "heat_mw", "unit": "MW"}` in place of
`value`; the first column of every CSV is `time`, ISO 8601 with an offset or `Z`. A series that does
not cover `time` is a `coverage` issue naming file, column, covered and requested window; a coarser
`time.step` averages the samples, a finer one is an issue.

Sections of `case.json`:

| Section | Holds |
| --- | --- |
| `time` | `start`, `end` (excluded), `step`; `case.time.index` is the UTC `DatetimeIndex` |
| `initial_state` | `{module path: {state: {value, unit}}}`; `case.initial_state[module][state].si` |
| `site` | `ground` (`surface_temperature`, `gradient`), `reservoir` (`reference_depth`, `thickness`, `permeability`, `pressure`, `temperature`), `fluid` (`density`, `viscosity`, `gas_liquid_ratio`, `dissolved_gas` as a leaf per species, `sand_concentration`), `air` (`temperature`, `relative_humidity`, `pressure`). `temperature_at(depth)` and `pressure_at(depth)` apply the two rules of `gemini/physics/ground.py` |
| `demand` | `heating` and `cooling`: `power` (a series or a quantity), `supply_temperature`, `return_temperature`, `minimum_return_temperature`, `maximum_return_temperature`, `return_pressure`; cooling also `indoor_temperature`, `indoor_relative_humidity`, `dew_point_margin`. `case.demand.frame` is the demand in W on `time.index`, columns `heating_demand` and `cooling_demand` |
| `utilities` | `electricity` (`co2_intensity`, `import_limit`, `export_limit`), `gas` (`composition` over `CH4`, `C2H6`, `C3H8`, `CO2`, `N2`, `O2`, the species of `gemini.physics.gas`; `heating_value`) |
| `economics` | an object or the path of an `economics.json`, see below |
| `requirements` | a list of `{name, on, quantity, unit?, over?, when?, min?, max?}` |
| (`choices`) | removed: the search ranges are `range` leaves of the plant (`size.doublets`, `params.depth`); a case with the key is refused with `old_format` naming them |

`apply_case` (see [engine.md](engine.md#how-the-case-reaches-the-modules)) reads `site.air.pressure`
for every `Atmosphere`, `utilities.gas.composition` for every `GasGrid` (both required where the
module is present), the consumer conditions of `demand` (`return_pressure`, the return-temperature
limits, `dew_point_margin`, `indoor_temperature`, `indoor_relative_humidity`), `site.fluid.sand_concentration`
for a `Desander`, the connection limits of `utilities.electricity`, and `demand.<service>.supply_temperature`
for the setpoint of a unit on a supply line. The plant states none of them.

**Requirements.** `on` is a role and `quantity` one of it, from the closed table `gm.case.roles()`,
which gives for each quantity its dimension and whether it takes `over`. A per-step quantity states
`over` (`each`, `sum`, `mean`, `max`, `min`, `duration`) and may state `when` (`always`, `running`;
absent is every step); a window quantity or a property (`pump_efficiency`, `count`, `unmet_share`)
takes neither. `unit` is present if and only if the bounds have a dimension, and `min`, `max` are
numbers in it; `equals` is `min` = `max`. `name` is required, snake_case and unique.

**Economics.** `gm.case.Economics` is its own class (`from_json`, `to_json`, `check`, `schema`)
and the case holds it as `case.economics`, `None` for a pure physics case. Fields: `currency` and
`price_year`, `discount_rate`, `analysis_period`, `capex.<kind>` (the 19 kinds of
[economics.md](economics.md#costs)), `opex.fixed.<kind>`, `opex.variable.chemical` and
`waste_disposal`, `energy.electricity` and `gas`, `carbon.price`, `revenue.heat`, `cold` and
`subsidy` (`amount` per year, `duration`), `accounting.allocation.heat_cost_share` and
`accounting.gwp` (`standard` text, `CH4`). `capex.drilling` is a quantity per metre or a depth table
`{"depth": {"value": [...], "unit": "m"}, "cost_per_metre": {"value": [...], "unit": "EUR/m"}}`;
`economics.drilling_cost_per_metre(length)` interpolates it linearly and a length outside the table
raises `out_of_bounds`. A price series needs the time of a case: `Economics.from_json(path,
time=case.time)`.

**Uncertainty.** Any leaf that is a number may carry `uncertainty` (`uniform`, `triangular`,
`normal`) in the leaf's unit. `case.uncertainty` is the index `{dotted path: Uncertainty}` in SI
(`site.ground.gradient`, `economics.energy.electricity`), derived from the leaves; `gm.study.sample`
and `gm.study.sensitivity` read it, a run uses only the value.

`inputs/examples/hackathon_2026/case.json` is the complete example, with the sources of the cited
values in [economics.md](economics.md#the-values-of-the-assumptions).

## Where data lives

There is one data folder, and no data file inside `gemini/`: a plant is a class.

`inputs/` is at the repository root, next to `gemini/`, and is not installed. It holds everything
that code reads: `examples/` (sample cases), `plants/` (example values: a `size`, `params`,
`fluids`, `boundary`, `bindings`, `param_history` and `inputs`; the template plants have none),
`doublet_heat/` (measured data) and `legacy_project/` (read by tests only, [legacy.md](legacy.md)). A function that needs it raises `RunError`
with code `inputs_missing` when it is absent, as in an installed wheel, and the message names the
file. Nothing fails at import time, and `gm.plants.get` works without it.

`docs/cost-sources/` is a cost catalogue, not a second data folder: reference data with sources
(`sources.csv`, `README.md`), plus `data/` with the HICP and Ember files that its conversions and
grid factors are recomputed from. No code in `gemini/` reads it and no value in it is a default: a
project copies what it uses into its own `case.json` and cites the row's `id`. `inputs/` stays the
only folder the code reads.

`inputs/examples/<sample>/` holds one folder per sample case, a whole case in the shapes of gemini.
Each has:

- `case.json`: a `gm.Case` (`gm.Case.from_json`), see [the case](#the-case). It names `economics.json` and the demand CSV;
- `economics.json`: a `gm.case.Economics`, given by path from the case;
- `data/demand.csv`, read through `case.json` (`demand.heating.power`), first column `time`;
- the plant dicts (`gm.Plant.from_json`): one file for each candidate in `plants/<Class>.json`; a design without the world;
- `study.json` (`gm.Study.from_json`): what to run on them, see the study;
- `README.md`: the source of the files and what the case asks.

`hackathon_2026/` also keeps its organiser files (the requirements PDF and the two daily demand
CSVs). A whole run is:

```python
import gemini as gm

case = gm.Case.from_json("inputs/examples/shallow_district/case.json")
plant = gm.Plant.from_json("inputs/examples/shallow_district/plants/HeatingHeatPumpCoolingPlant.json")
results = gm.simulate(plant, case)
```

**Only `examples/` and `tests/` read this folder** (tests through
`tests/fixtures/sample_cases.py`): nothing under `gemini/` names it or a sample, and
`tests/unit/test_code_quality.py` checks that. A sample is a test of the code, never the source of a
default, a name or a structure.

`docs/schemas/` is generated documentation, not data. `tests/fixtures/` holds goldens and
`tests/e2e/expected/` example outputs. `gemini/_utils/paths.py` is the one place that knows where the
folder is, and `tests/unit/test_code_quality.py` checks the layout.
