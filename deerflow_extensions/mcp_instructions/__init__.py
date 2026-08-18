"""mcp_instructions — MCP 服务器指令（initialize 握手 instructions）注入扩展。

通过双点 monkey-patch（tool_search + prompt 模块属性替换）将 MCP server
声明的 instructions（如 mcp-agent-mcp 的 SERVER_INSTRUCTIONS）注入 agent
system prompt，覆盖 lead / embedded client / subagent 三条构建路径。
核心源码零改动（Level 3 monkey-patch）。
"""

from deerflow_extensions.mcp_instructions.startup import (
    get_registry,
    install_mcp_instructions,
)

__all__ = ["install_mcp_instructions", "get_registry"]
