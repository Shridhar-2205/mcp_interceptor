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
    """Open a session in the given mode, list tools, run the incident playbook."""
    async with stdio_client(mcp_client._server_params(mode)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            results = {
                "error_rate": mcp_client._render(
                    await session.call_tool("get_error_rate", {"service": "checkout-api"})
                ),
                "rollback": mcp_client._render(
                    await session.call_tool("rollback", {"service": "checkout-api", "version": "v2.7.0"})
                ),
                "scale": mcp_client._render(
                    await session.call_tool("scale", {"service": "checkout-api", "replicas": 6})
                ),
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
    assert names == ["get_error_rate", "rollback", "scale"]
    assert results["error_rate"] == "9.2"
    assert results["rollback"] == "rolled back checkout-api to v2.7.0"
    assert results["scale"] == "scaled checkout-api to 6 replicas"


def test_rollback_version_validation_errors():
    result = asyncio.run(_call("direct", "rollback", {"service": "checkout-api", "version": "latest"}))
    assert result.isError is True


# --- logging interceptor --------------------------------------------------- #
def test_logging_interceptor_writes_transcript():
    if os.path.exists(INTERCEPT_LOG):
        os.remove(INTERCEPT_LOG)
    names, results = asyncio.run(_session_calls("log"))
    assert results["error_rate"] == "9.2"
    assert os.path.exists(INTERCEPT_LOG)

    # each log line is {ts, dir, raw}; raw is the actual JSON-RPC message string
    entries = [json.loads(line) for line in open(INTERCEPT_LOG, encoding="utf-8") if line.strip()]
    messages = [json.loads(e["raw"]) for e in entries]
    rollback_calls = [
        m for m in messages
        if m.get("method") == "tools/call" and m.get("params", {}).get("name") == "rollback"
    ]
    assert rollback_calls, "logging interceptor did not audit the rollback tools/call"
    assert any(e["dir"] == "client -> server" for e in entries)
    assert any(e["dir"] == "server -> client" for e in entries)


# --- file-modifying interceptor -------------------------------------------- #
def test_modify_interceptor_generates_runnable_replay():
    if os.path.exists(REPLAY_FILE):
        os.remove(REPLAY_FILE)
    names, results = asyncio.run(_session_calls("modify"))
    assert results["scale"] == "scaled checkout-api to 6 replicas"

    # the interceptor must have captured the incident as a valid, runnable runbook
    assert os.path.exists(REPLAY_FILE)
    src = open(REPLAY_FILE, encoding="utf-8").read()
    compile(src, REPLAY_FILE, "exec")  # raises SyntaxError if not valid Python
    assert "('get_error_rate', {'service': 'checkout-api'})" in src
    assert "('rollback', {'service': 'checkout-api', 'version': 'v2.7.0'})" in src

    # and running it should replay the remediation against the server
    proc = subprocess.run(
        [sys.executable, REPLAY_FILE],
        cwd=LAB_DIR, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "replay rollback({'service': 'checkout-api', 'version': 'v2.7.0'}) -> rolled back checkout-api to v2.7.0" in proc.stdout
    assert "-> scaled checkout-api to 6 replicas" in proc.stdout
