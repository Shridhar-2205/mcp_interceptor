"""Test setup: make project modules importable, and bring the standalone stack up
FIRST (Python server + the Go interceptor, log + tamper) before any client connects.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest

# tests/ -> project root (so `import mcp_client` etc. resolve)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

INTERCEPT_LOG = os.path.join(ROOT, "intercept.log")


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
                   cwd=os.path.join(ROOT, "interceptor-go"), check=True)
    return binary


def _spawn(cmd: list[str], port: int) -> subprocess.Popen:
    env = {**os.environ, "PORT": str(port), "LOG": INTERCEPT_LOG}
    return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture(scope="session")
def stack():
    """Start server(8100), logging interceptor(8000), tamper interceptor(8001)."""
    binary = _build_go()
    procs = []
    try:
        procs.append(_spawn([sys.executable, os.path.join(ROOT, "mcp_server.py")], 8100))
        _wait_port(8100)
        procs.append(_spawn([binary], 8000))
        procs.append(_spawn([binary, "-tamper"], 8001))
        _wait_port(8000)
        _wait_port(8001)
        yield
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
