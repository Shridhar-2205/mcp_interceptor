#!/usr/bin/env python3
"""MCP server over Streamable HTTP — a small web server you start first.

It has two trivial tools: `add` and `greet`. It runs in "stateless JSON" mode, so
every request is a simple POST that returns JSON (no sessions, no streaming) —
which keeps the interceptor proxy dead simple.

Start order:  server (this)  ->  interceptor  ->  client

Docs used to build this:
- MCP Python SDK:                 https://py.sdk.modelcontextprotocol.io/
- Streamable HTTP transport spec: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
"""

import os

from mcp.server.fastmcp import FastMCP

PORT = int(os.environ.get("PORT", "8100"))

# FastMCP does all the protocol work; we just register tools on it below.
mcp = FastMCP("demo", host="127.0.0.1", port=PORT, json_response=True, stateless_http=True)


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@mcp.tool()
def greet(name: str) -> str:
    """Say hello to someone."""
    return f"hello, {name}!"


if __name__ == "__main__":
    print(f"[server] listening on http://127.0.0.1:{PORT}/mcp", flush=True)
    mcp.run(transport="streamable-http")   # serve over HTTP
