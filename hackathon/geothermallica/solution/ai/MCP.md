# MCP server for the GEMINI tools

`ai/AI10_mcp.py` serves the 17 tools of `ai/AI02_tools.py` over stdio with the same names, schemas, docstrings and
JSON results. Every call goes through the same registry as the agent, so an out-of-range argument comes back as a
tool error with the registry's message (for example `q_m3h=400.0 outside 50.0-300.0`). It also serves the resource
`notes://readme` (this folder's README) and the prompt `design_brief` (the challenge brief). It needs `pip install
"mcp>=2"` and no language model.

Run from `hackathon/geothermallica/solution`:

1. Round-trip check, about 2 s: `python ai/AI10_mcp_check.py` spawns the server, lists the 17 tools, calls
   `site_inputs` and `doublet_point`, reads the resource and the prompt.
2. Any MCP client over stdio: command `python`, argument `<absolute path>/ai/AI10_mcp.py`.
   Claude Code: `claude mcp add geohack -- python <absolute path>/ai/AI10_mcp.py`, then `/mcp` lists `geohack`.
   MCP Inspector: `npx @modelcontextprotocol/inspector python <absolute path>/ai/AI10_mcp.py`.
3. A local Ollama model through `ollmcp`: `ollmcp --mcp-server <absolute path>/ai/AI10_mcp.py --model qwen3:4b`.

The tools find GEMINI through `GEMINI_DEV_SRC` if the client passes it, else through this branch's own `src/`.
The tool list with one line each is in `README.md`, section 4; the full docstrings are what the server sends.
