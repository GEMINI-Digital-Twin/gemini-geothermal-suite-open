"""The AI02 GEMINI tools as an MCP server over stdio: same names, schemas, docstrings and JSON results.

Why: one tool surface for any MCP client (Claude Code, ollmcp on a local Ollama model, the MCP Inspector); every call
goes through AI02_tools.call, so range checks and errors are exactly the agent's. Tools are registered in a loop from
AI02.SIG / TOOLS, not hand-written, so a tool added to AI02 appears here with no edit. mcp 2.x (MCPServer = FastMCP).
Run: python AI10_mcp.py (an MCP client spawns it). No Ollama is called.
"""
import contextlib
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

with contextlib.redirect_stdout(sys.stderr):   # library prints must never reach the JSON-RPC channel
    import AI02_tools as tools

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("geohack")
SCHEMA = {t["function"]["name"]: t["function"] for t in tools.TOOLS}


def make_tool(name):
    """A function with the tool's own keyword signature (optional args default None) that forwards to AI02.call."""
    def fn(**kw):
        try:
            with contextlib.redirect_stdout(sys.stderr):
                return tools.call(name, {k: v for k, v in kw.items() if v is not None})
        except ValueError as e:      # AI02's range check: the client gets is_error and the message, as AI03.call gives the agent
            raise ToolError(str(e)) from e
    kind = lambda a: int if a == "n_doublets" else float
    params = [inspect.Parameter(a, inspect.Parameter.KEYWORD_ONLY, annotation=kind(a) | None if a in tools.OPTIONAL else kind(a),
                                default=None if a in tools.OPTIONAL else inspect.Parameter.empty) for a in tools.SIG[name]]
    fn.__signature__ = inspect.Signature(params, return_annotation=dict)
    fn.__name__, fn.__doc__ = name, tools.FUNCS[name].__doc__
    return fn


for name in tools.SIG:
    server.add_tool(make_tool(name), name=name, description=SCHEMA[name]["description"], structured_output=False)
    server._tool_manager.get_tool(name).parameters = SCHEMA[name]["parameters"]   # clients see AI02's schema verbatim


@server.resource("notes://findings", name="findings", description="NOTES_findings.md: the GEMINI findings (jury material)", mime_type="text/markdown")
def findings():
    return (HERE.parent / "NOTES_findings.md").read_text()


@server.resource("notes://readme", name="readme", description="solution/README.md: the map of the deliverable", mime_type="text/markdown")
def readme():
    return (HERE.parent / "README.md").read_text()


@server.prompt(name="design_brief", description="The challenge brief (AI03.BRIEF), ready to send to the model")
def design_brief():
    with contextlib.redirect_stdout(sys.stderr):
        import AI03_agent   # lazy: imports AI01 (the ollama package) but calls no model
    return AI03_agent.BRIEF


if __name__ == "__main__":
    server.run("stdio")
