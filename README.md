# MCP Interceptor

Put a proxy between an **MCP client** and an **MCP server** and you can **see** —
or **change** — every tool call. This is the smallest possible demo of that.

```
 client  <--stdio-->  interceptor  <--stdio-->  server
                          │
                          └── logs every message   (interceptor.py)
                          └── or rewrites it        (interceptor_tamper.py)
```

The client and server are plain MCP and **don't know the interceptor is there** —
it just forwards bytes on the standard streams.

## Why it's this simple

MCP's **stdio transport** is newline-delimited JSON-RPC: the client launches the
server as a subprocess and they exchange **one JSON message per line** over
stdin/stdout. So an interceptor is just: launch the real server, and pump lines
in both directions (logging or editing them on the way). `stderr` is free for
logging; `stdout` must only carry valid MCP messages.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python mcp_client.py            # through the LOGGING interceptor  -> intercept.log
python mcp_client.py --tamper   # through the TAMPERING interceptor -> rewrites a call
python mcp_client.py --direct   # no interceptor (baseline)
```

The server has two trivial tools, `add` and `greet`. Every mode makes the same
two calls:

```
[client] tools: ['add', 'greet']
[client] add({'a': 2, 'b': 2}) -> 4
[client] greet({'name': 'world'}) -> hello, world!
```

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

Neither side can tell. A middlebox can rewrite, drop, or inject messages, so you
can't trust it for integrity — use TLS/mTLS + integrity checks on remote
transports, and gate real actions with server-side authorization, not client
intent. (Demo only — don't reuse this file.)

## See the flow (web UI)

A tiny web UI visualizes the client → interceptor → server flow. It doesn't change
the demo code — it just runs the existing `mcp_client.py` as a subprocess and
animates what happens (including the tampered call).

```bash
python ui/server.py        # stdlib only, no extra deps
# open http://127.0.0.1:8000  and pick a mode
```

Pick **Logging**, **Tamper**, or **Direct** and watch each JSON-RPC message travel
through the proxy; the tamper mode highlights the `add(2,2) -> 42` hijack in red.

## Trust model

These interceptors are a **local, authorized** man-in-the-middle. On stdio the
client itself launches the interceptor as its "server command", so the proxy runs
**inside the trust boundary by construction** — there's no network surface and no
auth is needed (per the MCP spec, stdio implementations use the environment, not
the HTTP auth framework). `interceptor.py` is a benign observer; `interceptor_tamper.py`
shows that whatever ends up in that position can abuse it, so an *unintended*
middlebox (compromised dependency, PATH/shim hijack, malicious server wrapper) is
the real risk — and on remote transports you must enforce integrity (TLS/mTLS) and
authorize real actions server-side.

## Files

| File | What |
|---|---|
| `mcp_server.py` | MCP server (stdio) with `add` and `greet` |
| `mcp_client.py` | MCP client; `--tamper` / `--direct` pick the path |
| `interceptor.py` | transparent proxy that **logs** every message |
| `interceptor_tamper.py` | ⚠️ proxy that **rewrites** an `add` call in flight |
| `ui/` | web UI (`server.py` + `index.html`) that animates the flow |
| `tests/` | end-to-end pytest coverage |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

CI runs the suite on Python 3.11–3.13 for every push and PR.

## MCP docs used to build this

- **MCP Python SDK** (server + client): https://py.sdk.modelcontextprotocol.io/
- **Writing MCP clients** (`ClientSession`, `stdio_client`, `StdioServerParameters`):
  https://py.sdk.modelcontextprotocol.io/client/
- **stdio transport** (the newline-delimited JSON-RPC framing the interceptor relies on):
  https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- **Python SDK source**: https://github.com/modelcontextprotocol/python-sdk
