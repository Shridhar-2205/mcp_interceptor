# MCP Interceptor — sit in the middle of an AI agent's tool calls

**Put a proxy between an MCP client and server and you can see — and reshape —
every tool call an AI agent makes.** This repo is a tiny, dependency-light demo
of exactly that: an **interceptor** that transparently sits in the middle of an
MCP stdio session.

```
 AI agent  ── tools/call ──▶  ┌─────────────┐  ── tools/call ──▶  tool server
(mcp_client) ◀── result ───   │ INTERCEPTOR │   ◀── result ─────  (mcp_server)
                              └─────────────┘
                                     │
                          sees every message ─┬─▶ audit log  (intercept.log)
                                              └─▶ runbook code (replay_calls.py)
```

The client and server are 100% standard MCP and **don't know the interceptor is
there** — it just forwards bytes. But because it's in the middle, it can:

- **👀 Audit** — capture a full transcript of every call and result
  ("who told the AI to run `rollback` in prod?").
- **📼 Record & replay** — turn a live session into a runnable script.
- **🧱 Extend** — the same seam is where you'd add redaction, policy checks, or
  approval gates in a real system... or, as `interceptor_tamper.py` demonstrates,
  where a **malicious** proxy could rewrite calls in flight.

## Try it in 30 seconds

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python mcp_client.py            # 1) through the AUDIT interceptor   -> intercept.log
python mcp_client.py --modify   # 2) through the RUNBOOK interceptor -> replay_calls.py
python mcp_client.py --tamper   # 3) through a MALICIOUS interceptor -> rewrites a call in flight
python mcp_client.py --direct   # 4) no interceptor (baseline)
```

The demo runs a small story so the output is meaningful: an **AI on-call agent**
works a `checkout-api` incident — it reads the error rate, rolls back the bad
deploy, and scales the service out. Every scenario prints the same thing:

```
[client] tools: ['get_error_rate', 'rollback', 'scale']
[client] call get_error_rate({'service': 'checkout-api'}) -> 9.2
[client] call rollback({'service': 'checkout-api', 'version': 'v2.7.0'}) -> rolled back checkout-api to v2.7.0
[client] call scale({'service': 'checkout-api', 'replicas': 6}) -> scaled checkout-api to 6 replicas
```

...but the interesting part is what the **interceptor** does with those calls.

## What the interceptor sees

MCP's stdio transport is **newline-delimited JSON-RPC** — one message per line.
The client launches the interceptor *as if it were the server*; the interceptor
launches the real server and pumps bytes both ways, tapping each line and
forwarding it verbatim.

> **Key trick:** diagnostics go to **stderr**/files only — never stdout, because
> stdout is the live JSON-RPC channel back to the client.

### 1) Audit interceptor — `interceptor.py`

Logs a human summary to stderr and the full raw JSON to `intercept.log`, then
forwards each message unchanged:

```
$ python mcp_client.py
client -> server  method=tools/call id=3 tool=rollback     ◀── the interceptor sees this
server -> client  id=3 result=ok

$ cat intercept.log     # full JSON-RPC transcript, one message per line
{"ts": "...", "dir": "client -> server", "raw": "{...\"method\":\"tools/call\",\"params\":{\"name\":\"rollback\",...}}"}
```

That `intercept.log` is your audit trail / forensics record of everything the
agent did and got back.

### 2) Runbook interceptor — `interceptor_modify.py`

Same transparent proxy, but each intercepted `tools/call` is captured and the
interceptor **(re)writes `replay_calls.py`** into a runnable runbook of those
exact steps — so watching an incident get resolved edits another Python file,
live:

```
$ python mcp_client.py --modify
[modify] captured step #1 (get_error_rate) -> rewrote runbook replay_calls.py
[modify] captured step #2 (rollback) -> rewrote runbook replay_calls.py
[modify] captured step #3 (scale) -> rewrote runbook replay_calls.py

$ python replay_calls.py     # re-run the captured incident response
replay get_error_rate({'service': 'checkout-api'}) -> 9.2
replay rollback({'service': 'checkout-api', 'version': 'v2.7.0'}) -> rolled back checkout-api to v2.7.0
replay scale({'service': 'checkout-api', 'replicas': 6}) -> scaled checkout-api to 6 replicas
```

It still forwards every message verbatim (it code-gens as a *side effect*; it
does not block or alter the in-flight call). The output path is a fixed filename
and arguments are written as Python **literals** (via `repr` of JSON-parsed
values), so intercepted data can't redirect the write or inject code.

### 3) ⚠️ Tamper interceptor — `interceptor_tamper.py` (what a *malicious* proxy could do)

The honest interceptors above always forward the original bytes. But being in the
middle means you *could* change them. This one hijacks the `rollback` call and
silently rewrites the version **before the server sees it** — the client asked for
`v2.7.0`, the server actually runs `v0.0.1`:

```
$ python mcp_client.py --tamper
[tamper] hijacked rollback: version 'v2.7.0' -> 'v0.0.1' (client never asked for this)
...
[client] call rollback({'service': 'checkout-api', 'version': 'v2.7.0'}) -> rolled back checkout-api to v0.0.1
                                                     ▲ client requested this        ▲ server actually did this
```

Neither the client nor the server can tell — which is exactly the point. A proxy
in the middle can **modify, redirect, drop, inject, or forge** any message (it
could rewrite the *response* too, to fully hide the swap). That's why MCP guidance
calls for **integrity/authenticity** (TLS/mTLS + integrity checks on remote
transports), treating all wire data as untrusted, and gating high-impact actions
with **server-side authorization + human-in-the-loop** rather than trusting client
intent. This file is a security demo only — don't use it as a template.

### 4) Direct — baseline, no interceptor

`python mcp_client.py --direct` wires the client straight to the server so you
can confirm the interceptors are transparent (identical results, nothing logged).

## Tap any other MCP stdio server

Both interceptors accept a target command, so you can put them in front of a
different server and inspect *its* traffic:

```bash
python interceptor.py         <server-command> <args...>
python interceptor_modify.py  <server-command> <args...>
```

## Files

| File | What |
|---|---|
| `interceptor.py` | **the star:** transparent stdio proxy that **audits** client↔server traffic |
| `interceptor_modify.py` | active proxy that turns intercepted calls into a **runbook** (`replay_calls.py`) |
| `interceptor_tamper.py` | ⚠️ malicious-proxy **security demo**: rewrites a `rollback` call in flight |
| `mcp_client.py` | the AI on-call agent; picks a mode via a flag (`--modify` / `--tamper` / `--direct`) |
| `mcp_server.py` | MCP server (stdio); incident-ops tools: `get_error_rate`, `rollback`, `scale` |
| `replay_calls.py` | auto-generated runbook (git-ignored) |
| `intercept.log` | auto-generated audit trail (git-ignored) |
| `tests/` | end-to-end pytest coverage for the tools and both interceptors |
| `requirements.txt` | `mcp>=1.28.1` (official Python SDK) |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

CI (GitHub Actions) runs the suite on Python 3.11–3.13 for every push and PR.

## Security notes (MCP guidelines applied)

- **stdio transport** everywhere — pipe-based, no network listener, so no
  DNS-rebinding / CORS / CSRF surface (recommended for local MCP).
- **Single-purpose tools** with explicit **input validation** (version format,
  replica bounds); no "do anything" tool; least privilege. The remediation
  actions are **simulated** — no real infrastructure is touched.
- The honest interceptors are **local audit / codegen** aids: they log or write
  to a local file with a fixed path and treat wire data as literals (never as code
  or as a path). In a real deployment, redact sensitive fields before logging and
  restrict access to `intercept.log` / generated files, per the logging guidelines.
- `interceptor_tamper.py` is an intentional **attacker demo** showing why a
  middlebox must not be trusted for integrity: on remote transports use TLS/mTLS +
  integrity checks, and enforce high-impact actions with server-side authorization
  and human-in-the-loop — never on client intent alone.
