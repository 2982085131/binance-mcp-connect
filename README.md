# binance-mcp-connect

**English** | [简体中文](README.zh-CN.md)

Connect to **Binance's Agentic MCP server** (`https://agent.binance.com/mcp/agentic`)
by reusing the OAuth token that the official **Codex CLI** already obtained.

This is a working, reproducible implementation of a route that took several
failed attempts to find. It exists because Binance's manual OAuth endpoints are
protected by a WAF that rejects self-registered clients.

> **Not affiliated with Binance.** Use at your own risk. See [Security](docs/SECURITY.md).

---

## Why this exists

Binance exposes an **Agentic MCP server** with 50 tools for USD-M futures, COIN-M
futures, margin and convert. It uses OAuth 2.1 with PKCE — there is no API-key
path. The official documentation only shows official clients (Codex CLI, Claude
Code, ChatGPT, VS Code).

If you try to implement the OAuth flow yourself, you hit:

| Attempt | Request | Result |
|---|---|---|
| A. Pre-registered client | `client_id=codex` + localhost callback, `authorization_endpoint=/agentic-oauth/authorize` | **HTTP 400 Bad Request** |
| B. Same, corrected path | `/oauth-agentic/authorize` + localhost callback | **HTTP 403 Forbidden** (WAF: "illegal request payload") |
| C. Self-registered CIMD client | public `client.json` via cloudflared + PKCE, desktop **and** phone | **HTTP 403 Forbidden** (both networks) |
| D. **Official Codex CLI** | `codex mcp add ... --oauth-client-id codex` | ✅ **OAuth succeeds** |

The conclusion: the WAF allowlists the fingerprint/registration of official
clients. A client-id is not enough — the whole flow must come from a client the
server recognises.

Codex stores the resulting token **encrypted** in
`~/.codex/secrets/mcp_oauth.age` (age format, passphrase in the OS keyring).
This project decrypts that file locally and fills the gap: **a small, scriptable
MCP client**.

---

## What you get

- OAuth discovery (`/.well-known/oauth-protected-resource/gateway-mcp`).
- A reference CIMD OAuth implementation (kept for research; blocked by the WAF today).
- **Codex credential extraction**: Windows Credential Manager / `keyring` → age passphrase →
  decrypt `mcp_oauth.age` → bearer token.
- A **streamable-HTTP MCP client**: `initialize`, `tools/list`, `tools/call`
  with `Mcp-Session-Id` handling, JSON or SSE responses.
- Hedge-mode order validation (`positionSide`, no `reduceOnly`, minimum notional).
- A CLI: `binance-mcp token | status | tools | call | login`.
- Examples and unit tests.
- Bilingual docs with every error we hit and how to fix it.

---

## How it works

```
┌────────────────┐        ┌──────────────────────────────┐
│ Codex CLI      │  OAuth │ accounts.binance.com         │
│ (official)     │───────▶│ /oauth-agentic/authorize     │
│                │◀───────│   callback → code → token    │
└───────┬────────┘        └──────────────────────────────┘
        │ stores encrypted
        ▼
~/.codex/secrets/mcp_oauth.age   ← age(passphrase), passphrase in OS keyring
        │
        │  pyrage decrypt + keyring read
        ▼
  access_token  ──────────────▶  https://agent.binance.com/mcp/agentic
                                   POST JSON-RPC (Bearer)
```

1. Codex performs the official OAuth flow once.
2. The token is encrypted with `age` (scrypt passphrase mode) and stored under `$CODEX_HOME/secrets/`.
3. The passphrase is in the OS keyring: service `codex`, account
   `secrets|<sha256(canonical CODEX_HOME)[:16]>`.
4. `binance-mcp-connect` reads the passphrase, decrypts the file, extracts
   `access_token`, and talks JSON-RPC to the MCP endpoint.

---

## Quick start

### 1. Prerequisites

- Python 3.10+
- The official Codex CLI, connected to Binance **once**:

```bash
npm install -g @openai/codex
codex mcp add binance --url https://agent.binance.com/mcp/agentic --oauth-client-id codex
```

This opens the official authorization page. Finish it in a browser on the same
machine (the callback is `http://127.0.0.1:<port>/callback/...`).

> If the browser cannot reach the callback, copy the full callback URL from the
> address bar and paste it into the terminal when Codex asks for it.

### 2. Install

```bash
pip install -e .
# optional, for non-Windows keyring access:
pip install -e ".[keyring]"
```

### 3. Extract the token

```bash
binance-mcp token --out token.json
```

Example output (token masked):

```json
{
  "access_token": "eyJhbG...9fQ",
  "expires_at": "2026-11-22T17:00:08+00:00",
  "server_name": "binance",
  "client_id": "codex",
  "account": "secrets|8daa9cf8d6535db3"
}
```

`token.json` is a **trading credential** — keep it private (`chmod 600`), never commit it.

### 4. Use it

```bash
binance-mcp status
binance-mcp tools
binance-mcp call futures_usds.symbolPriceTicker --args '{"symbol":"ETHUSDT"}'
```

---

## CLI

| Command | Description |
|---|---|
| `binance-mcp token [--out token.json]` | Extract the Codex token (masked output) |
| `binance-mcp status` | Server info, wallet, positions, ETHUSDT price |
| `binance-mcp tools [--json]` | List all 50 MCP tools |
| `binance-mcp call NAME --args JSON` | Call any tool |
| `binance-mcp login` | Print official-client login instructions |
| `--token-file PATH` | Use a saved token instead of reading Codex |

---

## Python API

```python
from binance_mcp_connect import BinanceMCPClient, get_codex_token

token = get_codex_token()                      # decrypt Codex credentials
client = BinanceMCPClient(token["access_token"])
client.initialize()                            # captures Mcp-Session-Id

print(client.price("ETHUSDT"))
print(client.balance())
print(client.positions("ETHUSDT"))
tools = client.list_tools()
result = client.call("futures_usds.symbolPriceTicker", {"symbol": "ETHUSDT"})
```

---

## Trading with the MCP tools

The important tools:

| Tool | Use |
|---|---|
| `futures_usds.symbolPriceTicker` | last price |
| `futures_usds.klineCandlestickData` | klines (1m minimum) |
| `futures_usds.accountInformationV3` | wallet / available balance |
| `futures_usds.positionInformationV2` | positions |
| `futures_usds.currentAllOpenOrders` | open orders |
| `futures_usds.newOrder` | place order |
| `futures_usds.cancelOrder` | cancel order |
| `futures_usds.queryOrder` | order status |
| `futures_usds.changeInitialLeverage` | set leverage |

### Rules that will bite you

The account we tested is in **hedge mode**, with a **20 USDT minimum notional**:

| Rule | Wrong | Right |
|---|---|---|
| Position side | `positionSide: "BOTH"` → `-4061` | `LONG` / `SHORT` |
| Closing | `reduceOnly: true` → `-1106` | opposite side + same `positionSide` |
| Minimum notional | 0.005 ETH (~12 USDT) → `-4164` | ≥ 20 USDT (0.009 ETH at 2,400) |
| Post-only | `timeInForce: "GTC"` | `"GTX"` (rejected with `-5022` if it would cross) |
| Quantity step | 0.0095 → rejected | 0.001 step |
| Price tick | 2400.123 → rejected | 0.01 tick |

Always validate before sending:

```python
from binance_mcp_connect import Order, validate

order = Order(symbol="ETHUSDT", side="BUY", position_side="LONG",
              order_type="LIMIT", quantity=0.009, price=2388.0, time_in_force="GTX")
validate(order)              # raises OrderValidationError with a clear message
client.call("futures_usds.newOrder", order.params())
```

---

## Security and legal

- The token grants **trading** rights on the **Agentic sub-account** (no withdrawal).
- Direct MCP calls **bypass the client's per-trade confirmation UI** — build your own
  confirmation and risk limits.
- Store tokens outside the repo, rotate them, and revoke the agent connection if leaked.
- This project is for research/education. It is not affiliated with Binance. Trading
  derivatives is risky; you can lose everything. No warranty.

Read [docs/SECURITY.md](docs/SECURITY.md) before using it with real money.

---

## Project layout

```
binance-mcp-connect/
├── binance_mcp_connect/
│   ├── client.py        # streamable-HTTP MCP client
│   ├── codex_creds.py   # keyring + age decryption + token extraction
│   ├── metadata.py      # OAuth discovery
│   ├── cimd.py          # self-registered client flow (reference, WAF-blocked)
│   ├── safety.py        # order validation
│   └── cli.py           # binance-mcp command
├── examples/            # price, list_tools, safe_order
├── tests/               # parser + validation tests
├── docs/                # troubleshooting, architecture, security
└── pyproject.toml
```

---

## Documentation

- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — every error we hit, with fixes.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — OAuth discovery, CIMD, Codex credentials, MCP transport.
- [docs/SECURITY.md](docs/SECURITY.md) — threat model and safe usage.

## Tested environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| Python | 3.13 |
| Codex CLI | 0.164.0 |
| MCP server | `Binance-MCP-Server 2.1.0` (50 tools) |
| Account | Agentic sub-account, hedge mode, 20 USDT minimum notional |

`pytest` covers parsing, keyring account derivation and order validation; the
OAuth/credential path is exercised by `binance-mcp token`.

## License

MIT — see [LICENSE](LICENSE).
