#!/usr/bin/env python3
"""MCP server over Streamable HTTP — a small web server you start first.

It has two tools:
- `checkout(cart)` — adds up the prices in a JSON cart the client sends. This is
  the "does some processing" tool: whatever ends up in the cart, it sums.
- `greet(name)`    — a plain call with no JSON payload (nothing to tamper).

It runs in "stateless JSON" mode, so every request is a simple POST that returns
JSON (no sessions, no streaming) — which keeps the interceptor proxy dead simple.

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
def checkout(cart: dict) -> str:
    """Add up the prices in a shopping cart (the JSON payload the client sends)."""
    total = sum(v for v in cart.values() if isinstance(v, (int, float)))
    return f"items={list(cart)} total={total}"


@mcp.tool()
def greet(name: str) -> str:
    """Say hello to someone."""
    return f"hello, {name}!"


if __name__ == "__main__":
    print(f"[server] listening on http://127.0.0.1:{PORT}/mcp", flush=True)
    mcp.run(transport="streamable-http")   # serve over HTTP
