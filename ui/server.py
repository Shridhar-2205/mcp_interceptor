#!/usr/bin/env python3
"""Web UI that showcases the standalone MCP interceptor flow.

It brings the stack UP FIRST — starts the server (:8100), the logging interceptor
(:8000), and the tampering interceptor (:8001) as standalone listeners — then, on
each request, runs the existing `mcp_client.py` against the chosen one and parses
the flow into JSON. It does NOT modify the demo code.

Run:
    python ui/server.py            # then open http://127.0.0.1:8080

Security: the UI and stack bind to localhost only; the `mode` query param is
validated against a fixed allow-list before any subprocess is launched.
"""

from __future__ import annotations

import ast
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CLIENT = os.path.join(REPO, "mcp_client.py")
LOG = os.path.join(REPO, "intercept.log")
INDEX = os.path.join(HERE, "index.html")

MODE_FLAG = {"log": [], "tamper": ["--tamper"], "direct": ["--direct"]}

_CALL_RE = re.compile(r"\[client\] (\w+)\((.*)\) -> (.*)")
_TOOLS_RE = re.compile(r"\[client\] tools: (\[.*\])")
_TAMPER_RE = re.compile(r"\[tamper\] (\w+): appended (\S+)=(\S+) into (\w+) \(in flight\)")


class Service:
    """A standalone stack process whose stdout we capture line-by-line."""

    def __init__(self, cmd: list[str], port: int) -> None:
        self.port = port
        self.lines: list[str] = []
        self.proc = subprocess.Popen(
            cmd,
            env={**os.environ, "PORT": str(port), "LOG": LOG},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout
        for line in self.proc.stdout:
            self.lines.append(line.rstrip("\n"))

    def mark(self) -> int:
        return len(self.lines)

    def since(self, n: int) -> list[str]:
        return self.lines[n:]

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


STACK: dict[str, Service] = {}


def _wait_port(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.1)
    raise RuntimeError(f"port {port} did not come up")


def _build_go() -> str:
    """Return the Go interceptor binary — prebuilt (INTERCEPTOR_BIN) or built now."""
    prebuilt = os.environ.get("INTERCEPTOR_BIN")
    if prebuilt and os.path.exists(prebuilt):
        return prebuilt
    binary = os.path.join(tempfile.gettempdir(), "mcp_interceptor_go")
    subprocess.run(["go", "build", "-o", binary, "."],
                   cwd=os.path.join(REPO, "interceptor-go"), check=True)
    return binary


def start_stack() -> None:
    binary = _build_go()
    STACK["server"] = Service([sys.executable, os.path.join(REPO, "mcp_server.py")], 8100)
    _wait_port(8100)
    STACK["log"] = Service([binary], 8000)
    STACK["tamper"] = Service([binary, "-tamper"], 8001)
    _wait_port(8000)
    _wait_port(8001)


def stop_stack() -> None:
    for svc in STACK.values():
        svc.stop()


def run_mode(mode: str) -> dict:
    interceptor = STACK.get(mode) if mode in ("log", "tamper") else None
    mark = interceptor.mark() if interceptor else 0
    if mode == "log" and os.path.exists(LOG):
        os.remove(LOG)

    proc = subprocess.run(
        [sys.executable, CLIENT, *MODE_FLAG[mode]],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    stdout = proc.stdout

    tools: list = []
    m = _TOOLS_RE.search(stdout)
    if m:
        try:
            tools = ast.literal_eval(m.group(1))
        except Exception:
            tools = []

    interceptor_lines = interceptor.since(mark) if interceptor else []
    tampered = {}
    for tm in _TAMPER_RE.finditer("\n".join(interceptor_lines)):
        tool, key, value, arg = tm.groups()
        tampered[tool] = {"key": key, "value": value, "arg": arg}

    steps = []
    for cm in _CALL_RE.finditer(stdout):
        tool, args_s, result = cm.groups()
        try:
            args = ast.literal_eval(args_s)
        except Exception:
            args = args_s
        steps.append({
            "tool": tool, "args": args, "result": result,
            "tampered": tool in tampered, "tamper": tampered.get(tool),
        })

    transcript = []
    if mode == "log" and os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8"):
            line = line.rstrip("\n")
            if ": " not in line:
                continue
            direction, raw = line.split(": ", 1)
            summary = raw[:90]
            try:
                msg = json.loads(raw)
                if msg.get("method"):
                    summary = msg["method"]
                    params = msg.get("params") or {}
                    if isinstance(params, dict) and params.get("name"):
                        summary += f"  ({params['name']})"
                elif "result" in msg:
                    summary = "result"
            except Exception:
                pass
            transcript.append({"direction": direction, "summary": summary, "raw": raw})

    return {
        "mode": mode,
        "tools": tools,
        "steps": steps,
        "transcript": transcript,
        "interceptor": [ln for ln in interceptor_lines if ln.strip()],
        "returncode": proc.returncode,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            with open(INDEX, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/run":
            mode = (parse_qs(parsed.query).get("mode") or ["log"])[0]
            if mode not in MODE_FLAG:
                self._send(400, json.dumps({"error": "invalid mode"}).encode(), "application/json")
                return
            try:
                body = json.dumps(run_mode(mode)).encode()
                self._send(200, body, "application/json")
            except Exception as exc:  # pragma: no cover
                self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    host = os.environ.get("UI_HOST", "127.0.0.1")   # set to 0.0.0.0 in Docker
    port = int(os.environ.get("UI_PORT", "8080"))
    print("Starting stack (server + interceptors)…", flush=True)
    start_stack()
    srv = ThreadingHTTPServer((host, port), Handler)
    shown = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
    print(f"MCP Interceptor UI -> http://{shown}:{port}  (Ctrl-C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        stop_stack()


if __name__ == "__main__":
    main()
