"""Public API for binance-mcp-connect."""
from .client import (
    BinanceMCPAuthError,
    BinanceMCPClient,
    BinanceMCPError,
    parse_body,
    parse_messages,
)
from .codex_creds import (
    CodexCredentialsError,
    decrypt_age,
    extract_token,
    get_codex_token,
    get_codex_token_from_file,
    keyring_account,
)
from .metadata import discover
from .safety import (
    MIN_NOTIONAL,
    PRICE_TICK,
    QTY_STEP,
    Order,
    OrderValidationError,
    close_params,
    round_price,
    round_qty,
    validate,
)

__all__ = [
    "BinanceMCPClient",
    "BinanceMCPError",
    "BinanceMCPAuthError",
    "parse_body",
    "parse_messages",
    "CodexCredentialsError",
    "get_codex_token",
    "get_codex_token_from_file",
    "decrypt_age",
    "extract_token",
    "keyring_account",
    "discover",
    "Order",
    "OrderValidationError",
    "validate",
    "round_qty",
    "round_price",
    "MIN_NOTIONAL",
    "QTY_STEP",
    "PRICE_TICK",
    "close_params",
]

__version__ = "0.1.1"
