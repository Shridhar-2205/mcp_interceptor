#!/usr/bin/env python3
"""Active MCP stdio interceptor that MODIFIES another Python file.

Same transparent man-in-the-middle proxy as ``interceptor.py``:

    client  <--stdio-->  interceptor_modify.py  <--stdio-->  mcp_server.py

...but with a side effect: every intercepted ``tools/call`` is captured and the
interceptor (re)writes a sibling Python file, ``replay_calls.py``, into a
runnable **runbook** that replays those exact remediation steps against the
server. So watching an incident get resolved actually rewrites another .py file
on disk, live — a reusable runbook, generated from real traffic.

Messages are still forwarded VERBATIM — this observes + code-gens, it does not
block or alter the in-flight call. Diagnostics go to stderr (never stdout).

Safety notes:
- The output path is a FIXED filename next to this file (no path comes from the
  wire), so intercepted data can't redirect the write elsewhere.
- Recorded arguments are emitted as Python literals via ``repr`` of values
  parsed by ``json.loads`` (str/int/float/bool/None/list/dict only) — data, not
  executable code — so a malicious argument can't inject code into the file.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET_FILE = os.path.join(HERE, "replay_calls.py")   # the .py file we modify
SERVER_FILE = os.path.join(HERE, "mcp_server.py")
_lock = threading.Lock()
_calls: list[tuple[str, dict]] = []   # recorded (tool_name, arguments)


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _record_if_tool_call(raw: bytes) -> None:
    """If this client->server line is a tools/call, record it and rewrite the file."""
    try:
        msg = json.loads(raw)
    except Exception:
        return
    if msg.get("method") != "tools/call":
        return
    params = msg.get("params")
    if not isinstance(params, dict) or "name" not in params:
        return
    name = str(params["name"])
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return
    with _lock:
        _calls.append((name, arguments))
        _write_replay_file()
        sys.stderr.write(
            f"[modify] captured step #{len(_calls)} ({name}) -> rewrote runbook {os.path.basename(TARGET_FILE)}\n"
        )
        sys.stderr.flush()


def _write_replay_file() -> None:
    """Rewrite replay_calls.py as a runnable runbook for the steps seen so far."""
    lines = [
        "#!/usr/bin/env python3",
        '"""AUTO-GENERATED runbook, written by interceptor_modify.py — do not edit by hand.',
        "",
        f"Captured {len(_calls)} remediation step(s) at {_ts()} by intercepting the",
        "on-call agent's MCP traffic. Run this file to replay the incident response",
        "against the server directly:  python replay_calls.py",
        '"""',
        "",
        "import asyncio",
        "import os",
        "import sys",
        "",
        "from mcp import ClientSession, StdioServerParameters",
        "from mcp.client.stdio import stdio_client",
        "",
        "HERE = os.path.dirname(os.path.abspath(__file__))",
        "",
        "# (tool_name, arguments) captured from intercepted tools/call messages",
        "STEPS = [",
    ]
    for name, args in _calls:
        lines.append(f"    ({name!r}, {args!r}),")
    lines += [
        "]",
        "",
        "",
        "async def main() -> None:",
        "    params = StdioServerParameters(",
        "        command=sys.executable, args=[os.path.join(HERE, 'mcp_server.py')]",
        "    )",
        "    async with stdio_client(params) as (read, write):",
        "        async with ClientSession(read, write) as session:",
        "            await session.initialize()",
        "            for name, arguments in STEPS:",
        "                result = await session.call_tool(name, arguments)",
        "                rendered = ' '.join(",
        "                    getattr(c, 'text', str(c)) for c in result.content",
        "                )",
        "                print(f'replay {name}({arguments}) -> {rendered}')",
        "",
        "",
        "if __name__ == '__main__':",
        "    asyncio.run(main())",
        "",
    ]
    tmp = TARGET_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp, TARGET_FILE)   # atomic swap


def _pump(src, dst, direction: str, record: bool) -> None:
    """Forward newline-delimited messages; optionally record tool calls."""
    try:
        for raw in iter(src.readline, b""):
            if record:
                _record_if_tool_call(raw)
            dst.write(raw)
            dst.flush()
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


def main() -> int:
    target = sys.argv[1:] or [sys.executable, SERVER_FILE]
    sys.stderr.write(f"[modify] proxying stdio to: {' '.join(target)}\n")
    sys.stderr.write(f"[modify] will rewrite: {TARGET_FILE}\n")
    sys.stderr.flush()

    proc = subprocess.Popen(target, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    up = threading.Thread(
        target=_pump, args=(sys.stdin.buffer, proc.stdin, "client -> server", True), daemon=True
    )
    down = threading.Thread(
        target=_pump, args=(proc.stdout, sys.stdout.buffer, "server -> client", False), daemon=True
    )
    up.start()
    down.start()

    rc = proc.wait()
    up.join(timeout=1)
    down.join(timeout=1)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
