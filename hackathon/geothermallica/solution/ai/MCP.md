# MCP server for the GEMINI tools (AI10)

`AI10_mcp.py` serves the 17 tools of `AI02_tools.FUNCS` over stdio with the same names, schemas, docstrings and JSON
results; every call goes through `AI02_tools.call`, so an out-of-range argument comes back as a tool error with
AI02's message (e.g. `q_m3h=400.0 outside 50.0-300.0`). Also: resources `notes://findings`, `notes://readme` (each only when its file is in the checkout), and
the prompt `design_brief` (the challenge brief, `AI03.BRIEF`). mcp 2.3.0 (`MCPServer`, the renamed FastMCP). No Ollama.

PY=/Users/bartlomiejsarwa/Documents/reservoir_eng/.venv/bin/python, SRV=/Users/bartlomiejsarwa/Documents/reservoir_eng/geohackathon_2026/solution/ai/AI10_mcp.py

1. Check (tested, about 2 s): `$PY .../ai/AI10_mcp_check.py` spawns the server, lists 17 tools, calls `site_inputs` and `doublet_point`, reads resources and the prompt.
2. Claude Code (untested by you): run from the repo root
   `claude mcp add --scope project geohack -- /Users/bartlomiejsarwa/Documents/reservoir_eng/.venv/bin/python /Users/bartlomiejsarwa/Documents/reservoir_eng/geohackathon_2026/solution/ai/AI10_mcp.py`
   then `/mcp` in Claude Code should list `geohack` with 17 tools. It writes `.mcp.json` in the repo root.
3. ollmcp on a local Ollama model (untested, not installed): `pipx install ollmcp` (or `uv tool install ollmcp`), then
   `ollmcp --mcp-server $SRV --model qwen3:4b` (check `ollmcp --help`; it may need the server as a `.py` path run by
   the same python, or a JSON config with `command: $PY, args: [$SRV]`). One Ollama job at a time.
4. MCP Inspector (untested, needs Node): `npx @modelcontextprotocol/inspector $PY $SRV`, open the URL it prints.

The GEMINI env var `GEMINI_DEV_SRC` is inherited from the client's environment; without it
`geo/gemini_path.py` falls back to `~/src/gemini-geothermallica/src` (the fork with our models).

## What each tool returns (from the docstrings)

- `site_inputs`: reservoir T and pressure at depth_m, producer wellhead T at 300 m3/h, whether the design tables cover the supply setpoints [D, A].
- `demand_summary`: peak MW, peak dates, annual GWh and cooling season of the 2027 demand files, scaled to the given peaks [D].
- `doublet_point`: one doublet at q_m3h and t_return_c: wellhead T, MW by source, ESP kW, heat-pump COP, pump-envelope flag [C, A].
- `heating_year`: 2027 daily dispatch of 1-3 doublets: GWh by source, electricity, unmet heat, capacity, peak-day split, hot brine for absorption [C, A].
- `cooling_year`: cold over 2027: free / absorption / electric GWh and shares, peak-day split, chiller and auxiliary electricity [C, A].
- `injector_point`: injectivity, bottomhole and wellhead pressure, pump kW, SodM margin, and the GEMINI-sign wellhead (F6) [C, A].
- `heat_pump_point`: GEMINI's HeatpumpBasic via HeatPumpLift: COP, heat and electricity MW, brine/water out, whether the floor binds [C, A].
- `checks`: the brief's 13 constraints, each `value (limit) -> pass or FAIL`, plus n_pass / n_fail [C].
- `economics`: CAPEX by item, annual cost, LCoH and LCoC, electricity, gas and CO2 [C, L, A].
- `return_sweep`: returns 40-70 C compared (boiler, electricity, share, unmet, margin) and best_return_c [C].
- `gemini_traps`: findings F1-F6 and F12 as short citable sentences [C].
