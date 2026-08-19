"""mcp_resilience — per-server MCP tool loading isolation (zero core intrusion).

Patches ``deerflow.mcp.tools.get_mcp_tools`` (and the package-level
re-export ``deerflow.mcp.get_mcp_tools``) so each configured MCP server is
loaded independently: one failing server no longer kills all the others.
"""
