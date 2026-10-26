"""Client ID Metadata Document (CIMD) OAuth flow - kept for reference.

Status as of 2026-10: Binance's authorization endpoint (accounts.binance.com)
is protected by a WAF that returns **403 Forbidden** to self-registered clients,
even when the CIMD document is publicly reachable and the request is opened from
a phone on a different network. Manual OAuth therefore does not complete; the
official-client route (see ``codex_creds``) is the working path.

This module is still useful to inspect the flow and to retry if Binance changes
the policy. It serves ``/client.json`` on port 8080; expose it with a tunnel
(e.g. ``cloudflared tunnel --url http://127.0.0.1:8080``) and pass the public URL.
"""
from __future__ import annotations

import base64
import functools
import hashlib
import http.server
import json
import secrets
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .metadata import discover

METADATA_PORT = 8080
DEFAULT_REDIRECT = "http://localhost:1455/auth/callback"


@dataclass
class _Flow:
    client_id: str
    state: str                    # expected state
    code: str | None = None
    received_state: str | None = None
    done: threading.Event = field(default_factory=threading.Event)


def client_document(public_url: str, redirect_uri: str) -> dict:
    """Build the CIMD document; the redirect URI is used verbatim everywhere."""
    base = public_url.rstrip("/")
    return {
        "client_id": base + "/client.json",
        "client_name": "binance-mcp-connect",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }


def authorize_url(authorization_endpoint: str, public_url: str, redirect_uri: str,
                  state: str, challenge: str, resource: str) -> str:
    base = public_url.rstrip("/")
    params = {
        "response_type": "code",
        "client_id": base + "/client.json",
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": resource,
    }
    return authorization_endpoint + "?" + urllib.parse.urlencode(params)


class _MetadataHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, document: dict | None = None, **kwargs):
        self.document = document or {}
        super().__init__(*args, **kwargs)

    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] != "/client.json":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(self.document).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, flow: _Flow | None = None, path: str = "/auth/callback", **kwargs):
        self.flow = flow
        self.callback_path = path
        super().__init__(*args, **kwargs)

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != self.callback_path:
            self.send_response(404)
            self.end_headers()
            return
        q = urllib.parse.parse_qs(parsed.query)
        assert self.flow is not None
        self.flow.code = (q.get("code") or [None])[0]
        self.flow.received_state = (q.get("state") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h2>Authorization received. You can close this tab.</h2>")
        self.flow.done.set()

    def log_message(self, *args):
        pass


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def run(public_url: str, redirect_uri: str = DEFAULT_REDIRECT,
        timeout: int = 600) -> dict:
    """Run the CIMD authorization-code flow and return the token response."""
    meta = discover()
    if not meta["client_id_metadata_document_supported"]:
        raise RuntimeError("server does not advertise CIMD support")

    public_url = public_url.rstrip("/")
    parsed = urllib.parse.urlparse(redirect_uri)
    callback_host = parsed.hostname or "localhost"
    callback_port = parsed.port or 80
    callback_path = parsed.path or "/auth/callback"

    verifier, challenge = _pkce()
    flow = _Flow(client_id=public_url + "/client.json", state=secrets.token_urlsafe(16))
    document = client_document(public_url, redirect_uri)

    metadata_handler = functools.partial(_MetadataHandler, document=document)
    callback_handler = functools.partial(_CallbackHandler, flow=flow, path=callback_path)
    metadata_server = http.server.HTTPServer(("", METADATA_PORT), metadata_handler)
    callback_server = http.server.HTTPServer((callback_host, callback_port), callback_handler)
    try:
        threading.Thread(target=metadata_server.serve_forever, daemon=True).start()
        threading.Thread(target=callback_server.serve_forever, daemon=True).start()

        url = authorize_url(meta["authorization_endpoint"], public_url, redirect_uri,
                            flow.state, challenge, meta["resource"])
        print("Open this URL in a browser and authorize:\n\n" + url + "\n")
        if not flow.done.wait(timeout):
            raise TimeoutError("no OAuth callback received")
        if flow.received_state != flow.state:
            raise RuntimeError("state mismatch")

        body = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": flow.code,
            "redirect_uri": redirect_uri,
            "client_id": flow.client_id,
            "code_verifier": verifier,
        }).encode()
        req = urllib.request.Request(meta["token_endpoint"], data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    finally:
        for server in (metadata_server, callback_server):
            try:
                server.shutdown()
            except Exception:  # noqa: BLE001
                pass
            try:
                server.server_close()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m binance_mcp_connect.cimd https://your-tunnel-host")
    print(json.dumps(run(sys.argv[1]), indent=2)[:800])
