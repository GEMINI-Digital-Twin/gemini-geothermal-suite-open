# SPE Europe Energy GeoHackathon 2026 (Express Edition) - Agentic geothermal design

Submission by Ramdhan Ari Wibawa. An agentic workflow that selects, sizes and validates a
deep-geothermal heating and cooling system for the supplied 2027 demand profiles, using the
GEMINI `gemini_model` physics directly and adding the surface component models GEMINI lacks.

- `SUBMISSION.md` - long-form technical write-up; `GEMINI_Hackathon_Report_Ramdhan_Wibawa.pptx` - 10-slide report
- `ARCHITECTURE.md` - system diagram; `PITCH_SCRIPT_5MIN.md`, `DEMO_SCRIPT.md` - pitch and demo
- `gemini_design_agent/` - package, tests and generated outputs (design reports, optimiser study, ESP monitoring, dashboard data)

Run from `gemini_design_agent/`:

```
pip install -r requirements.txt
python -m gemini_design_agent run --heating ../GEMINI_Heating_Demand_Daily_2027.csv --cooling ../GEMINI_Cooling_Demand_Daily_2027.csv --out outputs --mode rule
python -m pytest tests -q
```

The GEMINI models are found automatically because this folder sits inside the repository
(`src/gemini_model`); set `GEMINI_SRC` to point elsewhere. `--mode claude` needs
`ANTHROPIC_API_KEY` (placeholder: not committed); the rule-based mode reproduces the same design offline.
