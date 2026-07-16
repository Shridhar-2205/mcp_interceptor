#!/usr/bin/env python3
"""A standalone MCP interceptor you start FIRST — a tiny HTTP proxy.

The client POSTs its JSON-RPC here; we LOG each message, forward it to the real
server, and pass the reply back. We change nothing.

    client --http--> interceptor.py (:8000) --http--> mcp_server.py (:8100)

Docs: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
"""

import os

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route

PORT = int(os.environ.get("PORT", "8000"))                          # where we listen
UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:8100/mcp")  # the real server
LOG = os.path.join(os.path.dirname(__file__), "intercept.log")


def note(direction: str, body: bytes) -> None:
    """Print one message and append it to intercept.log."""
    text = body.decode("utf-8", "replace").strip()
    if text:
        print(f"[log] {direction}: {text[:200]}", flush=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{direction}: {text}\n")


async def proxy(request):
    body = await request.body()
    note("client->server", body)

    # forward to the real server (drop headers the HTTP layer sets for us)
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}
    async with httpx.AsyncClient() as http:
        reply = await http.request(request.method, UPSTREAM, content=body, headers=headers)

    note("server->client", reply.content)
    return Response(reply.content, reply.status_code,
                    media_type=reply.headers.get("content-type"))


app = Starlette(routes=[Route("/mcp", proxy, methods=["POST", "GET", "DELETE"])])

if __name__ == "__main__":
    print(f"[log] interceptor on :{PORT} -> {UPSTREAM}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
