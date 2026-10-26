from binance_mcp_connect import keyring_account, parse_body


def test_parse_json():
    assert parse_body('{"jsonrpc":"2.0","id":1,"result":{"ok":true}}')["result"]["ok"] is True


def test_parse_sse():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
    assert parse_body(body)["result"]["tools"] == []


def test_parse_empty():
    assert parse_body("") == {}


def test_keyring_account_windows_verbatim():
    # Observed on a real Codex install: the Rust keyring account uses the
    # verbatim path returned by fs::canonicalize.
    assert keyring_account(r"\\?\C:\Users\Pale_Knight\.codex") == "secrets|8daa9cf8d6535db3"
