
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Any, List

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool

# Global client instance (lazy init)
_client: MultiServerMCPClient | None = None

# Resolve project root (uda-hub/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _build_connections_config() -> Dict[str, Dict[str, Any]]:
    """
    Build the MultiServerMCPClient connections config.

    We use stdio transport and launch each FastMCP server as a subprocess
    via `python server.py`.
    """
    return {
        "kb": {
            "transport": "stdio",
            "command": "python",
            "args": [str(PROJECT_ROOT / "mcp_services" / "kb" / "server.py")],
        },
        "account": {
            "transport": "stdio",
            "command": "python",
            "args": [str(PROJECT_ROOT / "mcp_services" / "account" / "server.py")],
        },
        "memory": {
            "transport": "stdio",
            "command": "python",
            "args": [str(PROJECT_ROOT / "mcp_services" / "memory" / "server.py")],
        },
    }


async def aget_client() -> MultiServerMCPClient:
    """
    Async helper to initialize (once) and return the global MultiServerMCPClient.

    Safe to use inside Jupyter and async code.
    """
    global _client
    if _client is None:
        _client = MultiServerMCPClient(_build_connections_config())
    return _client


async def aget_tools_for_servers(*servers: str) -> List[BaseTool]:
    """
    Async helper: fetch LangChain tools from one or more MCP servers.

    NOTE: MultiServerMCPClient.get_tools() returns tools from *all* servers,
    so we filter by name prefix (kb_, account_, memory_) when `servers`
    are specified.
    """
    client = await aget_client()
    all_tools = await client.get_tools()  # no positional args

    if not servers:
        return all_tools

    prefixes = tuple(f"{s}_" for s in servers)
    filtered = [t for t in all_tools if t.name.startswith(prefixes)]
    return filtered


def get_tools_for_servers(*servers: str) -> List[BaseTool]:
    """
    Synchronous wrapper to fetch tools from one or more MCP servers.

    Use this in scripts (like 03_agentic_app.py), NOT inside Jupyter notebooks.

        tools = get_tools_for_servers("kb")

    In Jupyter, prefer `await aget_tools_for_servers("kb")`.
    """
    return asyncio.run(aget_tools_for_servers(*servers))
