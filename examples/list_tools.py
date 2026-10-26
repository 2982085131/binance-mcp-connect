"""List every tool exposed by Binance's Agentic MCP server."""
from binance_mcp_connect import BinanceMCPClient, get_codex_token

client = BinanceMCPClient(get_codex_token()["access_token"])
for tool in client.list_tools():
    print(f"{tool['name']:55s} {(tool.get('description') or '').splitlines()[0][:90]}")
