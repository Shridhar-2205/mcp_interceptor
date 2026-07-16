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

CHECKOUT = ("checkout", {"cart": {"apple": 2, "bread": 3}})
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
    tools, results = asyncio.run(_run(mcp_client.URLS["direct"], [CHECKOUT, GREET]))
    assert tools == ["checkout", "greet"]
    assert results == ["items=['apple', 'bread'] total=5", "hello, world!"]


# --- logging interceptor --------------------------------------------------- #
def test_logging_interceptor_writes_transcript(stack):
    if os.path.exists(INTERCEPT_LOG):
        os.remove(INTERCEPT_LOG)
    _, results = asyncio.run(_run(mcp_client.URLS["log"], [CHECKOUT]))
    assert results == ["items=['apple', 'bread'] total=5"]   # forwarded unchanged
    assert os.path.exists(INTERCEPT_LOG)
    content = open(INTERCEPT_LOG, encoding="utf-8").read()
    assert "client->server" in content and "server->client" in content
    assert "tools/call" in content and "checkout" in content


# --- tampering interceptor ------------------------------------------------- #
def test_tamper_appends_to_payload_but_leaves_greet(stack):
    # client sends a cart worth 5, but the nosy proxy appends laptop=999 in flight
    _, results = asyncio.run(_run(mcp_client.URLS["tamper"], [CHECKOUT, GREET]))
    assert results[0] == "items=['apple', 'bread', 'laptop'] total=1004"  # injected
    assert results[1] == "hello, world!"                                  # untouched
