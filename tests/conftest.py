"""Test setup: make project modules importable, and bring the standalone stack up
FIRST (server + both interceptors) before any client connects."""

import os
import socket
import subprocess
import sys
import time

import pytest

# tests/ -> project root (so `import mcp_client` etc. resolve)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


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


def _spawn(script: str, port: int) -> subprocess.Popen:
    env = {**os.environ, "PORT": str(port)}
    return subprocess.Popen(
        [sys.executable, os.path.join(ROOT, script)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


@pytest.fixture(scope="session")
def stack():
    """Start server(8100), logging interceptor(8000), tamper interceptor(8001)."""
    procs = []
    try:
        procs.append(_spawn("mcp_server.py", 8100))
        _wait_port(8100)
        procs.append(_spawn("interceptor.py", 8000))
        procs.append(_spawn("interceptor_tamper.py", 8001))
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
