#!/usr/bin/env python3
"""Incident-remediation MCP server (stdio transport).

Use case: an AI **on-call agent** drives a small set of production remediation
tools over MCP during an incident — read a service's error rate, roll a bad
deploy back, and scale a service out. These are exactly the kind of *high-impact*
actions you want an **interceptor** in front of: to audit every call, and to
capture the sequence as a re-runnable runbook.

Security posture (see MCP security guidelines):
- **stdio transport** for local use — pipe-based, so there is no network
  listener and no DNS-rebinding surface.
- Each tool is **single-purpose** with explicit input validation (no "do
  anything" tool, least privilege), and the "actions" are simulated — no real
  infra is touched.
- No secrets, no filesystem/network side effects.
"""

from __future__ import annotations

import re

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("incident-ops")

# Simulated live error rates (%). A real server would query your metrics backend.
_ERROR_RATES = {
    "checkout-api": 9.2,
    "payments-api": 0.4,
    "search-api": 1.1,
}

MAX_REPLICAS = 100
_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")


@mcp.tool()
def get_error_rate(service: str) -> float:
    """Return the current error rate (%) for a service."""
    return _ERROR_RATES.get(service, 0.0)


@mcp.tool()
def rollback(service: str, version: str) -> str:
    """Roll a service back to a previous semantic version (e.g. v2.7.0)."""
    if not _VERSION_RE.match(version):
        raise ValueError("version must look like v<major>.<minor>.<patch>, e.g. v2.7.0")
    return f"rolled back {service} to {version}"


@mcp.tool()
def scale(service: str, replicas: int) -> str:
    """Scale a service to a target replica count (0-100)."""
    if not 0 <= replicas <= MAX_REPLICAS:
        raise ValueError(f"replicas must be between 0 and {MAX_REPLICAS}")
    return f"scaled {service} to {replicas} replicas"


if __name__ == "__main__":
    # FastMCP.run() defaults to the stdio transport.
    mcp.run()
