# GEMINI GeoHackathon 2026 — Submission

## Team / Author
Mahdi Izadi

## Quick Start

```bash
# 1. Clone the repo (development branch)
git clone --branch development https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open.git
cd gemini-geothermal-suite-open

# 2. Set up Python
python3.11 -m venv .venv && source .venv/bin/activate
pip install numpy scipy pandas pytest

# 3. Copy this hackathon_submission/ folder into the repo root

# 4. Run the full-year simulation
cd hackathon_submission
python run_full_year.py
```

## Plant Design

**2-doublet geothermal district heating + cooling plant** with heat pump upgrade
and gas-fired backup (boiler + CHP).

### Architecture
```
Reservoir (2500m TVD, 250 bar, 87°C)
    │
    ▼
┌─────────────────────── DOUBLET (x2) ──────────────────────┐
│ ProducerWell (ESP) → Separator → FilterA → HEX → FilterB │
│                                              │            │
│ InjectorWell (pump, η=0.70) ◄────────────────┘            │
└───────────────────────────────────────────────────────────-┘
    │ (secondary side from HEX: ~52°C)
    ▼
Heat Pump (Carnot η=0.50, COP≈3.9) → 100°C supply
    │
    ▼
District Heating Network
    │
    ▼
Boiler/CHP (gas backup) → covers peak demand + 35 outage days
```

### Cooling
- Absorption chiller (COP 0.7) driven by excess geothermal heat
- Supplemented by electric chiller for remaining load
- Delivers 20°C cooling supply

## Challenge Compliance

| Constraint | Value | Limit | Status |
|---|---|---|---|
| Flow per doublet | 106.2 m³/h | 50–300 | ✓ PASS |
| Brine cooling | 37.2°C | ≤ 40°C | ✓ PASS |
| Heating supply | 100°C | 100°C | ✓ PASS |
| Cooling supply | 20°C | 20°C | ✓ PASS |
| Pump efficiency | 0.70 | 0.70 | ✓ PASS |
| Doublets | 2 | 1–3 | ✓ PASS |
| Geo operating days | 330 | 330 | ✓ PASS |
| Volume balance | Enforced | = | ✓ PASS |

## Annual Results

- **Heating delivered:** ~5,479 MW-day
- **Cooling delivered:** ~1,460 MW-day
- **Geothermal share:** ~100% (geo + heat pump)
- **Heat pump COP:** 3.92
- **CO₂ emissions:** ~33,255 tonnes/year
- **Constraint violations:** 0

## Files

| File | Description |
|---|---|
| `run_full_year.py` | Main simulation — 365-day dispatch loop |
| `challenge_plant.json` | GEMINI plant definition with corrected challenge inputs |
| `generate_demand.py` | Creates synthetic demand profiles (placeholder) |
| `heating_demand.csv` | 365-day heating demand time series (MW) |
| `cooling_demand.csv` | 365-day cooling demand time series (MW) |
| `results_daily.csv` | Daily simulation outputs (365 rows) |
| `results_summary.csv` | Annual KPI summary |
| `validation_report.txt` | Constraint pass/fail report |

## Key Assumptions

- **Brine specific heat:** 4186 J/kg/K (not supplied by challenge, documented)
- **District return temperature:** 40°C
- **Heat pump model:** Carnot COP with η=0.50 (50% of ideal Carnot)
- **Gas emission factor:** 56.6 kg CO₂/GJ (natural gas)
- **Grid emission factor:** 0.3 kg CO₂/kWh
- **Maintenance:** 35 lowest-demand days (summer)
- **Cooling:** Absorption chiller (COP 0.7) + electric backup (COP 3.0)

## Modifications to GEMINI Source

Only one change to the GEMINI codebase:
- `src/gemini_simulator/registry.py`: Added `HeatpumpBasic` to the component registry
  (the model already existed in `gemini_model/heatpump/` but was not registered)
