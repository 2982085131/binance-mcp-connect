"""OAuth discovery helpers for the Binance Agentic MCP server."""
from __future__ import annotations

import requests

MCP_ENDPOINT = "https://agent.binance.com/mcp/agentic"
PROTECTED_RESOURCE_URLS = [
    "https://agent.binance.com/.well-known/oauth-protected-resource/gateway-mcp",
    "https://agent.binance.com/.well-known/oauth-protected-resource",
]
AS_METADATA_URL = "https://agent.binance.com/.well-known/oauth-authorization-server"


def _get_json(url: str, timeout: int = 20) -> dict:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "binance-mcp-connect/0.1"})
    resp.raise_for_status()
    return resp.json()


def fetch_protected_resource() -> dict:
    last_error: Exception | None = None
    for url in PROTECTED_RESOURCE_URLS:
        try:
            data = _get_json(url)
            data["_url"] = url
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"could not fetch protected-resource metadata: {last_error}")


def fetch_authorization_server() -> dict:
    return _get_json(AS_METADATA_URL)


def discover() -> dict:
    """Return the OAuth metadata needed to start an authorization-code flow."""
    resource = fetch_protected_resource()
    as_meta = fetch_authorization_server()
    return {
        "resource": resource.get("resource", MCP_ENDPOINT),
        "authorization_servers": resource.get("authorization_servers", []),
        "authorization_endpoint": as_meta.get("authorization_endpoint"),
        "token_endpoint": as_meta.get("token_endpoint"),
        "code_challenge_methods": as_meta.get("code_challenge_methods_supported", []),
        "client_id_metadata_document_supported": as_meta.get(
            "client_id_metadata_document_supported", False),
        "token_endpoint_auth_methods": as_meta.get("token_endpoint_auth_methods_supported", []),
    }
