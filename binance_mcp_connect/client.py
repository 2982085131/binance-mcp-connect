"""MCP JSON-RPC client for Binance's Agentic MCP endpoint.

Transport: streamable HTTP (POST JSON-RPC, response may be JSON or SSE).
Auth: Bearer access token obtained from the official Codex CLI (see codex_creds).
"""
from __future__ import annotations

import json
from typing import Any

import requests

DEFAULT_ENDPOINT = "https://agent.binance.com/mcp/agentic"
PROTOCOL_VERSION = "2025-06-18"
MAX_PAGES = 50


class BinanceMCPError(RuntimeError):
    """Raised when the MCP server returns a JSON-RPC error or an invalid response."""


class BinanceMCPAuthError(BinanceMCPError):
    """Raised on 401/403 from the MCP endpoint (expired or invalid token)."""


def parse_messages(text: str) -> list[dict]:
    """Parse a JSON body or an SSE stream into a list of JSON-RPC messages.

    SSE allows one event to span multiple ``data:`` lines; they must be joined
    with newlines before JSON parsing (WHATWG event-stream rules).
    """
    text = text.strip()
    if not text:
        return []
    if text.startswith("{"):
        return [json.loads(text)]
    messages: list[dict] = []
    data: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif line.strip() == "" and data:
            payload = "\n".join(data)
            data = []
            try:
                messages.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    if data:
        try:
            messages.append(json.loads("\n".join(data)))
        except json.JSONDecodeError:
            pass
    return messages


def parse_body(text: str) -> dict:
    """Backward-compatible single-message parser (returns the first message)."""
    messages = parse_messages(text)
    if not messages:
        raise BinanceMCPError("response contained no JSON-RPC message")
    return messages[0]


class BinanceMCPClient:
    def __init__(self, access_token: str, endpoint: str = DEFAULT_ENDPOINT, timeout: int = 30):
        if not access_token:
            raise ValueError("access_token is required")
        self.access_token = access_token
        self.endpoint = endpoint
        self.timeout = timeout
        self.session_id: str | None = None
        self.server_info: dict | None = None
        self._initialized = False
        self._next_id = 0

    # ------------------------------------------------------------------ transport
    def _post(self, payload: dict) -> str:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "User-Agent": "binance-mcp-connect/0.1",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        resp = requests.post(self.endpoint, data=json.dumps(payload), headers=headers,
                             timeout=self.timeout)
        if resp.status_code in (401, 403):
            raise BinanceMCPAuthError(
                f"HTTP {resp.status_code}: token rejected. Re-run the Codex OAuth flow "
                "or refresh the token.")
        resp.raise_for_status()
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        return resp.text

    def _rpc(self, method: str, params: dict | None = None, notify: bool = False) -> dict:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        request_id = None
        if not notify:
            self._next_id += 1
            request_id = self._next_id
            payload["id"] = request_id
        if params is not None:
            payload["params"] = params
        text = self._post(payload)
        messages = parse_messages(text)
        if notify and not messages:
            return {}
        if not messages:
            raise BinanceMCPError(f"{method}: empty response")
        matching = [m for m in messages if request_id is not None and m.get("id") == request_id]
        msg = matching[-1] if matching else messages[-1]
        if "error" in msg:
            err = msg["error"]
            raise BinanceMCPError(f"{err.get('code')}: {err.get('message')}")
        if "result" not in msg and not notify:
            raise BinanceMCPError(
                f"{method}: response has neither result nor error (id={msg.get('id')})")
        return msg

    # ------------------------------------------------------------------ MCP methods
    def initialize(self) -> dict:
        msg = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "binance-mcp-connect", "version": "0.1"},
        })
        self.server_info = msg.get("result", {}).get("serverInfo", {})
        self._initialized = True
        try:
            self._rpc("notifications/initialized", {}, notify=True)
        except Exception:  # noqa: BLE001 - optional notification
            pass
        return self.server_info

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def list_tools(self) -> list[dict]:
        self._ensure_initialized()
        tools: list[dict] = []
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            params = {} if cursor is None else {"cursor": cursor}
            msg = self._rpc("tools/list", params)
            result = msg.get("result") or {}
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
            if cursor in seen:
                raise BinanceMCPError(f"tools/list pagination loop detected at cursor {cursor!r}")
            seen.add(cursor)
        else:
            raise BinanceMCPError(f"tools/list exceeded {MAX_PAGES} pages")
        return tools

    def call(self, name: str, arguments: dict | None = None) -> Any:
        self._ensure_initialized()
        msg = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        result = msg.get("result", {})
        if result.get("isError"):
            raise BinanceMCPError(str(result)[:500])
        sc = result.get("structuredContent")
        if sc:
            return sc
        content = result.get("content") or []
        if content and content[0].get("type") == "text":
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return result

    # ------------------------------------------------------------------ convenience
    def price(self, symbol: str) -> float:
        return float(self.call("futures_usds.symbolPriceTicker", {"symbol": symbol})["price"])

    def balance(self) -> dict:
        return self.call("futures_usds.accountInformationV3", {})

    def positions(self, symbol: str | None = None) -> list[dict]:
        args = {"symbol": symbol} if symbol else {}
        rows = self.call("futures_usds.positionInformationV2", args)
        if isinstance(rows, dict):
            rows = [rows]
        return [p for p in rows if abs(float(p.get("positionAmt", 0) or 0)) > 0]
