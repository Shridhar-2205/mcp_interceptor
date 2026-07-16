# MCP Interceptor

Sit a proxy between an MCP client and server and you can intercept every **tool
call** (`tools/call`) — watch it go by (logging) or rewrite its JSON payload before
it reaches the server (tamper). Client and server are Python, the interceptor is a
dependency-free Go program; they talk MCP over HTTP (JSON-RPC), so the language on
either end doesn't matter.

```mermaid
flowchart LR
    C["client<br/>mcp_client.py<br/>sends cart JSON"]
    L["interceptor-go :8000<br/>logs only"]
    T["interceptor-go -tamper :8001<br/>appends laptop=999 to cart"]
    S["server<br/>mcp_server.py :8100<br/>checkout, greet"]
    C --> L
    C -.->|"--tamper"| T
    L --> S
    T -->|"changed"| S
    S --> L
    S --> T
```

Three independent processes on their own ports; the client connects to whatever
URL you give it (so `--direct` skips the proxy).

## Run it

Docker — nothing else needed, opens the web UI:

```bash
docker compose up --build          # http://localhost:8080
```

Or locally (Python + Go), one per terminal:

```bash
pip install -r requirements.txt
python mcp_server.py                 # server      :8100
cd interceptor-go && go run .        # interceptor :8000  (add -tamper for :8001)
python mcp_client.py                 # client -> :8000  (--tamper :8001, --direct :8100)
```

Prefer the UI locally? `python ui/server.py`, then open http://127.0.0.1:8080.

## What the demo does

The client makes a **tool call**: `checkout` with a hardcoded JSON cart
`{"apple": 2, "bread": 3}`. The server sums it (`total=5`). The interceptor sees
that `tools/call` on the way through:

- **log** (default) — forwards the tool call unchanged and writes `intercept.log`.
  The result stays `total=5`.
- **tamper** (`-tamper`) — intercepts the tool call and appends `laptop=999` into
  the cart JSON *in flight*, so the server processes three items and returns
  `total=1004`. Neither side notices. A middle proxy can change anything, so only
  run one you trust and let the server decide what's allowed.

`greet` is a tool call with no JSON payload, so it passes through untouched — a
handy contrast that shows interception is selective.

## How it works

MCP is JSON-RPC (`initialize`, `tools/list`, `tools/call`) over a transport. This
uses Streamable HTTP in stateless-JSON mode: one `POST /mcp` per message, JSON in,
JSON out. So the interceptor is just *read body → log/edit → forward → return*,
using Go's stdlib. (stdio can't do this — there the client spawns the server, so
there's nothing to start first and point at.)

The tamper proxy parses the `tools/call` body, finds the argument that is itself a
JSON object (the cart), and slips an extra key/value in before forwarding — that's
the whole trick.

## Layout

| Path | What |
|---|---|
| `mcp_server.py` / `mcp_client.py` | MCP server and client (Python) |
| `interceptor-go/` | the Go interceptor (`-tamper` to append to the payload) |
| `ui/` | web UI that runs and animates the stack |
| `tests/`, `Dockerfile`, `docker-compose.yml` | tests and container |

## Tests

```bash
pip install -r requirements.txt && pytest -q     # needs Go
docker compose run --rm ui pytest -q             # or in Docker
```

## Links

- [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)
- [Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
