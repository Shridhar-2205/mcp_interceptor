#!/usr/bin/env python3
"""Transparent MCP stdio interceptor (man-in-the-middle proxy).

The MCP client launches THIS process instead of the real server, and this
process launches the real server:

    client  <--stdio-->  interceptor.py  <--stdio-->  mcp_server.py

MCP's stdio transport is newline-delimited JSON-RPC, so every message is a
single line. The interceptor logs each line (a human summary to stderr + the
full raw JSON to ``intercept.log``) and forwards it verbatim, so the client and
server behave exactly as if they were wired directly together.

IMPORTANT: logs NEVER go to stdout — stdout is the live JSON-RPC channel back to
the client. Diagnostics go to stderr and the log file only.

Usage (normally the client does this for you):

    python interceptor.py [<server-cmd> <args>...]
    # default target: python mcp_server.py  (next to this file)
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "intercept.log")
_lock = threading.Lock()


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _summary(direction: str, raw: bytes) -> str:
    """A short, human-readable one-liner describing a JSON-RPC message."""
    try:
        msg = json.loads(raw)
    except Exception:
        return f"{direction}  <non-json {len(raw)}B>"
    parts: list[str] = []
    if "method" in msg:
        parts.append(f"method={msg['method']}")
    if "id" in msg:
        parts.append(f"id={msg['id']}")
    params = msg.get("params")
    if isinstance(params, dict) and params.get("name"):
        parts.append(f"tool={params['name']}")
    if "error" in msg and isinstance(msg["error"], dict):
        parts.append(f"error={msg['error'].get('message')}")
    elif "result" in msg:
        parts.append("result=ok")
    return f"{direction}  " + " ".join(parts)


def _log(direction: str, raw: bytes) -> None:
    line = raw.decode("utf-8", "replace").rstrip("\n")
    if not line:
        return
    with _lock:
        sys.stderr.write(f"[{_ts()}] {_summary(direction, raw)}\n")
        sys.stderr.flush()
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _ts(), "dir": direction, "raw": line}) + "\n")


def _pump(src, dst, direction: str) -> None:
    """Forward newline-delimited messages from src to dst, logging each."""
    try:
        for raw in iter(src.readline, b""):
            _log(direction, raw)
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
    target = sys.argv[1:] or [sys.executable, os.path.join(HERE, "mcp_server.py")]
    sys.stderr.write(f"[interceptor] proxying stdio to: {' '.join(target)}\n")
    sys.stderr.write(f"[interceptor] full transcript -> {LOG_PATH}\n")
    sys.stderr.flush()

    proc = subprocess.Popen(target, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    up = threading.Thread(
        target=_pump, args=(sys.stdin.buffer, proc.stdin, "client -> server"), daemon=True
    )
    down = threading.Thread(
        target=_pump, args=(proc.stdout, sys.stdout.buffer, "server -> client"), daemon=True
    )
    up.start()
    down.start()

    rc = proc.wait()
    up.join(timeout=1)
    down.join(timeout=1)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
