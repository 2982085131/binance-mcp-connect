"""Command line interface: binance-mcp {token,status,tools,call,login}."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .client import BinanceMCPAuthError, BinanceMCPClient, BinanceMCPError
from .codex_creds import get_codex_token, get_codex_token_from_file


def _load_token(args) -> dict:
    if getattr(args, "token_file", None):
        return get_codex_token_from_file(args.token_file)
    return get_codex_token()


def _client(args) -> tuple[BinanceMCPClient, dict]:
    token = _load_token(args)
    client = BinanceMCPClient(token["access_token"])
    return client, token


def _mask(token: str) -> str:
    return token[:6] + "..." + token[-4:] if len(token) > 12 else "***"


def cmd_token(args) -> int:
    info = _load_token(args)
    expires = info.get("expires_at")
    if expires:
        try:
            expires = datetime.fromtimestamp(expires / 1000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    out = {
        "access_token": info["access_token"],
        "expires_at": expires,
        "server_name": info.get("server_name"),
        "client_id": info.get("client_id"),
        "account": info.get("account"),
    }
    if args.out:
        from pathlib import Path

        Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"saved to {args.out} (keep it private, chmod 600)")
    print(json.dumps({**out, "access_token": _mask(out["access_token"])}, indent=2))
    return 0


def cmd_status(args) -> int:
    client, token = _client(args)
    info = client.initialize()
    print(f"server   : {info.get('name')} {info.get('version')}")
    acc = client.balance()
    print(f"wallet   : {acc.get('totalWalletBalance')} USDT")
    print(f"available: {acc.get('availableBalance')} USDT")
    positions = client.positions()
    if not positions:
        print("positions: flat")
    for p in positions:
        print(f"position : {p.get('positionSide')} {p.get('positionAmt')} @ {p.get('entryPrice')} "
              f"uPnL={p.get('unRealizedProfit')}")
    try:
        print(f"ETHUSDT  : {client.price('ETHUSDT'):.2f}")
    except Exception as exc:  # noqa: BLE001
        print(f"price    : unavailable ({exc})")
    return 0


def cmd_tools(args) -> int:
    client, _ = _client(args)
    tools = client.list_tools()
    if args.json:
        print(json.dumps(tools, indent=2)[:8000])
        return 0
    for t in tools:
        desc = (t.get("description") or "").splitlines()[0][:90]
        print(f"{t.get('name'):55s} {desc}")
    print(f"\n{len(tools)} tools")
    return 0


def cmd_call(args) -> int:
    client, _ = _client(args)
    try:
        args_json = json.loads(args.args)
    except json.JSONDecodeError as exc:
        print(f"invalid --args JSON: {exc}", file=sys.stderr)
        return 2
    result = client.call(args.name, args_json)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:6000])
    return 0


def cmd_login(args) -> int:
    print(
        "Binance Agentic MCP uses OAuth; self-registered clients are currently blocked\n"
        "by a WAF (HTTP 403). Connect once with an official MCP client, then reuse its\n"
        "token with `binance-mcp token`.\n\n"
        "Codex CLI:\n"
        "  npm i -g @openai/codex\n"
        "  codex mcp add binance --url https://agent.binance.com/mcp/agentic "
        "--oauth-client-id codex\n\n"
        "Claude Code:\n"
        "  claude mcp add binance-mcp-server --transport http "
        "https://agent.binance.com/mcp/agentic\n\n"
        "After authorizing, run:\n"
        "  binance-mcp token\n"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="binance-mcp",
                                description="Connect to Binance Agentic MCP via a reused OAuth token")
    p.add_argument("--token-file", help="JSON file with access_token (overrides Codex lookup)")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("token", help="extract the access token from Codex and optionally save it")
    t.add_argument("--out", help="write token JSON to this path")
    t.set_defaults(func=cmd_token)

    s = sub.add_parser("status", help="account, positions and price")
    s.set_defaults(func=cmd_status)

    tl = sub.add_parser("tools", help="list MCP tools")
    tl.add_argument("--json", action="store_true")
    tl.set_defaults(func=cmd_tools)

    c = sub.add_parser("call", help="call one MCP tool")
    c.add_argument("name")
    c.add_argument("--args", default="{}")
    c.set_defaults(func=cmd_call)

    lg = sub.add_parser("login", help="print official-client login instructions")
    lg.set_defaults(func=cmd_login)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BinanceMCPAuthError as exc:
        print(f"auth error: {exc}", file=sys.stderr)
        return 3
    except (BinanceMCPError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
