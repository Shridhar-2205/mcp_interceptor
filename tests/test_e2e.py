"""End-to-end tests over Streamable HTTP.

Flow: the `stack` fixture starts the server and both interceptors FIRST (they are
standalone listeners), then each test connects the client to the right URL and
runs the tool calls through the already-running pipeline.
"""

from __future__ import annotations

import asyncio
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import mcp_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERCEPT_LOG = os.path.join(ROOT, "intercept.log")

ADD = ("add", {"a": 2, "b": 2})
GREET = ("greet", {"name": "world"})


def _text(result) -> str:
    return mcp_client._text(result)


async def _run(url: str, calls):
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            results = [_text(await session.call_tool(name, args)) for name, args in calls]
            return tools, results


# --- direct (baseline) ----------------------------------------------------- #
def test_direct_lists_and_calls_tools(stack):
    tools, results = asyncio.run(_run(mcp_client.URLS["direct"], [ADD, GREET]))
    assert tools == ["add", "greet"]
    assert results == ["4", "hello, world!"]


# --- logging interceptor --------------------------------------------------- #
def test_logging_interceptor_writes_transcript(stack):
    if os.path.exists(INTERCEPT_LOG):
        os.remove(INTERCEPT_LOG)
    _, results = asyncio.run(_run(mcp_client.URLS["log"], [ADD]))
    assert results == ["4"]
    assert os.path.exists(INTERCEPT_LOG)
    content = open(INTERCEPT_LOG, encoding="utf-8").read()
    assert "client->server" in content and "server->client" in content
    assert "tools/call" in content and "add" in content


# --- malicious tampering interceptor --------------------------------------- #
def test_tamper_rewrites_add_but_leaves_greet(stack):
    # client asks add(2, 2) -> 4, but the hostile proxy makes the server do add(2, 40)
    _, results = asyncio.run(_run(mcp_client.URLS["tamper"], [ADD, GREET]))
    assert results[0] == "42"             # add hijacked in flight
    assert results[1] == "hello, world!"  # greet untouched
