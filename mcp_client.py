#!/usr/bin/env python3
"""MCP client over Streamable HTTP. Connects to a URL — by default the
interceptor. Start the server and an interceptor FIRST, then run this.

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

URLS = {
    "log": "http://127.0.0.1:8000/mcp",
    "tamper": "http://127.0.0.1:8001/mcp",
    "direct": "http://127.0.0.1:8100/mcp",
}


def _text(result) -> str:
    return " ".join(getattr(c, "text", str(c)) for c in result.content)


async def main() -> None:
    mode = "direct" if "--direct" in sys.argv else "tamper" if "--tamper" in sys.argv else "log"
    url = os.environ.get("MCP_URL", URLS[mode])
    print(f"[client] mode: {mode} -> {url}\n")

    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("[client] tools:", [t.name for t in tools.tools])

            for name, args in [("add", {"a": 2, "b": 2}), ("greet", {"name": "world"})]:
                result = await session.call_tool(name, args)
                print(f"[client] {name}({args}) -> {_text(result)}")


if __name__ == "__main__":
    asyncio.run(main())
