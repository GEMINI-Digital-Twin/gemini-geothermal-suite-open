"""Spawn AI10_mcp over stdio as an MCP client, list and call its tools, read resources and prompt; no Ollama."""
import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import AI02_tools as tools


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "AI10_mcp.py")], env=dict(os.environ))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
        await s.initialize()
        names = [t.name for t in (await s.list_tools()).tools]
        assert sorted(names) == sorted(tools.FUNCS), names
        print(f"{len(names)} tools match AI02.FUNCS: {', '.join(names)}")
        for name, args in (("site_inputs", {"depth_m": 2500, "supply_heat_c": 100, "supply_cold_c": 20}),
                           ("doublet_point", {"q_m3h": 250, "t_return_c": 60}), ("doublet_point", {"q_m3h": 400, "t_return_c": 60})):
            r = await s.call_tool(name, args)
            print(f"\n{name}({args}) is_error={r.is_error}\n{r.content[0].text}")
        assert r.is_error, "out-of-range q must come back as a tool error"
        print("\nresources:", [str(x.uri) for x in (await s.list_resources()).resources])
        print("findings first line:", (await s.read_resource("notes://findings")).contents[0].text.splitlines()[0])
        print("prompts:", [p.name for p in (await s.list_prompts()).prompts])
        print("design_brief:", (await s.get_prompt("design_brief")).messages[0].content.text)


asyncio.run(main())
