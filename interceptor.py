#!/usr/bin/env python3
"""Standalone MCP interceptor — a real HTTP listener you start FIRST.

It sits between the client and the upstream server on the Streamable-HTTP
transport, forwarding every JSON-RPC message and LOGGING it (to stderr and
intercept.log). Start order:  server  ->  interceptor (this)  ->  client.

    client --http--> interceptor.py (:8000) --http--> mcp_server.py (:8100)

Trust model: this is a *local, authorized* man-in-the-middle — you run it on
purpose and point the client at it. It's a benign observer that forwards every
message unchanged. (See interceptor_tamper.py for what a hostile one could do.)

Docs: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
"""

from __future__ import annotations

import os

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "intercept.log")

PORT = int(os.environ.get("PORT", "8000"))
UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:8100/mcp")


def log(direction: str, body: bytes) -> None:
    text = body.decode("utf-8", "replace").strip()
    if not text:
        return
    print(f"[log] {direction}: {text[:200]}", flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{direction}: {text}\n")


def transform(body: bytes) -> bytes:
    """Logging proxy forwards the request unchanged."""
    return body


async def proxy(request):
    body = transform(await request.body())
    log("client->server", body)

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}
    async with httpx.AsyncClient(timeout=30) as client:
        upstream = await client.request(
            request.method, UPSTREAM, content=body,
            headers=headers, params=dict(request.query_params),
        )

    log("server->client", upstream.content)
    resp_headers = {k: v for k, v in upstream.headers.items()
                    if k.lower() not in ("content-length", "transfer-encoding", "connection")}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=resp_headers)


app = Starlette(routes=[Route("/mcp", proxy, methods=["GET", "POST", "DELETE"])])


if __name__ == "__main__":
    print(f"[log] interceptor on http://127.0.0.1:{PORT}/mcp -> {UPSTREAM}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
