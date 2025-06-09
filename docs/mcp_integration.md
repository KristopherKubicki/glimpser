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

## Starting the MCP Server

Install the `openai-agents-python` package and launch the server locally:

```sh
pip install openai-agents-python
python -m openai_agents_python.server --port 7007
```

Set `MCP_SERVER_URL` to `"http://127.0.0.1:7007"` in `app/config.py` or export
the variable in your environment. If both `MCP_SERVER_COMMAND` and
`MCP_SERVER_URL` are empty, Glimpser falls back to the built-in stub server.

## Invoking Tools

Call a tool directly from Python:

```python
result = mcp.call_tool_sync("upper", {"text": "hello"})
print(result)  # {'text': 'HELLO'}
```

Or via HTTP:

```sh
curl -X POST http://localhost:8082/mcp/tool/upper \
     -H 'Content-Type: application/json' \
     -d '{"text": "hello"}'
```

The response will be JSON:

```json
{"text": "HELLO"}
```

## Error Handling

Requesting an unknown tool returns an error:

```python
mcp.call_tool_sync("missing")
# {'error': 'Unknown tool: missing'}
```

Connection errors indicate the MCP server is unreachable. Check the URL or rely
on the stub implementation when needed.
