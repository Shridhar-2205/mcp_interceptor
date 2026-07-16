#!/usr/bin/env python3
"""MCP client over Streamable HTTP.

Start the server and an interceptor FIRST, then run this. It just connects to a
URL and makes two tool calls:

    python mcp_client.py            # -> logging interceptor  (:8000)
    python mcp_client.py --tamper   # -> tampering interceptor (:8001)
    python mcp_client.py --direct   # -> server directly       (:8100)

Client docs: https://py.sdk.modelcontextprotocol.io/client/
"""

import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Each mode is just a different URL.
URLS = {
    "log": "http://127.0.0.1:8000/mcp",     # logging interceptor
    "tamper": "http://127.0.0.1:8001/mcp",  # tampering interceptor
    "direct": "http://127.0.0.1:8100/mcp",  # straight to the server
}


def _text(result) -> str:
    """Pull the plain text out of a tool result."""
    return " ".join(getattr(c, "text", str(c)) for c in result.content)


async def main() -> None:
    mode = "direct" if "--direct" in sys.argv else "tamper" if "--tamper" in sys.argv else "log"
    url = URLS[mode]
    print(f"[client] mode: {mode} -> {url}\n")

    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()                        # handshake

            tools = await session.list_tools()                # tools/list
            print("[client] tools:", [t.name for t in tools.tools])

            for name, args in [("add", {"a": 2, "b": 2}), ("greet", {"name": "world"})]:
                result = await session.call_tool(name, args)  # tools/call
                print(f"[client] {name}({args}) -> {_text(result)}")


if __name__ == "__main__":
    asyncio.run(main())
