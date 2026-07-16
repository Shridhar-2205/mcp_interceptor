#!/usr/bin/env python3
"""A tiny MCP server with two trivial tools: `add` and `greet`.

Built with the official MCP Python SDK (FastMCP), which serves over the stdio
transport by default.

Docs used to build this:
- MCP Python SDK:       https://py.sdk.modelcontextprotocol.io/
- stdio transport spec: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@mcp.tool()
def greet(name: str) -> str:
    """Say hello to someone."""
    return f"hello, {name}!"


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
