#!/usr/bin/env python3
"""Minimal MCP server (stdio transport) exposing a few safe, single-purpose tools.

Security posture (see MCP security guidelines):
- **stdio transport** for local use — pipe-based, so there is no network
  listener and no DNS-rebinding surface.
- Each tool is **single-purpose** with explicit input validation / length caps
  (no "do anything" tool, least privilege).
- No secrets, no filesystem/network side effects.
"""

from __future__ import annotations

import re

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-tools")

MAX_TEXT = 500


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


@mcp.tool()
def echo(text: str) -> str:
    """Echo the given text back unchanged (max 500 chars)."""
    if len(text) > MAX_TEXT:
        raise ValueError(f"text too long (max {MAX_TEXT})")
    return text


@mcp.tool()
def slugify(text: str) -> str:
    """Convert text into a lowercase URL-safe slug (max 200 chars)."""
    if len(text) > 200:
        raise ValueError("text too long (max 200)")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


if __name__ == "__main__":
    # FastMCP.run() defaults to the stdio transport.
    mcp.run()
