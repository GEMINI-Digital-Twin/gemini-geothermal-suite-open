"""The AI02 GEMINI tools as an MCP server over stdio; an MCP client spawns it (python AI10_mcp.py), no Ollama."""
import contextlib
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

with contextlib.redirect_stdout(sys.stderr):   # library prints must never reach the JSON-RPC channel
    import AI02_tools as tools

from mcp.server.mcpserver import MCPServer   # mcp 2.x: MCPServer = FastMCP
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("geohack")
SCHEMA = {t["function"]["name"]: t["function"] for t in tools.TOOLS}


# build a function with the tool's keyword signature (optional args default None) that forwards to AI02.call
def make_tool(name):
    def fn(**kw):
        try:
            with contextlib.redirect_stdout(sys.stderr):
                return tools.call(name, {k: v for k, v in kw.items() if v is not None})
        except ValueError as e:      # AI02's range check becomes a tool error
            raise ToolError(str(e)) from e
    kind = lambda a: int if a in ("n_doublets", "outage_days", "max_doublets") else str if a in tools.STRINGS else float
    params = [inspect.Parameter(a, inspect.Parameter.KEYWORD_ONLY, annotation=kind(a) | None if a in tools.OPTIONAL else kind(a),
                                default=None if a in tools.OPTIONAL else inspect.Parameter.empty) for a in tools.SIG[name]]
    fn.__signature__ = inspect.Signature(params, return_annotation=dict)
    fn.__name__, fn.__doc__ = name, tools.FUNCS[name].__doc__
    return fn


for name in tools.SIG:
    server.add_tool(make_tool(name), name=name, description=SCHEMA[name]["description"], structured_output=False)
    server._tool_manager.get_tool(name).parameters = SCHEMA[name]["parameters"]   # clients see AI02's schema verbatim


def note_path(name):
    """The markdown note in solution/ or in the folder above it (the fork's hackathon/geothermallica), else None."""
    return next((q for q in (HERE.parent / name, HERE.parents[1] / name) if q.exists()), None)


README = note_path("README.md")

# the resource is registered only when the file is in this checkout, so no client sees a dead resource
if README:
    @server.resource("notes://readme", name="readme", description="README.md: the map of the deliverable", mime_type="text/markdown")
    def readme():
        return README.read_text()


@server.prompt(name="design_brief", description="The challenge brief (AI03.BRIEF), ready to send to the model")
def design_brief():
    with contextlib.redirect_stdout(sys.stderr):
        import AI03_agent   # lazy: imports AI01 (the ollama package) but calls no model
    return AI03_agent.BRIEF


if __name__ == "__main__":
    server.run("stdio")
