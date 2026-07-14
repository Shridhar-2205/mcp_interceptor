#!/usr/bin/env python3
"""On-call agent (MCP client) that remediates an incident THROUGH the interceptor.

Wiring:  mcp_client  ->  interceptor.py  ->  mcp_server   (all over stdio)

The client plays an AI on-call agent working a "checkout-api" incident: it reads
the error rate, rolls back the bad deploy, then scales the service out. It spawns
the interceptor as its "server command"; the interceptor spawns the real server.
To the client this is indistinguishable from talking to the server directly — but
every high-impact call is audited (and optionally captured as a runbook) by the
interceptor in the middle.

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
    name = {
        "modify": "interceptor_modify.py",
        "tamper": "interceptor_tamper.py",
    }.get(mode, "interceptor.py")
    interceptor = os.path.join(HERE, name)
    return StdioServerParameters(command=sys.executable, args=[interceptor, sys.executable, server])


def _render(result) -> str:
    return " ".join(getattr(c, "text", str(c)) for c in result.content)


async def main() -> None:
    if "--direct" in sys.argv:
        mode = "direct"
    elif "--modify" in sys.argv:
        mode = "modify"
    elif "--tamper" in sys.argv:
        mode = "tamper"
    else:
        mode = "log"
    label = {"direct": "directly to server",
             "modify": "through the file-modifying interceptor",
             "tamper": "through the MALICIOUS tampering interceptor",
             "log": "through the logging interceptor"}[mode]
    print(f"[client] connecting {label}\n")

    async with stdio_client(_server_params(mode)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("[client] tools:", [t.name for t in tools.tools])

            # Incident playbook: assess -> roll back the bad deploy -> scale out.
            calls = [
                ("get_error_rate", {"service": "checkout-api"}),
                ("rollback", {"service": "checkout-api", "version": "v2.7.0"}),
                ("scale", {"service": "checkout-api", "replicas": 6}),
            ]
            for name, args in calls:
                result = await session.call_tool(name, args)
                print(f"[client] call {name}({args}) -> {_render(result)}")


if __name__ == "__main__":
    asyncio.run(main())
