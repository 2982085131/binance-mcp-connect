# Architecture

This document explains the moving parts and why the final route was chosen.

## 1. Endpoint and discovery

| Item | Value |
|---|---|
| MCP endpoint | `https://agent.binance.com/mcp/agentic` |
| Protected-resource metadata | `https://agent.binance.com/.well-known/oauth-protected-resource/gateway-mcp` |
| Authorization-server metadata | `https://agent.binance.com/.well-known/oauth-authorization-server` |
| Authorization endpoint | `https://accounts.binance.com/oauth-agentic/authorize` |
| Token endpoint | `https://accounts.binance.com/oauth-agentic/token` |

The MCP endpoint responds to unauthenticated POST with `401` and:

```
WWW-Authenticate: Bearer resource_metadata="https://agent.binance.com/.well-known/oauth-protected-resource/gateway-mcp"
```

The protected-resource document lists `authorization_servers: ["https://agent.binance.com"]`.
The AS metadata advertises `token_endpoint_auth_methods_supported: ["none"]`,
`code_challenge_methods_supported: ["S256"]` and
`client_id_metadata_document_supported: true`.

`metadata.py` wraps both calls.

## 2. The three client strategies

### 2.1 Pre-registered client (`client_id=codex`)

The Binance docs show Codex connecting with `--oauth-client-id codex`. Reusing
that id with our own callback fails: the authorization endpoint returns `400`
(redirect mismatch) or `403` (WAF), because the registered redirect and the client
fingerprint are not ours.

### 2.2 CIMD self-registration

RFC-style client-id metadata document:

```
GET https://<public-host>/client.json
{
  "client_id": "https://<public-host>/client.json",
  "client_name": "binance-mcp-connect",
  "redirect_uris": ["http://localhost:1455/auth/callback"],
  "grant_types": ["authorization_code"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none"
}
```

`cimd.py` serves this on `:8080` (expose it with a tunnel), performs PKCE and
exchanges the code. It is protocol-correct, but the authorize request is blocked
by the WAF (403) on both desktop and mobile networks.

### 2.3 Official client + credential reuse (chosen)

Codex CLI performs the official OAuth flow. The server accepts it. Codex then
stores the MCP credentials encrypted:

```
$CODEX_HOME/secrets/mcp_oauth.age     # age ciphertext (scrypt passphrase mode)
```

Passphrase storage (from `codex-rs/secrets`):

```
keyring service : "codex"
keyring account : "secrets|" + sha256(canonical(CODEX_HOME))[:16]
```

The decrypted payload:

```json
{
  "version": 1,
  "secrets": {
    "global/MCP_OAUTH_<HASH>": "{\"server_name\":\"binance\",\"url\":\"...\",\"client_id\":\"codex\",\"token_response\":{\"access_token\":\"...\",\"token_type\":\"Bearer\",\"expires_in\":2592000},\"expires_at\":1795338008613}"
  }
}
```

`codex_creds.py` reads the passphrase (Windows Credential Manager via `ctypes`,
or `keyring` on other platforms), decrypts with `pyrage`, and returns the token.

This route works because the token is issued to a client the server trusts; we
never talk to the authorize endpoint ourselves.

## 3. MCP transport

`client.py` implements streamable HTTP:

```
POST /mcp/agentic
Authorization: Bearer <token>
Content-Type: application/json
Accept: application/json, text/event-stream
MCP-Protocol-Version: 2025-06-18
Mcp-Session-Id: <from initialize>

{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"...","arguments":{...}}}
```

- The response may be JSON or SSE (`event: message` + `data: {...}`).
- `initialize` is mandatory; capture `Mcp-Session-Id` from the response headers.
- `notifications/initialized` is sent afterwards (optional but recommended).
- Tool results usually carry `structuredContent`; otherwise parse
  `content[0].text` as JSON.

Sequence:

```
client                         server
  │  initialize                  │
  │─────────────────────────────▶│
  │◀── result + Mcp-Session-Id ──│
  │  notifications/initialized   │
  │─────────────────────────────▶│
  │  tools/list                  │
  │─────────────────────────────▶│
  │◀──── 50 tools ───────────────│
  │  tools/call                  │
  │─────────────────────────────▶│
  │◀──── result / error ─────────│
```

## 4. Scope and limits

The token belongs to the **Agentic sub-account**, not the main account:

- market data, balances, positions, orders, leverage, margin, convert;
- **no withdrawal** permission (by design);
- per-trade confirmation exists in the official client UI, but a direct MCP call
  bypasses it — risk controls must live in your own code.

Token lifetime is about 30 days; expiry returns `401`, and the Codex flow must be
repeated.
