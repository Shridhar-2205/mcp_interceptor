#!/usr/bin/env python3
"""Tiny web UI backend that showcases the MCP interceptor flow.

It does NOT modify the demo code. It simply runs the existing `mcp_client.py`
(which launches `interceptor.py` / `interceptor_tamper.py` and the server) as a
subprocess, then parses stdout/stderr/intercept.log into JSON for the browser.

Run:
    python ui/server.py            # then open http://127.0.0.1:8000

Security: binds to localhost only; the `mode` query param is validated against a
fixed allow-list, so nothing user-supplied ever reaches the subprocess command.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CLIENT = os.path.join(REPO, "mcp_client.py")
LOG = os.path.join(REPO, "intercept.log")
INDEX = os.path.join(HERE, "index.html")

# allow-list: maps a UI mode to the flags passed to the real client
MODE_FLAG = {"log": [], "tamper": ["--tamper"], "direct": ["--direct"]}

_CALL_RE = re.compile(r"\[client\] (\w+)\((.*)\) -> (.*)")
_TOOLS_RE = re.compile(r"\[client\] tools: (\[.*\])")
_TAMPER_RE = re.compile(r"\[tamper\] (\w+): (\w+) (.+?) -> (.+?) \(in flight\)")


def run_mode(mode: str) -> dict:
    """Run the existing client once in the given mode and parse the flow."""
    flag = MODE_FLAG[mode]
    if os.path.exists(LOG):
        os.remove(LOG)

    proc = subprocess.run(
        [sys.executable, CLIENT, *flag],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    stdout, stderr = proc.stdout, proc.stderr

    tools: list = []
    m = _TOOLS_RE.search(stdout)
    if m:
        try:
            tools = ast.literal_eval(m.group(1))
        except Exception:
            tools = []

    # what the interceptor changed, keyed by tool name
    tampered: dict[str, dict] = {}
    for tm in _TAMPER_RE.finditer(stderr):
        tool, arg, frm, to = tm.groups()
        tampered[tool] = {"arg": arg, "from": frm, "to": to}

    # client-visible calls (request args + returned result)
    steps = []
    for cm in _CALL_RE.finditer(stdout):
        tool, args_s, result = cm.groups()
        try:
            args = ast.literal_eval(args_s)
        except Exception:
            args = args_s
        steps.append({
            "tool": tool,
            "args": args,
            "result": result,
            "tampered": tool in tampered,
            "tamper": tampered.get(tool),
        })

    # full wire transcript (only the logging interceptor writes the file)
    transcript = []
    if os.path.exists(LOG):
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
                elif "error" in msg:
                    summary = "error"
            except Exception:
                pass
            transcript.append({"direction": direction, "summary": summary, "raw": raw})

    return {
        "mode": mode,
        "tools": tools,
        "steps": steps,
        "transcript": transcript,
        # only the interceptor's own lines ([log]/[tamper]); skip the server's stderr
        "interceptor": [ln for ln in stderr.splitlines() if ln.strip().startswith("[")],
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

    def log_message(self, *args) -> None:  # keep the console quiet
        pass


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"MCP Interceptor UI -> http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
