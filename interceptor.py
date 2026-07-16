#!/usr/bin/env python3
"""Standalone MCP interceptor — a small HTTP server you start FIRST.

It sits in the middle of the Streamable-HTTP transport: the client sends its
JSON-RPC messages here, this proxy LOGS each one, and then forwards it to the
real server. The server's replies are logged and passed back the same way.

    client --http--> interceptor.py (:8000) --http--> mcp_server.py (:8100)

Start order:  server  ->  interceptor (this)  ->  client

This is a friendly observer: it changes nothing, it just watches the traffic.
(See interceptor_tamper.py for what a nosy proxy could do instead.)

Docs: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
"""

from __future__ import annotations

import os

import httpx                                   # used to forward requests upstream
import uvicorn                                 # the little web server that runs us
from starlette.applications import Starlette   # tiny web framework
from starlette.responses import Response
from starlette.routing import Route

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "intercept.log")      # full transcript is written here

# Where we listen, and where we forward to. Both are overridable via env vars.
PORT = int(os.environ.get("PORT", "8000"))
UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:8100/mcp")


def log(direction: str, body: bytes) -> None:
    """Print one message to the console and append it to intercept.log."""
    text = body.decode("utf-8", "replace").strip()
    if not text:
        return
    print(f"[log] {direction}: {text[:200]}", flush=True)   # short line for the console
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{direction}: {text}\n")                    # full line for the file


def transform(body: bytes) -> bytes:
    """The logging proxy forwards the request unchanged (tamper.py overrides this)."""
    return body


async def proxy(request):
    """Handle one incoming request: log it, forward it, log + return the reply."""
    body = transform(await request.body())
    log("client->server", body)

    # Copy the client's headers, minus a couple the HTTP layer will set for us.
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}

    # Forward the (possibly rewritten) message to the real server.
    async with httpx.AsyncClient(timeout=30) as client:
        upstream = await client.request(
            request.method, UPSTREAM, content=body,
            headers=headers, params=dict(request.query_params),
        )

    # Log the server's reply and hand it straight back to the client.
    log("server->client", upstream.content)
    resp_headers = {k: v for k, v in upstream.headers.items()
                    if k.lower() not in ("content-length", "transfer-encoding", "connection")}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=resp_headers)


# One route: everything the MCP client sends goes to /mcp.
app = Starlette(routes=[Route("/mcp", proxy, methods=["GET", "POST", "DELETE"])])


if __name__ == "__main__":
    print(f"[log] interceptor on http://127.0.0.1:{PORT}/mcp -> {UPSTREAM}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
