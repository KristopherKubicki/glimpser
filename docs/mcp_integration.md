# MCP Integration

Glimpser can delegate actions to an external **Model Control Plane (MCP)**. The
MCP server exposes a list of tools that can be invoked from the web interface or
through the `/mcp/tool/<name>` endpoint.

## Configuration
Set `MCP_SERVER_COMMAND` or `MCP_SERVER_URL` in `app/config.py` to point to the
MCP server. When neither is configured, Glimpser falls back to a lightweight
stub implementation.

## Registering Local Tools
When running without `openai-agents` installed, you can register custom tools
for the stub server using `register_local_tool`:

```python
from app.utils import mcp

def upper(params=None):
    text = (params or {}).get("text", "")
    return {"text": text.upper()}

mcp.register_local_tool("upper", "Uppercase text", upper)
```

The new tool immediately becomes available via `mcp.call_tool_sync("upper")` and
through the HTTP API.
