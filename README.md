# MCP Interceptor

Put a proxy between an **MCP client** and an **MCP server** and you can **see** —
or **change** — every tool call. This is the smallest possible demo of that, using
MCP's **Streamable HTTP** transport so the interceptor is a **standalone server you
start first**.

```
 client  --http-->  interceptor  --http-->  server
                        │
                        ├── logs every message   (interceptor.py,        :8000)
                        └── or rewrites it        (interceptor_tamper.py, :8001)

 server = mcp_server.py (:8100)
```

The client just points at a URL; the server is plain MCP. Neither knows the
interceptor is there — it forwards the JSON-RPC over HTTP.

## Start order (this is the point)

Each piece is its own listener, so you bring them up **in order**, then run the
client:

```
1. server        (:8100)   →   2. interceptor (:8000/:8001)   →   3. client
```

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) start the server (leave it running)
python mcp_server.py

# 2) start an interceptor (new terminal, leave it running)
python interceptor.py            # LOGGING   on :8000 -> intercept.log
python interceptor_tamper.py     # TAMPERING on :8001 (run instead / as well)

# 3) run the client (new terminal)
python mcp_client.py             # -> logging interceptor  (:8000)
python mcp_client.py --tamper    # -> tampering interceptor (:8001)
python mcp_client.py --direct    # -> server directly       (:8100, no interceptor)
```

The server has two trivial tools, `add` and `greet`. Every mode makes the same
two calls:

```
[client] tools: ['add', 'greet']
[client] add({'a': 2, 'b': 2}) -> 4
[client] greet({'name': 'world'}) -> hello, world!
```

## Why it's this simple

The server runs Streamable HTTP in **stateless JSON** mode, so each request is a
plain `POST /mcp` whose body is one JSON-RPC message and whose response is one
JSON-RPC message. An interceptor is therefore just a tiny HTTP proxy: read the
POST body (log or edit it), forward it upstream, return the response.

### Logging interceptor — `interceptor.py`

Logs each message and forwards it unchanged (full transcript in `intercept.log`):

```
[log] client->server: {"method":"tools/call","params":{"name":"add","arguments":{"a":2,"b":2}},...}
[log] server->client: {"result":{"content":[{"type":"text","text":"4"}],...}}
```

### ⚠️ Tamper interceptor — `interceptor_tamper.py` (security demo)

Does **not** forward the request unchanged — it rewrites `add`'s second argument
in flight, so the client asks `add(2, 2)` but the server actually runs `add(2, 40)`:

```
$ python mcp_client.py --tamper
[tamper] add: b 2 -> 40 (in flight)
[client] add({'a': 2, 'b': 2}) -> 42       ◀── client asked for 4, got 42
```

Neither side can tell. Anything in the middle can rewrite, drop, or inject
messages — so only run a proxy you actually trust, and let the **server** decide
what actions are really allowed. (Demo only — don't reuse this file.)

## See the flow (web UI)

A tiny web UI **starts the whole stack for you** (server + both interceptors),
then runs the existing `mcp_client.py` against the mode you pick and animates the
client → interceptor → server flow. It doesn't change the demo code.

```bash
python ui/server.py        # brings up the stack, then serves the UI
# open http://127.0.0.1:8080  and pick a mode
```

Pick **Logging**, **Tamper**, or **Direct** and watch each JSON-RPC message travel
through the proxy; the tamper mode highlights the `add(2,2) -> 42` hijack in red.

## Trust model

You run these interceptors on purpose and point the client at their URL, so
they're something you already trust. `interceptor.py` just watches; `interceptor_tamper.py`
shows that whatever sits in the middle *could* change the traffic instead. The
takeaway: only run a proxy you trust, and let the **server** decide what actions
are really allowed rather than trusting whatever the client sent.

## Files

| File | What |
|---|---|
| `mcp_server.py` | MCP server over Streamable HTTP with `add` and `greet` (:8100) |
| `mcp_client.py` | MCP client; `--tamper` / `--direct` pick the target URL |
| `interceptor.py` | standalone HTTP proxy that **logs** every message (:8000) |
| `interceptor_tamper.py` | ⚠️ standalone HTTP proxy that **rewrites** an `add` call (:8001) |
| `ui/` | web UI (`server.py` + `index.html`) that starts the stack and animates it |
| `tests/` | end-to-end pytest coverage |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The test fixture starts the server and both interceptors **first**, then connects
the client — the same start order as above. CI runs the suite on Python 3.11–3.13
for every push and PR.

## MCP docs used to build this

- **MCP Python SDK** (server + client): https://py.sdk.modelcontextprotocol.io/
- **Writing MCP clients** (`ClientSession`, `streamable_http_client`):
  https://py.sdk.modelcontextprotocol.io/client/
- **Streamable HTTP transport** (the JSON-RPC-over-HTTP framing the interceptor relies on):
  https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- **Python SDK source**: https://github.com/modelcontextprotocol/python-sdk
