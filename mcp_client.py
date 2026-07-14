#!/usr/bin/env python3
"""MCP client that talks to the demo server THROUGH the interceptor.

Wiring:  mcp_client  ->  interceptor.py  ->  mcp_server   (all over stdio)

The client spawns the interceptor as its "server command"; the interceptor
spawns the real server. To the client this is indistinguishable from talking to
the server directly — but every message is logged by the interceptor.

Run the server directly (no interception) with --direct.
"""

from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))


def _server_params(mode: str) -> StdioServerParameters:
    server = os.path.join(HERE, "mcp_server.py")
    if mode == "direct":
        return StdioServerParameters(command=sys.executable, args=[server])
    # command the client launches = interceptor; interceptor's args = real server
    name = "interceptor_modify.py" if mode == "modify" else "interceptor.py"
    interceptor = os.path.join(HERE, name)
    return StdioServerParameters(command=sys.executable, args=[interceptor, sys.executable, server])


def _render(result) -> str:
    return " ".join(getattr(c, "text", str(c)) for c in result.content)


async def main() -> None:
    mode = "direct" if "--direct" in sys.argv else "modify" if "--modify" in sys.argv else "log"
    label = {"direct": "directly to server",
             "modify": "through the file-modifying interceptor",
             "log": "through the logging interceptor"}[mode]
    print(f"[client] connecting {label}\n")

    async with stdio_client(_server_params(mode)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("[client] tools:", [t.name for t in tools.tools])

            calls = [
                ("add", {"a": 2, "b": 3}),
                ("echo", {"text": "hello mcp"}),
                ("slugify", {"text": "On Call L9"}),
            ]
            for name, args in calls:
                result = await session.call_tool(name, args)
                print(f"[client] call {name}({args}) -> {_render(result)}")


if __name__ == "__main__":
    asyncio.run(main())
