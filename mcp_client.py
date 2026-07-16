#!/usr/bin/env python3
"""MCP client over Streamable HTTP.

It connects to a URL — by default the logging interceptor. Start the server and
an interceptor FIRST, then run this.

    python mcp_client.py            # -> logging interceptor  (127.0.0.1:8000)
    python mcp_client.py --tamper   # -> tampering interceptor (127.0.0.1:8001)
    python mcp_client.py --direct   # -> server directly       (127.0.0.1:8100)

Override the target with the MCP_URL env var if you use different ports.

Client docs: https://py.sdk.modelcontextprotocol.io/client/
"""

from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Each mode is just a different URL to connect to.
URLS = {
    "log": "http://127.0.0.1:8000/mcp",     # through the logging interceptor
    "tamper": "http://127.0.0.1:8001/mcp",  # through the tampering interceptor
    "direct": "http://127.0.0.1:8100/mcp",  # straight to the server
}


def _text(result) -> str:
    """Pull the plain text out of a tool result."""
    return " ".join(getattr(c, "text", str(c)) for c in result.content)


async def main() -> None:
    # Pick the target from the command-line flag (default: logging interceptor).
    mode = "direct" if "--direct" in sys.argv else "tamper" if "--tamper" in sys.argv else "log"
    url = os.environ.get("MCP_URL", URLS[mode])
    print(f"[client] mode: {mode} -> {url}\n")

    # Open the HTTP connection, then start an MCP session on top of it.
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()          # MCP handshake

            # Ask the server what tools it has.
            tools = await session.list_tools()
            print("[client] tools:", [t.name for t in tools.tools])

            # Call each tool and print what came back.
            for name, args in [("add", {"a": 2, "b": 2}), ("greet", {"name": "world"})]:
                result = await session.call_tool(name, args)
                print(f"[client] {name}({args}) -> {_text(result)}")


if __name__ == "__main__":
    asyncio.run(main())
