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


class BinanceMCPError(RuntimeError):
    """Raised when the MCP server returns a JSON-RPC error."""


class BinanceMCPAuthError(BinanceMCPError):
    """Raised on 401/403 from the MCP endpoint (expired or invalid token)."""


def parse_body(text: str) -> dict:
    """Parse either a JSON body or an SSE stream into a JSON-RPC message."""
    text = text.strip()
    if not text:
        return {}
    if text.startswith("{"):
        return json.loads(text)
    # SSE: events look like "event: message\ndata: {...}\n\n"
    last: dict = {}
    for line in text.splitlines():
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if chunk:
                try:
                    last = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
    return last


class BinanceMCPClient:
    def __init__(self, access_token: str, endpoint: str = DEFAULT_ENDPOINT, timeout: int = 30):
        if not access_token:
            raise ValueError("access_token is required")
        self.access_token = access_token
        self.endpoint = endpoint
        self.timeout = timeout
        self.session_id: str | None = None
        self.server_info: dict | None = None

    # ------------------------------------------------------------------ transport
    def _post(self, payload: dict, notify: bool = False) -> dict:
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
        return parse_body(resp.text)

    def _rpc(self, method: str, params: dict | None = None, notify: bool = False) -> dict:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notify:
            payload["id"] = 1
        if params is not None:
            payload["params"] = params
        msg = self._post(payload, notify=notify)
        if "error" in msg:
            err = msg["error"]
            raise BinanceMCPError(f"{err.get('code')}: {err.get('message')}")
        return msg

    # ------------------------------------------------------------------ MCP methods
    def initialize(self) -> dict:
        msg = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "binance-mcp-connect", "version": "0.1"},
        })
        self.server_info = msg.get("result", {}).get("serverInfo", {})
        try:
            self._rpc("notifications/initialized", {}, notify=True)
        except Exception:  # noqa: BLE001 - optional notification
            pass
        return self.server_info

    def list_tools(self) -> list[dict]:
        if not self.session_id:
            self.initialize()
        msg = self._rpc("tools/list", {})
        return msg.get("result", {}).get("tools", [])

    def call(self, name: str, arguments: dict | None = None) -> Any:
        if not self.session_id:
            self.initialize()
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
