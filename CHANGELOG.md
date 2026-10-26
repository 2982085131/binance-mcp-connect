# Changelog

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
