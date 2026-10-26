"""Print the ETHUSDT mark price through Binance MCP."""
from binance_mcp_connect import BinanceMCPClient, get_codex_token

token = get_codex_token()
client = BinanceMCPClient(token["access_token"])
print(client.initialize())
print("ETHUSDT", client.price("ETHUSDT"))
