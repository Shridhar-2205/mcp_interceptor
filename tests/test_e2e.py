"""End-to-end tests: real MCP sessions over stdio, direct and through both
interceptors. No pytest-asyncio needed — we drive the async sessions with
asyncio.run().
"""

from __future__ import annotations

import asyncio
import os

from mcp import ClientSession
from mcp.client.stdio import stdio_client

import mcp_client

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERCEPT_LOG = os.path.join(HERE, "intercept.log")


async def _call(mode: str, name: str, args: dict):
    async with stdio_client(mcp_client._server_params(mode)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(name, args)


async def _tools(mode: str):
    async with stdio_client(mcp_client._server_params(mode)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return sorted(t.name for t in tools.tools)


def _text(result) -> str:
    return mcp_client._text(result)


# --- direct (baseline) ----------------------------------------------------- #
def test_direct_lists_and_calls_tools():
    assert asyncio.run(_tools("direct")) == ["add", "greet"]
    assert _text(asyncio.run(_call("direct", "add", {"a": 2, "b": 2}))) == "4"
    assert _text(asyncio.run(_call("direct", "greet", {"name": "world"}))) == "hello, world!"


# --- logging interceptor --------------------------------------------------- #
def test_logging_interceptor_writes_transcript():
    if os.path.exists(INTERCEPT_LOG):
        os.remove(INTERCEPT_LOG)
    assert _text(asyncio.run(_call("log", "add", {"a": 2, "b": 2}))) == "4"
    assert os.path.exists(INTERCEPT_LOG)
    content = open(INTERCEPT_LOG, encoding="utf-8").read()
    assert "client->server" in content and "server->client" in content
    assert "tools/call" in content and "add" in content


# --- malicious tampering interceptor --------------------------------------- #
def test_tamper_rewrites_add_in_flight():
    # client asks add(2, 2) -> 4, but the hostile proxy makes the server do add(2, 40)
    assert _text(asyncio.run(_call("tamper", "add", {"a": 2, "b": 2}))) == "42"


def test_tamper_leaves_greet_untouched():
    assert _text(asyncio.run(_call("tamper", "greet", {"name": "world"}))) == "hello, world!"
