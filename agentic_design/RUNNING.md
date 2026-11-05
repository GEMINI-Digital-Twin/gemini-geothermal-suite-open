# Running the code (Windows, Command Prompt)

Always run from the repository root, e.g. `C:\Users\mohib\Desktop\Geohackathon\2026\gemini`, one command per line.
Use `python` (not `py`) so the active environment is used.

## One-time setup

```
python -m pip install -r agentic_design\requirements.txt
ollama pull qwen3:8b
```

## After extracting a new zip

```
tar -xf "%USERPROFILE%\Downloads\<zip name>.zip"
python -m pytest agentic_design/tests -q
```

All tests must pass before running anything else.

## The agent (Ollama must be running)

| Command | What it does | Output |
|---|---|---|
| `python -m agentic_design.agent --demo` | 7 scripted questions (normal, design, incomplete, missing input, user value, irrelevant, explain) | `agentic_design\transcripts\demo_*.md` |
| `python -m agentic_design.agent` | Free chat; `/stats`, `/save`, `/exit` | transcript on `/save` |

## The plant model without the agent

| Command | What it does |
|---|---|
| `python -m agentic_design.run_design --doublets 2 --depth 3500 --abs 5 --ec 5 --ri` | One design (here the selected one) for all 365 days, all checks, costs, GEMINI cross-check. Options: `--doublets`, `--depth`, `--hp`, `--abs`, `--ec`, `--ri` (reinject surplus associated gas), `--id`, `--esp-depth`, `--return-temp` |
| `python -m agentic_design.run_design --compare` | 1-3 doublets at 2500/3000/3500 m (heating only) |
| `python -m agentic_design.diagram --doublets 2 --depth 3500 --abs 5 --ec 5 --ri` | Plant flowsheet from the GEMINI project file |
| `python -m agentic_design.token_report` | Token and checker table of all transcripts in `evidence\` (token-reduction evidence) |
| `python -m agentic_design.studies` | Report studies (~3 min): 216-design sweep, Pareto front (`pareto.png`), cost and technical sensitivities, in `results\studies\` |

Results: `agentic_design\results\<design name>\` (`summary.txt`, `kpis.json`, `daily.csv`, `verification.txt`,
`gemini_peak_day.json`, `economics.json`, `plant_diagram.md`).

## Keeping evidence

`results`, `transcripts` and `memory` are not committed (they are regenerated). Copy transcripts to keep into
`agentic_design\evidence\demo_vN.md`, then:

```
git add -A
git commit -m "what changed"
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Wrong folder: `cd` to the repository root |
| Fewer tests pass than expected | The zip did not overwrite files: extract again with `tar` |
| Agent hangs / connection error | Start Ollama (`ollama serve`) |
