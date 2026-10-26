# Contributing

Thanks for looking at this project. It is deliberately small and focused.

## Scope

In scope:

- keeping the MCP client working when Binance changes the transport;
- additional credential backends (macOS Keychain, Linux Secret Service) — the
  `keyring` package path is already supported, but tested only on Windows;
- new validation rules for other symbols (quantity/price steps differ);
- docs: more failure modes, especially OAuth/WAF changes.

Out of scope:

- trading strategies or signal generation (this is plumbing);
- anything that bypasses Binance's confirmation/security controls;
- storing tokens in the repository.

## Development

```bash
pip install -e ".[dev,keyring]"
python -m pytest -q
```

No network is required for the tests; they cover parsing, keyring account
derivation and order validation.

## Pull requests

1. Keep changes focused; one topic per PR.
2. Add a test for a new parsing/validation rule.
3. Update `docs/TROUBLESHOOTING.md` if you hit a new error.
4. Never include real tokens, `mcp_oauth.age`, screenshots of credentials, or
   account identifiers.

## Security issues

Please do not open a public issue for a leaked credential or a Binance-side
vulnerability. Report it to Binance security first, and describe only the
client-side integration problem here.

## 中文

- 本项目只负责“连接与下单管道”，不包含交易策略；
- 提交前请确保没有把 `token.json`、`mcp_oauth.age`、账号信息带进仓库；
- 新增错误处理时，请同步更新 `docs/TROUBLESHOOTING.md`。
