# Changelog

## 0.1.1 — 2026-10-26

Fixes from an external code review (9 findings + 1 compatibility item):

- **P1** token extraction now selects the credential bound to Binance
  (`server_name`/URL), and refuses missing or ambiguous matches instead of
  returning the first token in the file.
- Quantity rounding uses `Decimal` floor, so `0.043` stays `0.043`.
- `examples/safe_order.py` always attempts `cancelOrder` (try/finally) and
  reports orphan orders when cancelling fails.
- SSE parser joins multi-line `data:` fields per event; `_rpc` validates the
  response id and the presence of `result`/`error`; empty responses raise.
- CLI `tools --json` and `call` print complete JSON (no truncation).
- `tools` no longer crashes when a tool has no description.
- `tools/list` follows `nextCursor` pagination with a loop guard.
- CIMD uses one `redirect_uri` for metadata, authorization and token exchange,
  preserves HTTPS, and releases both HTTP servers in `finally`.
- MCP initialization is tracked by a flag, not by the optional session id.
- `token --out` sets `0600` where the OS supports it.

Test suite: 23 tests (13 new regression tests for the review findings).

## 0.1.0 — 2026-10-26

Initial release.

- OAuth discovery for Binance Agentic MCP (`/gateway-mcp` metadata).
- CIMD reference flow (`cimd.py`) — protocol-correct, currently blocked by the
  Binance WAF (HTTP 403) for self-registered clients.
- Codex credential extraction: keyring passphrase → age decryption → token.
- Streamable-HTTP MCP client: initialize, session id, tools/list, tools/call,
  JSON and SSE responses.
- Hedge-mode order validation: position side, no `reduceOnly`, 20 USDT minimum
  notional, quantity/price steps.
- CLI: `token`, `status`, `tools`, `call`, `login`.
- Examples and 10 unit tests.
- Bilingual README (EN / zh-CN), troubleshooting, architecture and security docs.

### Verified environment

- Windows 11, Python 3.13, Codex CLI 0.164.0.
- Binance MCP server `Binance-MCP-Server 2.1.0` (50 tools).
- Account: Agentic sub-account, hedge mode, 20 USDT minimum notional.
