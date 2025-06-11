"""Utility functions for interacting with MCP servers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

try:
    from openai_agents_python import (
        MCPServerSse,
        MCPServerStdio,
        MCPServerStreamableHttp,
    )
except Exception:  # pragma: no cover - openai-agents may not be installed
    MCPServerStdio = None
    MCPServerSse = None
    MCPServerStreamableHttp = None


class _StubMCPServer:
    """Fallback server used when ``openai-agents`` is unavailable."""

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        self.register_tool(
            "echo",
            "Return the provided text",
            lambda params=None: {"text": (params or {}).get("text", "")},
        )

    def register_tool(self, name: str, description: str, func) -> None:
        """Register a callable as a stub MCP tool."""
        self._tools[name] = {"description": description, "func": func}

    async def list_tools(self) -> List[Dict[str, Any]]:
        return [{"name": name, "description": info["description"]} for name, info in self._tools.items()]

    async def call_tool(self, name: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        info = self._tools.get(name)
        if not info:
            return {"error": f"Unknown tool: {name}"}
        return info["func"](params)


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

    async def call_tool(self, name: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
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


def register_local_tool(name: str, description: str, func) -> None:
    """Register a stub MCP tool when no server is available."""
    client = _get_default_client()
    asyncio.run(client._ensure_server())
    if isinstance(client._server, _StubMCPServer):  # type: ignore[attr-defined]
        client._server.register_tool(name, description, func)


def list_tools_sync() -> List[Dict[str, Any]]:
    """Return the list of tools from the configured MCP server."""
    client = _get_default_client()
    return asyncio.run(client.list_tools())


def call_tool_sync(name: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Call a tool on the configured MCP server."""
    client = _get_default_client()
    return asyncio.run(client.call_tool(name, params))
