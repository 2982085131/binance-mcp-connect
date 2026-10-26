"""Regression tests for the external code review findings (2026-10-26)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from binance_mcp_connect import (
    BinanceMCPClient,
    BinanceMCPError,
    CodexCredentialsError,
    extract_token,
    parse_messages,
    round_qty,
)
from binance_mcp_connect.cimd import authorize_url, client_document
from binance_mcp_connect.cli import _first_line


def _secrets(*entries: dict) -> bytes:
    secrets = {}
    for i, e in enumerate(entries):
        secrets[f"global/MCP_OAUTH_{i}"] = json.dumps(e)
    return json.dumps({"version": 1, "secrets": secrets}).encode()


def _entry(name: str, url: str, token: str) -> dict:
    return {"server_name": name, "url": url, "client_id": "codex",
            "token_response": {"access_token": token, "token_type": "Bearer"},
            "expires_at": 1795338008613}


# 1. token binding -----------------------------------------------------------
def test_token_selects_binance_not_first():
    data = _secrets(
        _entry("other", "https://other.example/mcp", "FAKE_OTHER"),
        _entry("binance", "https://agent.binance.com/mcp/agentic", "FAKE_BINANCE"),
    )
    assert extract_token(data)["access_token"] == "FAKE_BINANCE"


def test_token_refuses_when_binance_missing():
    data = _secrets(_entry("other", "https://other.example/mcp", "FAKE_OTHER"))
    with pytest.raises(CodexCredentialsError, match="no credential"):
        extract_token(data)


def test_token_refuses_ambiguous():
    data = _secrets(
        _entry("binance", "https://agent.binance.com/mcp/agentic", "A"),
        _entry("binance", "https://agent.binance.com/mcp/agentic", "B"),
    )
    with pytest.raises(CodexCredentialsError, match="multiple"):
        extract_token(data)


# 2. quantity rounding -------------------------------------------------------
def test_round_qty_no_float_drift():
    assert round_qty(0.043) == 0.043
    assert round_qty(0.051) == 0.051
    assert round_qty(0.0099) == 0.009


# 4. SSE / response validation ----------------------------------------------
def test_sse_multiline_data():
    body = ('event: message\n'
            'data: {"jsonrpc":"2.0",\n'
            'data: "id":1,"result":{"ok":true}}\n\n')
    messages = parse_messages(body)
    assert messages and messages[0]["result"]["ok"] is True


def test_empty_response_raises():
    client = BinanceMCPClient("token")
    client._post = lambda payload: ""  # type: ignore[method-assign]
    with pytest.raises(BinanceMCPError, match="empty response"):
        client._rpc("tools/list", {})


def test_missing_result_raises():
    client = BinanceMCPClient("token")
    client._post = lambda payload: '{"jsonrpc":"2.0","id":1}'  # type: ignore[method-assign]
    with pytest.raises(BinanceMCPError, match="neither result nor error"):
        client._rpc("tools/list", {})


# 7. pagination + stateless init --------------------------------------------
def test_tools_pagination():
    client = BinanceMCPClient("token")
    client._initialized = True
    seen = []

    def fake_rpc(method, params=None, notify=False):
        seen.append(params)
        if params and params.get("cursor") == "p2":
            return {"result": {"tools": [{"name": "b"}]}}
        return {"result": {"tools": [{"name": "a"}], "nextCursor": "p2"}}

    client._rpc = fake_rpc  # type: ignore[method-assign]
    assert [t["name"] for t in client.list_tools()] == ["a", "b"]
    assert len(seen) == 2


def test_stateless_session_initializes_once():
    client = BinanceMCPClient("token")
    calls = []

    def fake_rpc(method, params=None, notify=False):
        calls.append(method)
        if method == "initialize":
            return {"result": {"serverInfo": {}}}
        if method == "notifications/initialized":
            return {}
        if method == "tools/list":
            return {"result": {"tools": []}}
        raise AssertionError(method)

    client._rpc = fake_rpc  # type: ignore[method-assign]
    client.list_tools()
    client.list_tools()
    assert calls.count("initialize") == 1


# 5/6. CLI helpers -----------------------------------------------------------
def test_first_line_handles_none():
    assert _first_line(None) == ""
    assert _first_line("") == ""
    assert _first_line("hello\nworld") == "hello"


# 8. CIMD redirect consistency ----------------------------------------------
def test_cimd_redirect_is_consistent():
    redirect = "https://example.invalid/auth/callback"
    doc = client_document("https://example.invalid", redirect)
    url = authorize_url("https://as.example/authorize", "https://example.invalid",
                        redirect, "state", "challenge", "https://agent.binance.com/mcp/agentic")
    assert doc["redirect_uris"] == [redirect]
    assert "redirect_uri=https%3A%2F%2Fexample.invalid%2Fauth%2Fcallback" in url


# 3. example cancels even when query fails ----------------------------------
def _load_safe_order():
    path = Path(__file__).resolve().parents[1] / "examples" / "safe_order.py"
    spec = importlib.util.spec_from_file_location("safe_order", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeClient:
    def __init__(self, fail_cancel: bool = False):
        self.cancelled = False
        self.fail_cancel = fail_cancel

    def call(self, name, args):
        if name.endswith("newOrder"):
            return {"orderId": 123}
        if name.endswith("queryOrder"):
            raise TimeoutError("boom")
        if name.endswith("cancelOrder"):
            self.cancelled = True
            if self.fail_cancel:
                raise RuntimeError("cancel failed")
            return {"status": "CANCELED"}
        raise AssertionError(name)


def _order():
    from binance_mcp_connect import Order
    return Order(symbol="ETHUSDT", side="BUY", position_side="LONG",
                 order_type="LIMIT", quantity=0.009, price=2400.0, time_in_force="GTX")


def test_safe_order_cancels_after_query_failure():
    module = _load_safe_order()
    fake = _FakeClient()
    assert module.place_and_cancel(fake, _order(), "ETHUSDT", wait_seconds=0) == 0
    assert fake.cancelled is True


def test_safe_order_reports_cancel_failure():
    module = _load_safe_order()
    fake = _FakeClient(fail_cancel=True)
    assert module.place_and_cancel(fake, _order(), "ETHUSDT", wait_seconds=0) == 2
    assert fake.cancelled is True
