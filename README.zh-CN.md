# binance-mcp-connect

[English](README.md) | **简体中文**

通过复用官方 **Codex CLI** 已经拿到的 OAuth token，连接 **Binance Agentic MCP 服务器**
（`https://agent.binance.com/mcp/agentic`）。

这是一个踩了很多坑才跑通的方案的可复现实现。之所以需要它，是因为 Binance 的
手动 OAuth 端点有 WAF 保护，会拒绝自注册客户端。

> **与 Binance 无关联。** 风险自负，详见 [安全说明](docs/SECURITY.md)。

---

## 为什么需要这个项目

Binance 的 **Agentic MCP 服务器**提供 50 个工具，覆盖 USDⓈ-M 合约、币本位合约、
杠杆和闪兑。它使用 OAuth 2.1 + PKCE，**没有 API key 通道**。官方文档只演示了
官方客户端（Codex CLI、Claude Code、ChatGPT、VS Code）。

如果你自己实现 OAuth，会遇到：

| 尝试 | 请求 | 结果 |
|---|---|---|
| A. 预注册 client | `client_id=codex` + 本地回调，`/agentic-oauth/authorize` | **HTTP 400 Bad Request** |
| B. 修正路径 | `/oauth-agentic/authorize` + 本地回调 | **HTTP 403 Forbidden**（WAF：非法请求载荷） |
| C. 自注册 CIMD 客户端 | 公网 `client.json` + cloudflared + PKCE，电脑和手机都试 | **HTTP 403 Forbidden**（两个网络都拦） |
| D. **官方 Codex CLI** | `codex mcp add ... --oauth-client-id codex` | ✅ **OAuth 成功** |

结论：WAF 放行的是**官方客户端的指纹/注册信息**，光有 client_id 不够，整个流程
必须来自服务器认识的客户端。

Codex 会把 token **加密**存在 `~/.codex/secrets/mcp_oauth.age`（age 格式，口令在
系统钥匙串里）。本项目在本地解密，补上最后一块：**一个可脚本化的 MCP 客户端**。

---

## 它提供了什么

- OAuth 元数据发现（`/.well-known/oauth-protected-resource/gateway-mcp`）；
- CIMD 自注册 OAuth 的参考实现（保留研究用，目前被 WAF 拦）；
- **Codex 凭据提取**：Windows 凭据管理器 / `keyring` → age 口令 → 解密 → Bearer token；
- **streamable HTTP MCP 客户端**：`initialize`、`tools/list`、`tools/call`，处理
  `Mcp-Session-Id`，兼容 JSON 和 SSE 响应；
- Hedge 模式下单校验（`positionSide`、禁止 `reduceOnly`、最小名义额）；
- CLI：`binance-mcp token | status | tools | call | login`；
- 示例、单元测试、中英双语文档，包含我们踩过的全部错误与修法。

---

## 工作原理

```
┌────────────────┐        ┌──────────────────────────────┐
│ Codex CLI      │  OAuth │ accounts.binance.com         │
│ （官方客户端）  │───────▶│ /oauth-agentic/authorize     │
│                │◀───────│   回调 → code → token        │
└───────┬────────┘        └──────────────────────────────┘
        │ 加密存储
        ▼
~/.codex/secrets/mcp_oauth.age   ← age(口令)，口令在系统钥匙串
        │
        │  pyrage 解密 + 读取钥匙串
        ▼
  access_token  ──────────────▶  https://agent.binance.com/mcp/agentic
                                    POST JSON-RPC（Bearer）
```

1. 用 Codex 完成一次官方 OAuth；
2. token 用 `age`（scrypt 口令模式）加密，存在 `$CODEX_HOME/secrets/`；
3. 口令在系统钥匙串：service `codex`，account `secrets|<sha256(规范化 CODEX_HOME)[:16]>`；
4. 本项目读出`口令`、解密文件、取 `access_token`，直接对 MCP 端点发 JSON-RPC。

---

## 快速开始

### 1. 前置条件

- Python 3.10+
- 官方 Codex CLI，并且**成功连接过 Binance**：

```bash
npm install -g @openai/codex
codex mcp add binance --url https://agent.binance.com/mcp/agentic --oauth-client-id codex
```

这会打开官方授权页。请在同一台机器的浏览器里完成授权（回调是
`http://127.0.0.1:<端口>/callback/...`）。

> 如果浏览器打不开回调地址，把地址栏里带 `code` 的完整 URL 复制下来，
> 在 Codex 提示时粘贴进去。

### 2. 安装

```bash
pip install -e .
# 非 Windows 如需 keyring：
pip install -e ".[keyring]"
```

### 3. 提取 token

```bash
binance-mcp token --out token.json
```

输出示例（token 已打码）：

```json
{
  "access_token": "eyJhbG...9fQ",
  "expires_at": "2026-11-22T17:00:08+00:00",
  "server_name": "binance",
  "client_id": "codex",
  "account": "secrets|8daa9cf8d6535db3"
}
```

`token.json` 是**交易凭据**，请设为仅本人可读（`chmod 600`），不要提交到仓库。

### 4. 使用

```bash
binance-mcp status
binance-mcp tools
binance-mcp call futures_usds.symbolPriceTicker --args '{"symbol":"ETHUSDT"}'
```

---

## CLI 说明

| 命令 | 作用 |
|---|---|
| `binance-mcp token [--out token.json]` | 提取 Codex token（打码显示） |
| `binance-mcp status` | 服务器信息、钱包、持仓、ETHUSDT 价格 |
| `binance-mcp tools [--json]` | 列出 50 个工具 |
| `binance-mcp call NAME --args JSON` | 调用任意工具 |
| `binance-mcp login` | 打印官方客户端登录指引 |
| `--token-file PATH` | 使用已保存的 token，而不是读 Codex |

---

## Python API

```python
from binance_mcp_connect import BinanceMCPClient, get_codex_token

token = get_codex_token()                      # 解密 Codex 凭据
client = BinanceMCPClient(token["access_token"])
client.initialize()                            # 获取 Mcp-Session-Id

print(client.price("ETHUSDT"))
print(client.balance())
print(client.positions("ETHUSDT"))
tools = client.list_tools()
result = client.call("futures_usds.symbolPriceTicker", {"symbol": "ETHUSDT"})
```

---

## 用 MCP 下单

常用工具：

| 工具 | 用途 |
|---|---|
| `futures_usds.symbolPriceTicker` | 最新价 |
| `futures_usds.klineCandlestickData` | K 线（最小 1m） |
| `futures_usds.accountInformationV3` | 钱包/可用余额 |
| `futures_usds.positionInformationV2` | 持仓 |
| `futures_usds.currentAllOpenOrders` | 挂单 |
| `futures_usds.newOrder` | 下单 |
| `futures_usds.cancelOrder` | 撤单 |
| `futures_usds.queryOrder` | 查单 |
| `futures_usds.changeInitialLeverage` | 改杠杆 |

### 会咬人的规则

我们测试的账户是 **Hedge 模式**，**最小名义额 20 USDT**：

| 规则 | 错误写法 | 正确写法 |
|---|---|---|
| 持仓方向 | `positionSide: "BOTH"` → `-4061` | `LONG` / `SHORT` |
| 平仓 | `reduceOnly: true` → `-1106` | 反向单 + 相同 `positionSide` |
| 最小名义额 | 0.005 ETH（约 12 USDT）→ `-4164` | ≥ 20 USDT（0.009 ETH） |
| Post-only | `timeInForce: "GTC"` | `"GTX"`（会吃单则 `-5022`） |
| 数量步长 | 0.0095 → 拒单 | 0.001 |
| 价格步长 | 2400.123 → 拒单 | 0.01 |

下单前先校验：

```python
from binance_mcp_connect import Order, validate

order = Order(symbol="ETHUSDT", side="BUY", position_side="LONG",
              order_type="LIMIT", quantity=0.009, price=2388.0, time_in_force="GTX")
validate(order)              # 不合法会抛 OrderValidationError，信息明确
client.call("futures_usds.newOrder", order.params())
```

---

## 安全与合规

- token 拥有 **Agentic 子账户**的**交易**权限（无提现权限）；
- 直接调 MCP 会**绕过客户端的每笔确认 UI**，必须自己做确认与风控；
- token 不要放在仓库里，定期轮换；泄露后在 Binance 断开 agent 连接；
- 本项目仅用于研究与学习，与 Binance 无关联；合约交易风险极高，可能损失全部本金；
  不提供任何担保。

用真钱之前请先读 [docs/SECURITY.md](docs/SECURITY.md)。

---

## 项目结构

```
binance-mcp-connect/
├── binance_mcp_connect/
│   ├── client.py        # streamable-HTTP MCP 客户端
│   ├── codex_creds.py   # keyring + age 解密 + token 提取
│   ├── metadata.py      # OAuth 发现
│   ├── cimd.py          # 自注册客户端流程（参考，被 WAF 拦）
│   ├── safety.py        # 下单校验
│   └── cli.py           # binance-mcp 命令
├── examples/            # price / list_tools / safe_order
├── tests/               # 解析与校验测试
├── docs/                # 排错、架构、安全
└── pyproject.toml
```

---

## 文档

- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — 所有踩过的错误与修法
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — OAuth 发现、CIMD、Codex 凭据、MCP 传输
- [docs/SECURITY.md](docs/SECURITY.md) — 威胁模型与安全用法

## 已验证环境

| 项目 | 值 |
|---|---|
| 操作系统 | Windows 11 |
| Python | 3.13 |
| Codex CLI | 0.164.0 |
| MCP 服务器 | `Binance-MCP-Server 2.1.0`（50 个工具） |
| 账户 | Agentic 子账户，Hedge 模式，最小名义额 20 USDT |

`pytest` 覆盖解析、钥匙串 account 推导和下单校验；OAuth/凭据链路由
`binance-mcp token` 实际验证。

## 许可证

MIT，见 [LICENSE](LICENSE)。
