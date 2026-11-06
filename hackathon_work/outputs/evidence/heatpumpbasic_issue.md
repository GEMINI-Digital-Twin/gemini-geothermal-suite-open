# `HeatpumpBasic`: unreliable solutions and aliased output

**Component:** `src/gemini_model/heatpump/heatpump_basic.py` (GEMINI `development` @ `d86e8bb`)
**Found by:** hackathon daily model (`hackathon_work/daily_model.py`), 2026-11-02
**Repro:** `hackathon_work/repro_heatpumpbasic.py` (no `src/` edits)

```powershell
$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/repro_heatpumpbasic.py
```

All cases use Lorenz mode, `eta_lorenz` 0.5, `COP_0` 3.0, `Cp_h = Cp_s` 4100 J/(kg·K),
`rho_h = rho_s` 1030 kg/m³, `Th_out_target` 100 °C. "Root-solved" is the model's **own two
equations** (COP = η·T̄h/(T̄h − T̄s) and COP = Qh/(Qh − Qs), log-mean temperatures in K)
solved with `scipy.optimize.brentq` on `Ts_out`.

## 1. `Ts_in_minimum` fallback returns a runaway sink temperature

Inputs: `Th_in` 61.5 °C, `Ts_in` 62.0 °C, `hot_flow_rate` 0.1776 m³/s, `source_flow_rate` 50 m³/h,
`Ts_in_minimum` 39.67 °C (source-limited).

```
HeatpumpBasic:               COP=   1.0023  Th_out=   835.72 C  Ts_out=   39.67 C
```

When the unconstrained `Ts_out` falls below `Ts_in_minimum`, `carnot_model2`/`lorenz_model2`
re-solve for `(COP, Th_out)` with `Ts_out` pinned. Nelder-Mead finds a degenerate minimum at
COP ≈ 1 (Qs ≪ Qh), where both residuals are small for almost any `Th_out`, so `Th_out` is
unbounded (835 °C here, above the 100 °C target). There is no bound `Th_in < Th_out ≤ Th_out_target`.

## 2. Primary solve diverges at low lift / small sink flow

```
Low lift (Th_in 85.34, Ts_in 82.94, hot 0.00793 m3/s, source 300 m3/h):
  HeatpumpBasic:               COP=   0.0138  Th_out=   409.21 C  Ts_out=  -50.00 C
  same equations, root-solved: COP=  17.6880  Th_out=   100.00 C  Ts_out=   81.62 C
Small sink (Th_in 68.31, Ts_in 69.37, hot 0.00889 m3/s, source 176 m3/h):
  HeatpumpBasic:               COP=   0.1813  Th_out=   246.31 C  Ts_out=  -50.00 C
  same equations, root-solved: COP=  10.4032  Th_out=   100.00 C  Ts_out=   64.16 C
Normal case (Th_in 77.85, Ts_in 79.0, hot 0.0889 m3/s, source 295 m3/h):
  HeatpumpBasic (converges):   COP=   8.7974  Th_out=   100.00 C  Ts_out=   57.70 C
  same equations, root-solved: COP=   8.7974  Th_out=   100.00 C  Ts_out=   57.70 C
```

The objective `J = |COP − Lorenz| + |COP − Qh/(Qh − Qs)|` is non-smooth and is started from
`x0 = [COP_0, Ts_in − 10]`. When the true `Ts_out` is close to `Ts_in` (small duty relative to
source flow), Nelder-Mead walks to `Ts_out` far below the source, which triggers issue 1 (here with
`Ts_in_minimum = −50`). The result is COP < 1 and `Th_out` of hundreds of °C, with no warning.
Where it converges, it agrees with the root-solved answer to 4 decimals. In the hackathon year
run (Lorenz η 0.5, uncapped) it agreed within 1% on only 238–272 of 344–365 heat-pump days.

## 3. `get_output()` returns the internal dict

```
first result COP when returned: 8.7974; same object after a second call: 8.7676
first is hp.output: True  (gemini_model.model_abstract.Model.get_output returns a copy)
```

`HeatpumpBasic.get_output()` overrides `Model.get_output()` (which returns `dict(self.output)`)
with `return self.output`. Any caller that keeps a result while re-running the model, such as a
bisection, sees it silently overwritten. This caused a 0.009 K brine-cooling overshoot in our
first daily-model version.

## Proposed fix (upstream; not applied, `src/` untouched)

1. **`get_output`**: delete the override, or `return dict(self.output)`, to match `Model`.
2. **Primary mode**: replace Nelder-Mead with a bracketed 1-D root solve on `Ts_out`.
   With `Th_out` fixed at the target, `Qh` is known, and
   `r(Ts_out) = ms·Cp_s·(Ts_in − Ts_out) − Qh·(1 − 1/COP(Ts_out))` is monotonic in `Ts_out`
   on `[Ts_in − Qh/(ms·Cp_s), Ts_in)`, so the root is unique:
   ```python
   ts_low = Ts_in - Qh / (ms * Cp_s)          # Qs = Qh (infinite COP): r > 0
   Ts_out = brentq(r, ts_low, Ts_in - 1e-9)   # r < 0 just below Ts_in
   ```
   Carnot mode is the same with constant temperatures.
3. **Source-limited mode**: solve `Th_out` in `(Th_in, Th_out_target]` with `Ts_out = Ts_in_minimum`
   by the same bracketing approach (residual monotonic in `Th_out`), or return the largest sink
   share that reaches the target, as the hackathon model does. Never return `Th_out > Th_out_target`.
4. **Validation**: raise or warn when `COP ≤ 1`, `Ts_out ≥ Ts_in`, `Th_out ≤ Th_in`, or the optimizer
   reports `success = False`. Add unit tests for the three cases above.
5. Optional: a `COP_max` parameter (the hackathon base case caps COP at 6.0).

## Workaround used in the hackathon model

`daily_model.Plant.heat_pump_point` solves the same two equations with `brentq` (with an optional
COP cap) and limits the sink share so the brine never goes below `T_wellhead − 40 K`.
HeatpumpBasic's COP is still computed every day as a cross-check and logged in `daily.csv`
(`hp_COP_heatpumpbasic`).
