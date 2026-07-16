#!/usr/bin/env python3
"""A tiny MCP client. Talks to the server directly, or through an interceptor.

Built with the official MCP Python SDK. Client docs:
https://py.sdk.modelcontextprotocol.io/client/

    python mcp_client.py            # through the logging interceptor
    python mcp_client.py --tamper   # through the tampering interceptor
    python mcp_client.py --direct   # straight to the server (no interceptor)
"""

from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))


def _server_params(mode: str) -> StdioServerParameters:
    """What the client launches. For interceptor modes, the client launches the
    interceptor and the interceptor launches the real server."""
    server = os.path.join(HERE, "mcp_server.py")
    if mode == "direct":
        return StdioServerParameters(command=sys.executable, args=[server])
    interceptor = "interceptor_tamper.py" if mode == "tamper" else "interceptor.py"
    return StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(HERE, interceptor), sys.executable, server],
    )


def _text(result) -> str:
    return " ".join(getattr(c, "text", str(c)) for c in result.content)


async def main() -> None:
    mode = "direct" if "--direct" in sys.argv else "tamper" if "--tamper" in sys.argv else "log"
    print(f"[client] mode: {mode}\n")

    async with stdio_client(_server_params(mode)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("[client] tools:", [t.name for t in tools.tools])

            for name, args in [("add", {"a": 2, "b": 2}), ("greet", {"name": "world"})]:
                result = await session.call_tool(name, args)
                print(f"[client] {name}({args}) -> {_text(result)}")


if __name__ == "__main__":
    asyncio.run(main())
