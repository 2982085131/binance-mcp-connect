"""Client ID Metadata Document (CIMD) OAuth flow - kept for reference.

Status as of 2026-10: Binance's authorization endpoint (accounts.binance.com)
is protected by a WAF that returns **403 Forbidden** to self-registered clients,
even when the CIMD document is publicly reachable and the request is opened from
a phone on a different network. Manual OAuth therefore does not complete; the
official-client route (see ``codex_creds``) is the working path.

This module is still useful to inspect the flow and to retry if Binance changes
the policy. It serves ``/client.json`` on a local port; expose it with a tunnel
(e.g. ``cloudflared tunnel --url http://127.0.0.1:8080``) and pass the public URL.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.parse
import urllib.request

from .metadata import discover

REDIRECT_PATH = "/auth/callback"


class _MetadataHandler(http.server.BaseHTTPRequestHandler):
    public_url = ""

    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] != "/client.json":
            self.send_response(404)
            self.end_headers()
            return
        doc = {
            "client_id": self.public_url + "/client.json",
            "client_name": "binance-mcp-connect",
            "redirect_uris": [self.public_url.replace("https://", "http://") + REDIRECT_PATH],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
        body = json.dumps(doc).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        pass


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code = None
    state = None
    done = threading.Event()

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != REDIRECT_PATH:
            self.send_response(404)
            self.end_headers()
            return
        q = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.code = (q.get("code") or [None])[0]
        _CallbackHandler.state = (q.get("state") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h2>Authorization received. You can close this tab.</h2>")
        _CallbackHandler.done.set()

    def log_message(self, *args):
        pass


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def run(public_url: str, redirect_uri: str = "http://localhost:1455/auth/callback",
        timeout: int = 600) -> dict:
    """Run the CIMD authorization-code flow and return the token response.

    ``public_url`` must be an HTTPS origin exposing this process on port 8080.
    """
    meta = discover()
    if not meta["client_id_metadata_document_supported"]:
        raise RuntimeError("server does not advertise CIMD support")

    _MetadataHandler.public_url = public_url.rstrip("/")
    metadata_server = http.server.HTTPServer(("", 8080), _MetadataHandler)
    threading.Thread(target=metadata_server.serve_forever, daemon=True).start()

    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    client_id = _MetadataHandler.public_url + "/client.json"
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": meta["resource"],
    }
    url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)
    print("Open this URL in a browser and authorize:\n\n" + url + "\n")

    callback_server = http.server.HTTPServer(("", 1455), _CallbackHandler)
    threading.Thread(target=callback_server.serve_forever, daemon=True).start()
    if not _CallbackHandler.done.wait(timeout):
        raise TimeoutError("no OAuth callback received")
    if _CallbackHandler.state != state:
        raise RuntimeError("state mismatch")
    metadata_server.shutdown()
    callback_server.shutdown()

    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": _CallbackHandler.code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    }).encode()
    req = urllib.request.Request(meta["token_endpoint"], data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m binance_mcp_connect.cimd https://your-tunnel-host")
    print(json.dumps(run(sys.argv[1]), indent=2)[:800])
