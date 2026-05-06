# DeepRAG MCP 对接 DeerFlow 整合指南

> **WING**
> **初稿：2026-04-29**

---

## 一、DeepRAG MCP 深度分析报告

### 1.1 技术架构概览

```
DeerFlow (MCP Client)
        │
        │ HTTP / Streamable HTTP
        ▼
DeepRAG MCP Server (Python)
        │
        │ 本地知识库
        ▼
Knowledge-Base (文件检索)
```

### 1.2 DeepRAG MCP 项目信息

| 属性 | 值 |
|------|-----|
| 协议类型 | HTTP (Streamable HTTP, MCP 2025-06-18) |
| 默认地址 | `http://192.168.1.56:86/mcp` |
| 传输协议 | Streamable HTTP |
| 认证方式 | 无（内网服务） |

### 1.3 DeepRAG MCP 工具清单

| 工具名称 | 功能 | Annotations |
|----------|------|-------------|
| `deeprag_get_knowledge_base_info` | 获取知识库摘要和文件树 | readOnlyHint=true |
| `deeprag_retrieve_files` | 检索指定文件内容 | readOnlyHint=true |
| `deeprag_search_files` | 搜索包含关键词的文件 | readOnlyHint=true |
| `deeprag_sync_knowledge_base` | 触发知识库同步 | readOnlyHint=false |
| `deeprag_get_sync_status` | 获取同步进度 | readOnlyHint=true |
| `deeprag_chat` | 与 DeepRAG 单轮对话 | readOnlyHint=false |

---

## 二、DeerFlow MCP 集成点分析

### 2.1 DeerFlow MCP 加载机制

DeerFlow 使用 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 加载 MCP 工具：

```python
# backend/packages/harness/deerflow/mcp/tools.py
from langchain_mcp_adapters.client import MultiServerMCPClient

async def get_mcp_tools() -> list[BaseTool]:
    extensions_config = ExtensionsConfig.from_file()
    servers_config = build_servers_config(extensions_config)
    client = MultiServerMCPClient(servers_config, tool_name_prefix=True)
    tools = await client.get_tools()
    return tools
```

### 2.2 MCP 懒加载机制

**重要**：MCP 工具在 DeerFlow 中是懒加载的，只有在第一次请求时才会初始化 MCP 客户端。

---

## 三、DeepRAG MCP 对接 DeerFlow 配置方案

### 3.1 配置修改

**修改文件：`extensions_config.json`**

```json
{
  "mcpServers": {
    "deeprag": {
      "enabled": true,
      "type": "http",
      "url": "http://192.168.1.56:86/mcp",
      "description": "DeepRAG 知识库检索 - 支持文件检索、搜索、同步等功能"
    }
  },
  "skills": {}
}
```

### 3.2 同步 Git 追踪文件

同时更新 `extensions_config.example.json` 以确保 Git 追踪：

```json
{
  "mcpServers": {
    "deeprag": {
      "enabled": true,
      "type": "http",
      "url": "http://192.168.1.56:86/mcp",
      "description": "DeepRAG 知识库检索 - 支持文件检索、搜索、同步等功能"
    }
  },
  "skills": {}
}
```

---

## 四、部署架构

### 4.1 Docker 部署

```
┌─────────────────────────────────────────────────────────────┐
│                        Windows 宿主机                          │
│                                                              │
│   ┌─────────────────────┐          ┌─────────────────────┐ │
│   │  DeerFlow Docker     │  HTTP    │  DeepRAG MCP        │ │
│   │  (host 网络模式)     │─────────►│  (192.168.1.56:86)  │ │
│   │                     │  8172    │  (独立服务器)        │ │
│   └─────────────────────┘          └─────────────────────┘ │
│           │                                      │          │
│           ▼                                      ▼          │
│   ┌─────────────────────┐          ┌─────────────────────┐ │
│   │  ADS MCP            │          │  Knowledge-Base    │ │
│   │  (Node.js stdio)    │          │  (在 DeepRAG 服务器)│ │
│   └─────────────────────┘          └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、验证结果（2026-04-29）

### 5.1 验证日志

```
✅ Configured MCP server: deeprag
✅ Received session ID: 0ec21caefdb44d2faab414cd55090f33
✅ Negotiated protocol version: 2025-11-25
✅ Successfully loaded 60 tool(s) from MCP servers
✅ Total tools loaded: 10, built-in tools: 2, MCP tools: 60
```

### 5.2 功能验证

通过 DeerFlow Web UI 发送测试消息后，日志显示 DeepRAG MCP 工具已成功加载。

### 5.3 关键发现

| 发现项 | 说明 |
|--------|------|
| **MCP 懒加载** | MCP 工具在 DeerFlow 中是懒加载的，只有在第一次请求时才会初始化 |
| **工具数量** | DeepRAG MCP 提供 9 个工具（总 MCP 工具 60 个含 ADS 51 个） |
| **HTTP 连接** | DeerFlow 通过 HTTP 成功连接到 `http://192.168.1.56:86/mcp` |

---

## 六、故障排查

### 问题 1: `connection refused`

**排查**:
```bash
# 1. 确认 DeepRAG MCP 服务运行
curl http://192.168.1.56:86/mcp

# 2. 确认网络可达
docker exec deer-flow-gateway ping -c 3 192.168.1.56

# 3. 确认端口开放
docker exec deer-flow-gateway nc -zv 192.168.1.56 86
```

**常见原因**:
- DeepRAG MCP 未启动 → 启动 DeepRAG MCP 服务
- 防火墙阻止 → 开放 192.168.1.56:86
- 网络不通 → 检查网络配置

### 问题 2: MCP 工具未出现在 Agent 中

**原因**：MCP 工具是懒加载的，需要发送请求触发初始化。

**解决**：在 DeerFlow Web UI 中发送一条消息。

---

## 七、维护清单

### 每次修改配置后
- [ ] 重启 DeerFlow：`docker compose -f docker-compose-dev.yaml down && docker compose -f docker-compose-dev.yaml up -d`
- [ ] 验证日志：`docker logs deer-flow-langgraph --tail 30 | grep deeprag`

### 部署前检查
- [ ] 确认 DeepRAG MCP 服务运行中
- [ ] 确认 `extensions_config.json` 和 `extensions_config.example.json` 已更新

---

## 八、AI 开发参考文档

### 8.1 DeepRAG MCP 工具速查

| 业务场景 | 推荐工具 | 调用示例 |
|----------|----------|----------|
| 了解知识库结构 | `deeprag_get_knowledge_base_info` | `deeprag_get_knowledge_base_info({})` |
| 搜索相关文件 | `deeprag_search_files` | `deeprag_search_files({"query": "关键词", "limit": 5})` |
| 获取文件内容 | `deeprag_retrieve_files` | `deeprag_retrieve_files({"file_paths": ["path/to/file.md"]})` |
| 更新知识库 | `deeprag_sync_knowledge_base` | `deeprag_sync_knowledge_base({"force": false})` |
| 查询同步状态 | `deeprag_get_sync_status` | `deeprag_get_sync_status({})` |
| RAG 对话 | `deeprag_chat` | `deeprag_chat({"message": "用户问题"})` |

### 8.2 最佳实践

**推荐工作流**:
```
1. 先调用 deeprag_get_knowledge_base_info 了解知识库结构
2. 根据用户问题调用 deeprag_search_files 定位相关文件
3. 调用 deeprag_retrieve_files 获取具体文件内容
4. 综合信息回答用户问题
```

---

## 九、相关文档

- [ADS-MCP对接DeerFlow整合指南-实测版.md](./ADS-MCP对接DeerFlow整合指南-实测版.md)
- [RAGFLOW_MCP_INTEGRATION.md](./RAGFLOW_MCP_INTEGRATION.md)

---

**WING**
**2026-04-29 初稿**
**2026-04-29 验证完成**
