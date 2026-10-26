# Security

## What the token can do

The Bearer token is issued to the **Agentic sub-account** and grants:

- read market data and balances;
- read positions and orders;
- **place and cancel orders**, change leverage and margin;
- use margin and convert tools.

It does **not** grant withdrawals. It is still a trading credential: anyone with
the token can trade the sub-account's funds.

## Bypassing the confirmation UI

The official clients (Codex, Claude, ChatGPT, VS Code) ask the user to confirm
each trade/transfer. A direct JSON-RPC call skips that gate. If you build on this
project:

1. validate every order locally (symbol, side, position side, quantity, notional, price);
2. impose a maximum position size and a daily loss limit;
3. require an explicit human confirmation above a threshold;
4. provide a kill switch that cancels open orders and stops the loop.

`binance_mcp_connect.safety` implements the exchange-specific checks
(hedge mode, 20 USDT minimum notional, quantity/price steps).

## Token handling

| Do | Don't |
|---|---|
| keep `token.json` outside the repo, `chmod 600` | commit it, paste it in issues/chat |
| rotate on a schedule | share the decrypted `mcp_oauth.age` |
| revoke by disconnecting the agent in Binance | run with a main-account token |
| use a dedicated sub-account with small funds | reuse the token across unrelated bots |

If a token leaks: disconnect the agent connection in Binance
(`Profile → Dashboard → Sub-account → Account Management → Disconnect agents`),
then re-authorize.

## Files this project reads

| File | Sensitivity |
|---|---|
| `$CODEX_HOME/secrets/mcp_oauth.age` | encrypted; useless without the keyring passphrase |
| OS keyring entry `codex` / `secrets\|<hash>` | the passphrase; protected by the OS user session |
| `token.json` (optional) | **plaintext trading token**; protect it |

The code never sends these files anywhere; it only performs local decryption and
then talks to `agent.binance.com`.

## Legal / ToS

- This project is not affiliated with, endorsed by, or supported by Binance.
- Automating the Agentic MCP server may be subject to Binance's Product Terms and
  AI Policy. Check them before production use.
- The WAF behaviour described here may change without notice; the manual OAuth
  path may become legal/available later, or stricter.
- Derivatives trading can lose more than expected; nothing here is financial advice.

## Responsible disclosure

If you find a security issue in Binance's MCP/OAuth implementation, report it to
Binance security rather than publishing exploit details. This project only
documents defensive workarounds for client-side integration.
