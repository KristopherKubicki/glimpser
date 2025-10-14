import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.utils import mcp


class TestMCPClient(unittest.TestCase):
    def tearDown(self):
        mcp._default_client = None

    def test_stub_operations(self):
        client = mcp.MCPClient()
        tools = asyncio.run(client.list_tools())
        self.assertTrue(any(t["name"] == "echo" for t in tools))

        result = asyncio.run(client.call_tool("echo", {"text": "hi"}))
        self.assertEqual(result, {"text": "hi"})

        result = asyncio.run(client.call_tool("bad"))
        self.assertEqual(result, {"error": "Unknown tool: bad"})

    def test_register_local_tool(self):
        def upper(params=None):
            text = (params or {}).get("text", "")
            return {"text": text.upper()}

        mcp.register_local_tool("upper", "Uppercase text", upper)
        result = mcp.call_tool_sync("upper", {"text": "hi"})
        self.assertEqual(result, {"text": "HI"})

    def test_sync_helpers_use_config(self):
        with (
            patch("app.config.MCP_SERVER_COMMAND", "cmd"),
            patch("app.config.MCP_SERVER_URL", "url"),
            patch("app.utils.mcp.MCPClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.list_tools = AsyncMock(return_value=[{"name": "echo"}])
            inst.call_tool = AsyncMock(return_value={"text": "hi"})
            mcp._default_client = None
            tools1 = mcp.list_tools_sync()
            result = mcp.call_tool_sync("echo", {"text": "hi"})
        self.assertEqual(tools1, [{"name": "echo"}])
        self.assertEqual(result, {"text": "hi"})
        mock_cls.assert_called_once_with(command="cmd", url="url")


if __name__ == "__main__":
    unittest.main()
