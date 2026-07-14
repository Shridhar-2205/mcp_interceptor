"""End-to-end tests for the MCP client/server and the two interceptors.

Each test drives a real MCP session over stdio (spawning the interceptor and
server as subprocesses) and asserts on the results and the side effects
(intercept.log / replay_calls.py). No pytest-asyncio needed — we drive the async
sessions with asyncio.run().
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys

from mcp import ClientSession
from mcp.client.stdio import stdio_client

import mcp_client

LAB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERCEPT_LOG = os.path.join(LAB_DIR, "intercept.log")
REPLAY_FILE = os.path.join(LAB_DIR, "replay_calls.py")


async def _session_calls(mode: str):
    """Open a session in the given mode, list tools, run the 3 standard calls."""
    async with stdio_client(mcp_client._server_params(mode)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            results = {
                "add": mcp_client._render(await session.call_tool("add", {"a": 2, "b": 3})),
                "echo": mcp_client._render(await session.call_tool("echo", {"text": "hi"})),
                "slug": mcp_client._render(await session.call_tool("slugify", {"text": "On Call L9"})),
            }
            return names, results


async def _call(mode: str, name: str, args: dict):
    async with stdio_client(mcp_client._server_params(mode)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(name, args)


# --- tools / direct -------------------------------------------------------- #
def test_direct_lists_and_calls_tools():
    names, results = asyncio.run(_session_calls("direct"))
    assert names == ["add", "echo", "slugify"]
    assert results["add"] == "5"
    assert results["echo"] == "hi"
    assert results["slug"] == "on-call-l9"


def test_echo_length_validation_errors():
    result = asyncio.run(_call("direct", "echo", {"text": "x" * 600}))
    assert result.isError is True


# --- logging interceptor --------------------------------------------------- #
def test_logging_interceptor_writes_transcript():
    if os.path.exists(INTERCEPT_LOG):
        os.remove(INTERCEPT_LOG)
    names, results = asyncio.run(_session_calls("log"))
    assert results["add"] == "5"
    assert os.path.exists(INTERCEPT_LOG)

    # each log line is {ts, dir, raw}; raw is the actual JSON-RPC message string
    entries = [json.loads(line) for line in open(INTERCEPT_LOG, encoding="utf-8") if line.strip()]
    messages = [json.loads(e["raw"]) for e in entries]
    add_calls = [
        m for m in messages
        if m.get("method") == "tools/call" and m.get("params", {}).get("name") == "add"
    ]
    assert add_calls, "logging interceptor did not capture the add tools/call"
    assert any(e["dir"] == "client -> server" for e in entries)
    assert any(e["dir"] == "server -> client" for e in entries)


# --- file-modifying interceptor -------------------------------------------- #
def test_modify_interceptor_generates_runnable_replay():
    if os.path.exists(REPLAY_FILE):
        os.remove(REPLAY_FILE)
    names, results = asyncio.run(_session_calls("modify"))
    assert results["slug"] == "on-call-l9"

    # the interceptor must have written a valid, runnable replay file
    assert os.path.exists(REPLAY_FILE)
    src = open(REPLAY_FILE, encoding="utf-8").read()
    compile(src, REPLAY_FILE, "exec")  # raises SyntaxError if not valid Python
    assert "('add', {'a': 2, 'b': 3})" in src
    assert "('slugify', {'text': 'On Call L9'})" in src

    # and running it should replay the calls against the server
    proc = subprocess.run(
        [sys.executable, REPLAY_FILE],
        cwd=LAB_DIR, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "replay add({'a': 2, 'b': 3}) -> 5" in proc.stdout
    assert "-> on-call-l9" in proc.stdout
