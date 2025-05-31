"""Utility functions for interacting with MCP servers."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import logging

try:
    from openai_agents_python import (
        MCPServerStdio,
        MCPServerSse,
        MCPServerStreamableHttp,
    )
except Exception:  # pragma: no cover - openai-agents may not be installed
    MCPServerStdio = None
    MCPServerSse = None
    MCPServerStreamableHttp = None


class _StubMCPServer:
    """Fallback server used when ``openai-agents`` is unavailable."""

    async def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "echo",
                "description": "Return the provided text",
            }
        ]

    async def call_tool(
        self, name: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        if name != "echo":
            return {"error": f"Unknown tool: {name}"}
        return {"text": (params or {}).get("text", "")}


class MCPClient:
    """Wrapper around an MCP server."""

    def __init__(self, command: str | None = None, url: str | None = None):
        self.command = command
        self.url = url
        self._server = None

    async def _ensure_server(self):
        if self._server is not None:
            return
        if MCPServerStdio and self.command:
            self._server = MCPServerStdio(params={"command": self.command, "args": []})
            await self._server.__aenter__()
        elif MCPServerSse and self.url:
            self._server = MCPServerSse(url=self.url)
            await self._server.__aenter__()
        elif MCPServerStreamableHttp and self.url:
            self._server = MCPServerStreamableHttp(url=self.url)
            await self._server.__aenter__()
        else:
            logging.warning("openai-agents not installed, using stub MCP server")
            self._server = _StubMCPServer()

    async def list_tools(self) -> List[Dict[str, Any]]:
        await self._ensure_server()
        return await self._server.list_tools()

    async def call_tool(
        self, name: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        await self._ensure_server()
        return await self._server.call_tool(name, params)

    async def close(self):  # pragma: no cover - best effort cleanup
        if hasattr(self._server, "__aexit__"):
            await self._server.__aexit__(None, None, None)
        self._server = None


# Convenience functions used by routes
_default_client: MCPClient | None = None


def _get_default_client() -> MCPClient:
    global _default_client
    if _default_client is None:
        from app import config

        _default_client = MCPClient(
            command=config.MCP_SERVER_COMMAND,
            url=config.MCP_SERVER_URL,
        )
    return _default_client


def list_tools_sync() -> List[Dict[str, Any]]:
    """Return the list of tools from the configured MCP server."""
    client = _get_default_client()
    return asyncio.run(client.list_tools())


def call_tool_sync(name: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Call a tool on the configured MCP server."""
    client = _get_default_client()
    return asyncio.run(client.call_tool(name, params))
