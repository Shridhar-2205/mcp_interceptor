"""End-to-end tests.

Flow: bring the proxy pipeline UP FIRST, then run the client calls.

Opening the stdio session launches the interceptor, which launches the server;
`session.initialize()` completes the MCP handshake. Only once that pipeline is
ready to listen do we send the client's tool calls — all through the single open
session (no per-call re-spawn).
"""

from __future__ import annotations

import asyncio
import os

from mcp import ClientSession
from mcp.client.stdio import stdio_client

import mcp_client

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERCEPT_LOG = os.path.join(HERE, "intercept.log")

ADD = ("add", {"a": 2, "b": 2})
GREET = ("greet", {"name": "world"})


def _text(result) -> str:
    return mcp_client._text(result)


async def _run_pipeline(mode: str, calls: list[tuple[str, dict]]):
    """Start interceptor+server ONCE (ready to listen), then run all calls."""
    async with stdio_client(mcp_client._server_params(mode)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()  # handshake done -> pipeline is ready
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            results = [_text(await session.call_tool(name, args)) for name, args in calls]
            return tools, results


# --- direct (baseline) ----------------------------------------------------- #
def test_direct_lists_and_calls_tools():
    tools, results = asyncio.run(_run_pipeline("direct", [ADD, GREET]))
    assert tools == ["add", "greet"]
    assert results == ["4", "hello, world!"]


# --- logging interceptor --------------------------------------------------- #
def test_logging_interceptor_writes_transcript():
    if os.path.exists(INTERCEPT_LOG):
        os.remove(INTERCEPT_LOG)
    tools, results = asyncio.run(_run_pipeline("log", [ADD]))
    assert results == ["4"]
    assert os.path.exists(INTERCEPT_LOG)
    content = open(INTERCEPT_LOG, encoding="utf-8").read()
    assert "client->server" in content and "server->client" in content
    assert "tools/call" in content and "add" in content


# --- malicious tampering interceptor --------------------------------------- #
def test_tamper_rewrites_add_but_leaves_greet():
    # client asks add(2, 2) -> 4, but the hostile proxy makes the server do add(2, 40)
    tools, results = asyncio.run(_run_pipeline("tamper", [ADD, GREET]))
    assert results[0] == "42"             # add hijacked in flight
    assert results[1] == "hello, world!"  # greet untouched
