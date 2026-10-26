"""Read the OAuth access token that the official Codex CLI stored for Binance MCP.

Codex encrypts MCP OAuth credentials with `age` (passphrase mode) into
``$CODEX_HOME/secrets/mcp_oauth.age``. The passphrase lives in the OS keyring
under service ``codex`` and account ``secrets|<sha256(canonical CODEX_HOME)[:16]>``.

This module reads that passphrase (Windows Credential Manager via ctypes, or the
`keyring` package), decrypts the age file with `pyrage`, and extracts the bearer
token. It only reads local files; it never talks to Binance.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from ctypes import wintypes
from pathlib import Path

KEYRING_SERVICE = "codex"
SECRETS_FILE = "mcp_oauth.age"
BINANCE_MCP_URL = "https://agent.binance.com/mcp/agentic"


def _norm_url(url: str | None) -> str:
    return (url or "").strip().rstrip("/").lower()


class CodexCredentialsError(RuntimeError):
    pass


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def canonical_candidates(home: Path) -> list[str]:
    """Rust's fs::canonicalize on Windows returns a verbatim (\\\\?\\) path."""
    resolved = str(home.resolve())
    if os.name == "nt":
        verbatim = resolved if resolved.startswith("\\\\?\\") else "\\\\?\\" + resolved
        return [verbatim, resolved]
    return [resolved]


def keyring_account(home_str: str) -> str:
    digest = hashlib.sha256(home_str.encode("utf-8")).hexdigest()[:16]
    return f"secrets|{digest}"


# --------------------------------------------------------------------------- Windows
class _CREDENTIAL_ATTRIBUTE(ctypes.Structure):
    _fields_ = [
        ("Keyword", wintypes.LPWSTR),
        ("Flags", wintypes.DWORD),
        ("ValueSize", wintypes.DWORD),
        ("Value", ctypes.POINTER(ctypes.c_byte)),
    ]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.POINTER(_CREDENTIAL_ATTRIBUTE)),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _read_windows_credential(target: str) -> str | None:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    cred_ptr = ctypes.POINTER(_CREDENTIAL)()
    ok = advapi32.CredReadW(target, 1, 0, ctypes.byref(cred_ptr))  # 1 = CRED_TYPE_GENERIC
    if not ok:
        return None
    try:
        cred = cred_ptr.contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    finally:
        advapi32.CredFree(cred_ptr)
    if not blob:
        return None
    # The Rust keyring crate stores UTF-16LE on Windows.
    try:
        return blob.decode("utf-16-le").rstrip("\x00")
    except UnicodeDecodeError:
        return blob.decode("utf-8", errors="replace")


def read_passphrase(home: Path) -> tuple[str, str]:
    """Return (passphrase, account) for the given CODEX_HOME."""
    errors: list[str] = []
    for cand in canonical_candidates(home):
        account = keyring_account(cand)
        if os.name == "nt":
            target = f"{account}.{KEYRING_SERVICE}"
            try:
                pw = _read_windows_credential(target)
                if pw:
                    return pw, account
            except OSError as exc:  # pragma: no cover - platform specific
                errors.append(str(exc))
        try:
            import keyring  # optional dependency

            pw = keyring.get_password(KEYRING_SERVICE, account)
            if pw:
                return pw, account
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    raise CodexCredentialsError(
        "could not read the Codex keyring passphrase; tried accounts for "
        f"{canonical_candidates(home)}. Errors: {errors[:3]}")


# --------------------------------------------------------------------------- age
def decrypt_age(path: Path, passphrase: str) -> bytes:
    try:
        from pyrage import passphrase as age_passphrase
    except ImportError as exc:  # pragma: no cover
        raise CodexCredentialsError("pyrage is required: pip install pyrage") from exc
    ciphertext = path.read_bytes()
    return age_passphrase.decrypt(ciphertext, passphrase)


def extract_token(decrypted: bytes, expected_server: str = "binance",
                  expected_url: str = BINANCE_MCP_URL) -> dict:
    """Pick the token bound to Binance, never "the first token we find".

    Codex can hold credentials for several MCP servers. Sending the wrong
    bearer token to Binance would leak another service's credential.
    """
    payload = json.loads(decrypted)
    secrets = payload.get("secrets", {})
    candidates: list[dict] = []
    for value in secrets.values():
        try:
            inner = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            continue
        token = inner.get("token_response") or {}
        if token.get("access_token"):
            candidates.append({
                "access_token": token["access_token"],
                "token_type": token.get("token_type", "Bearer"),
                "expires_at": inner.get("expires_at"),
                "server_name": inner.get("server_name"),
                "url": inner.get("url"),
                "client_id": inner.get("client_id"),
            })
    if not candidates:
        raise CodexCredentialsError("no access_token found in the decrypted secrets file")

    target_url = _norm_url(expected_url)
    matched = [
        c for c in candidates
        if c.get("server_name") == expected_server or _norm_url(c.get("url")) == target_url
    ]
    if len(matched) == 1:
        return matched[0]
    if not matched:
        found = sorted({f"{c.get('server_name')} ({c.get('url')})" for c in candidates})
        raise CodexCredentialsError(
            f"no credential for server '{expected_server}' at {expected_url}; "
            f"found: {found}")
    raise CodexCredentialsError(
        f"multiple credentials match '{expected_server}'; refusing to guess: "
        f"{[c.get('url') for c in matched]}")


def get_codex_token(home: Path | None = None) -> dict:
    home = home or codex_home()
    path = home / "secrets" / SECRETS_FILE
    if not path.exists():
        raise CodexCredentialsError(
            f"{path} not found. Connect Binance once with the official Codex CLI:\n"
            "  codex mcp add binance --url https://agent.binance.com/mcp/agentic "
            "--oauth-client-id codex")
    passphrase, account = read_passphrase(home)
    decrypted = decrypt_age(path, passphrase)
    info = extract_token(decrypted)
    info["account"] = account
    return info


def get_codex_token_from_file(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "access_token" not in data:
        raise CodexCredentialsError(f"{path} does not contain access_token")
    return data
