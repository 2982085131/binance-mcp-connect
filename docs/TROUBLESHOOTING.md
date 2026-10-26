# Troubleshooting

Every error below was observed while building this project (October 2026).
Chinese quick-reference first, details after.

## 中文速查

| 现象 | 原因 | 修法 |
|---|---|---|
| `HTTP 451` | 地区封锁 / 出口 IP 被限制 | 换网络或使用可访问 Binance 的机器 |
| OAuth 页 `400 Bad Request` | 授权端点路径或 `redirect_uri` 不匹配 | 用官方客户端，不要手拼 |
| OAuth 页 `403 Forbidden`（WAF） | 自注册/仿冒客户端被风控 | 改用官方 Codex CLI 授权 |
| 手机也 403 | 不是 IP 问题，是客户端指纹 | 同上 |
| MCP `401` | token 过期/无效 | 重新用 Codex 授权并重新提取 |
| `mcp_oauth.age not found` | Codex 没连过 Binance | `codex mcp add ...` 完成一次授权 |
| 读不到钥匙串口令 | account 哈希不对（`\\?\` 前缀） | 用规范化路径；本项目会两个都试 |
| `-4061` | Hedge 模式必须 LONG/SHORT | 不要用 `BOTH` |
| `-1106` | Hedge 模式禁止 `reduceOnly` | 反向单 + 相同 `positionSide` |
| `-4164` | 名义额 < 20 USDT | 加数量（0.009 ETH 起） |
| `-5022` | post-only 单会吃单 | 挂单价离盘口更远，或改 GTC |
| `-1021` | 时间戳超出 recvWindow | 同步系统时钟 |
| `-1003` | 请求过快 | 降低频率/退避 |
| `Get-Content -Wait \| codex ...` 卡住 | 管道永不结束 | 不要用这种方式喂输入 |

---

## OAuth / authorization

### `HTTP 451` (geo-block)

Binance blocks some regions at the edge. A request that worked an hour ago can
return 451 later (the block is IP/route dependent). Test:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://fapi.binance.com/fapi/v1/ping
```

### `400 Bad Request` on `/agentic-oauth/authorize`

Observed with `client_id=codex` and a custom `redirect_uri`. Causes:

- the authorization endpoint path from the metadata (`/agentic-oauth/authorize`)
  versus the one that actually serves the flow (`/oauth-agentic/authorize`);
- `redirect_uri` not matching the registered client byte-for-byte
  (`localhost` vs `127.0.0.1` counts as different).

Manual flows cannot resolve this without the client's registered parameters.

### `403 Forbidden` from the WAF

Message: *"For security reasons you can't connect to the server for this app or
website at this time... illegal request payload is identified as an attack."*

Observed for:

- `client_id=codex` with our own callback;
- a self-registered **CIMD** client, even with a public metadata document;
- the same CIMD link opened on a **phone on a different network**.

Conclusion: the block is tied to the client fingerprint/registration, not the IP.
Repeated retries can escalate to a longer block — **stop retrying**.

### `invalid_client` (401) vs `invalid_grant` (400) on the token endpoint

`client_id=codex` returned `400` for a dummy code (client accepted, grant
invalid), while unknown client ids returned `401`. This is useful for diagnosing
which client ids are registered, but it does not help bypass the authorize WAF.

### CIMD (`client_id_metadata_document_supported: true`)

The server advertises CIMD support, but the authorize page still rejects
self-registered clients. The reference implementation in `cimd.py` is kept for
future retries; it needs a public HTTPS origin serving `/client.json`
(e.g. `cloudflared tunnel --url http://127.0.0.1:8080`).

---

## Token / credentials

### MCP returns `401` after working before

The access token expires (about 30 days). Re-run the Codex OAuth flow and
extract again:

```bash
codex mcp login binance
binance-mcp token --out token.json
```

### `mcp_oauth.age not found`

Codex has never connected to Binance on this machine. Run:

```bash
codex mcp add binance --url https://agent.binance.com/mcp/agentic --oauth-client-id codex
```

### `could not read the Codex keyring passphrase`

The keyring account is derived from the **canonical** `CODEX_HOME`:

- Windows: Rust's `fs::canonicalize` returns a verbatim path (`\\?\C:\...`),
  so the hash is over that string, not the plain path;
- a different `CODEX_HOME` (e.g. a custom env var) produces a different account.

This project tries both the verbatim and the plain path. On Windows it reads
`secrets|<hash>.codex` from Credential Manager via `ctypes`; elsewhere it uses
the `keyring` package (`pip install -e ".[keyring]"`).

### `pyrage is required`

```bash
pip install pyrage
```

### `age decrypt failed`

The passphrase read from the keyring does not match the file. Usually means the
keyring entry was rotated (Codex re-login) or `CODEX_HOME` points elsewhere.

### `no access_token found in the decrypted secrets file`

The decrypted JSON is `{"version":1,"secrets":{"global/MCP_OAUTH_<hash>":"<inner>"}}`.
The inner JSON must contain `token_response.access_token`. If the shape changed,
inspect (do **not** paste it anywhere) and adapt `extract_token`.

---

## MCP transport

### `GET /mcp/agentic` returns 404

Normal. The endpoint only accepts JSON-RPC **POST**; unauthenticated POST returns
401 with a `WWW-Authenticate` header pointing at the resource metadata.

### Response is SSE, not JSON

The server may answer with `event: message\ndata: {...}`. `parse_body()` accepts
both formats. If you write your own client, read `data:` lines.

### `Mcp-Session-Id`

`initialize` returns a session id header; include it on every later request.
Without it, `tools/list` / `tools/call` may fail.

### `tools/call` returns `isError: true`

The Binance error is inside `content[0].text` or `structuredContent`; raise and
print it. Example: `-4164` min notional.

### A JSON-RPC `error` whose `message` is a JSON string

e.g. `{"code": -32603, "message": "{\"code\":-4061,\"msg\":\"...\"}"}`.
Parse the message as JSON to surface the Binance code.

---

## Trading errors

| Code | Meaning | Fix |
|---|---|---|
| `-4061` | position side does not match user's setting | use `LONG` / `SHORT` (hedge mode) |
| `-1106` | parameter `reduceonly` sent when not required | remove it in hedge mode |
| `-4164` | order notional too small | ≥ 20 USDT on the tested account |
| `-5022` | post-only order would take liquidity | move the limit away from the touch |
| `-2015` | invalid API key, IP or permissions | wrong environment (testnet key on mainnet, IP whitelist) |
| `-2014` | API-key format invalid | dummy/test key; signature path is fine but key is not |
| `-1021` | timestamp outside recvWindow | sync the clock; the test machine was **2.4 s** behind |
| `-1003` | too many requests | back off, reduce concurrency |
| `-4131` | PERCENT_PRICE filter | price too far from mark |

Clock skew matters: the machine used here was ~2.4 s behind Binance server time.
Use `/fapi/v1/time` and pass the offset, or ccxt's `adjustForTimeDifference`.

---

## Environment

### `Get-Content -Wait | codex mcp login ...` hangs forever

`Get-Content -Wait` never ends, so the pipeline never closes. Do not use it to
feed the callback URL. Run Codex interactively, or let it open the browser.

### The browser cannot reach `127.0.0.1:<port>/callback`

The callback is bound to the machine running Codex. If you authorize on another
device, copy the full callback URL from the address bar and paste it when Codex
asks.

### WAF blocks even the official callback

Wait (the block is temporary), and do not hammer the authorize endpoint. If it
persists, use a network/region that Binance normally serves.

---

## Data precision (for strategy work)

- MCP klines expose **1 minute** as the finest interval (1m/3m/5m/15m/30m/1h…1M).
- Binance **spot** REST supports **1s** klines; USD-M futures REST does not.
- Binance Vision publishes **tick trades** (`futures/um/daily/trades/...`) for the
  highest precision, but they are large.
- Order-book history is not public; only the real-time WebSocket.
