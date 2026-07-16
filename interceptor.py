#!/usr/bin/env python3
"""A transparent MCP interceptor: sit between client and server and LOG every
message, forwarding each one unchanged.

Why this is so simple: MCP's stdio transport is newline-delimited JSON-RPC — one
message per line over the server's stdin/stdout. So a proxy just pumps lines both
ways. (stderr is free for logging; stdout is the live channel and must only carry
valid MCP messages.)

    client  <--stdio-->  interceptor.py  <--stdio-->  mcp_server.py

Spec: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "intercept.log")
_lock = threading.Lock()


def pump(src, dst, label: str) -> None:
    """Forward each newline-delimited message from src to dst, logging it."""
    for line in iter(src.readline, b""):
        text = line.decode("utf-8", "replace").rstrip("\n")
        with _lock:
            sys.stderr.write(f"[log] {label}: {text}\n")
            sys.stderr.flush()
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(f"{label}: {text}\n")
        dst.write(line)
        dst.flush()
    dst.close()


def main() -> int:
    server = sys.argv[1:] or [sys.executable, os.path.join(HERE, "mcp_server.py")]
    sys.stderr.write(f"[log] proxying to: {' '.join(server)}  (transcript -> {LOG})\n")
    sys.stderr.flush()

    proc = subprocess.Popen(server, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    threading.Thread(target=pump, args=(sys.stdin.buffer, proc.stdin, "client->server"), daemon=True).start()
    threading.Thread(target=pump, args=(proc.stdout, sys.stdout.buffer, "server->client"), daemon=True).start()
    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
