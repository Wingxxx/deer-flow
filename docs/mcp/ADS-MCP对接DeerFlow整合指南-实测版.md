# ADS MCP 对接 DeerFlow 整合指南（更新版）

> **WING**
> **初稿：2026-04-17**
> **实际验证：2026-04-20**

---

## 一、ADS MCP 深度分析报告

### 1.1 技术架构概览

```
DeerFlow (MCP Client)
        │
        │ stdio / Node.js 子进程
        ▼
ADS MCP Server (TypeScript)
        │
        │ HTTP + AES-128-ECB 解密
        ▼
ADS Server (Spring Boot)
        │
        │ MySQL / ClickHouse
        ▼
ADS 云桌面业务数据
```

### 1.2 ADS MCP 项目结构

```
ds2server/ds2server/ads-agent/mcp/
├── src/
│   ├── index.ts                    ← MCP Server 主入口（StdioServerTransport）
│   ├── client/
│   │   └── AdsApiClient.ts        ← API 客户端（单例，AES-128-ECB 解密）
│   ├── errors/
│   │   ├── errors.ts              ← 错误码定义（11 种错误类型）
│   │   └── index.ts               ← 错误模块导出
│   ├── schema/                    ← Zod Schema 定义
│   └── tools/                     ← 47+ 工具实现
├── dist/                          ← TypeScript 编译产物
├── node_modules/                  ← 运行时依赖（关键！）
└── package.json
```

### 1.3 关键依赖

| 依赖包 | 版本 | 说明 |
|--------|------|------|
| `@modelcontextprotocol/sdk` | ^1.0.0 | MCP SDK，必须在 node_modules 中 |
| `zod` | ^3.x | 参数验证 |
| `typescript` | ^5.x | 类型编译 |

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

## 三、ADS MCP 对接 DeerFlow 配置方案

### 3.1 配置修改

**修改文件 1：`docker/docker-compose-dev.yaml`**

在 `langgraph` 和 `gateway` 服务的 volumes 中添加：

```yaml
langgraph:
  volumes:
    # ... existing volumes ...
    - C:/Users/wing/Documents/Wing/git/ds2server/ds2server/ads-agent/mcp:/app/ads-mcp:ro

gateway:
  volumes:
    # ... existing volumes ...
    - C:/Users/wing/Documents/Wing/git/ds2server/ds2server/ads-agent/mcp:/app/ads-mcp:ro
```

**⚠️ 关键点**：必须挂载**整个 MCP 目录**（包含 `node_modules`），而不是仅 `dist` 目录。因为 `dist/index.js` 依赖 `@modelcontextprotocol/sdk` npm 包。

**修改文件 2：`extensions_config.json`**

```json
{
  "mcpServers": {
    "ragflow": {
      "enabled": false,
      "type": "sse",
      "url": "http://host.docker.internal:9382/sse",
      "headers": {
        "Authorization": "Bearer $RAGFLOW_MCP_API_KEY"
      },
      "description": "RagFlow 企业知识库检索服务"
    },
    "ads": {
      "enabled": true,
      "type": "stdio",
      "command": "node",
      "args": ["/app/ads-mcp/dist/index.js"],
      "env": {
        "ADS_API_BASE_URL": "http://192.168.1.54"
      },
      "description": "ADS 云桌面全生命周期管理（终端/用户/镜像/策略/部门）"
    }
  },
  "skills": {}
}
```

### 3.2 环境变量

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `ADS_API_BASE_URL` | ADS Server 地址 | `http://127.0.0.1:80` |

---

## 四、部署架构

### 4.1 Docker 部署

```
┌─────────────────────────────────────────────────────────────┐
│                        Windows 宿主机                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                    DeerFlow Docker                      │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  │  │
│  │  │  Frontend   │  │   Gateway   │  │  LangGraph   │  │  │
│  │  │  (:3000)    │  │   (:8001)   │  │   (:2024)    │  │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘  │  │
│  │                            │                           │  │
│  │                            ▼                           │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │   ADS MCP Server (Node.js 子进程)              │  │  │
│  │  │   Volume: ADS-MCP-DIR → /app/ads-mcp          │  │  │
│  │  │   command: node /app/ads-mcp/dist/index.js   │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                             │                                 │
│                        host.docker.internal                   │
│                             │ HTTP (:80)                     │
│                             ▼                                 │
│                    ┌─────────────────┐                       │
│                    │   ADS Server    │                       │
│                    │  (192.168.1.54) │                       │
│                    └─────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、AI 开发参考文档

### 5.1 ADS MCP 工具速查

| 业务场景 | 推荐工具 | 调用示例 |
|----------|----------|----------|
| 获取终端列表 | `ads_client_list` | `ads_client_list({})` |
| 查询终端状态 | `ads_client_show` | `ads_client_show({ clientId: 86 })` |
| 批量开机 | `ads_client_start` | `ads_client_start({ clientIds: "86,87,88" })` |
| 批量关机 | `ads_client_shutdown` | `ads_client_shutdown({ clientIds: "86,87,88" })` |
| 重启终端 | `ads_client_reboot` | `ads_client_reboot({ clientId: 86 })` |
| 锁定终端 | `ads_client_lock` | `ads_client_lock({ clientId: 86 })` |
| 解锁终端 | `ads_client_unlock` | `ads_client_unlock({ clientId: 86 })` |
| 获取部门树 | `ads_dept_tree` | `ads_dept_tree({})` |
| 获取镜像列表 | `ads_image_list` | `ads_image_list({})` |
| 获取策略列表 | `ads_policy_list` | `ads_policy_list({})` |
| 系统状态 | `ads_system_status` | `ads_system_status({})` |
| 管理员登录 | `ads_auth_adminLogin` | `ads_auth_adminLogin({ name: "admin", pwd: "xxx" })` |

### 5.2 错误处理

```python
# 工具返回格式
{
  "content": [
    {
      "type": "text",
      "text": "{\"code\":0,\"message\":\"success\"}"  # JSON 字符串
    }
  ]
}

# 错误码
| code | 含义 |
|------|------|
| 0 | 成功 |
| RESOURCE_NOT_FOUND | 资源不存在 |
| VALIDATION_ERROR | 参数验证失败 |
| AUTH_ERROR | 认证失败 |
| NETWORK_ERROR | 网络错误 |
| CLIENT_OFFLINE | 终端离线 |
```

---

## 六、实际验证结果（2026-04-20）

### 6.1 验证日志

```
✅ Configured MCP server: ads
✅ ADS API Base URL: http://192.168.1.54
✅ ADS MCP Server started
✅ Successfully loaded 51 tool(s) from MCP servers
✅ Total tools loaded: 9, built-in tools: 2, MCP tools: 51
```

### 6.2 功能验证

通过 DeerFlow Web UI 发送 "请列出 ADS 终端列表"：

```
AI 思考过程：
1. 识别用户意图：列出 ADS 终端
2. 调用 ads_client_list 工具
3. 成功返回 3 个终端：
   - ID 86: Windows 7 x86, 状态: 运行中
   - ID 87: Windows 7 x86, 状态: 运行中
   - ID 88: Windows 7 x86, 状态: 运行中
```

### 6.3 关键发现

| 发现项 | 说明 |
|--------|------|
| **必须挂载整个目录** | ADS MCP 依赖 `@modelcontextprotocol/sdk` npm 包，必须挂载整个 MCP 目录（包含 node_modules），而不是仅 dist 目录 |
| **MCP 懒加载** | MCP 工具在 DeerFlow 中是懒加载的，只有在第一次请求时才会初始化 MCP 客户端 |
| **容器重建** | 修改 `docker-compose-dev.yaml` 后需要完全重建容器（`docker compose up -d`）才能使 volume 挂载生效 |
| **工具数量** | ADS MCP 提供 51 个 MCP Tools |

---

## 七、验证清单

### 7.1 环境验证
- [x] ADS MCP 目录存在（包含 node_modules）
- [x] ADS Server HTTP API 可达（http://192.168.1.54）
- [x] DeerFlow Docker 运行中

### 7.2 配置验证
- [x] `docker-compose-dev.yaml` 已添加 ADS MCP volume 挂载
- [x] `extensions_config.json` 已添加 ADS MCP 配置

### 7.3 功能验证
- [x] LangGraph 日志显示 `Configured MCP server: ads`
- [x] LangGraph 日志显示 `Successfully loaded 51 tool(s) from MCP servers`
- [x] `ads_client_list({})` 调用成功，返回 3 个终端

---

## 八、故障排查

### 问题 1：`Cannot find module '@modelcontextprotocol/sdk'`
**原因**：只挂载了 `dist` 目录，没有挂载 `node_modules`
**解决**：修改 volume 挂载为整个 MCP 目录

### 问题 2：修改 volume 后 ADS MCP 仍然找不到
**原因**：容器没有重建，volume 挂载未生效
**解决**：执行 `docker compose up -d` 完全重建容器

### 问题 3：MCP 工具加载后没有出现在 Agent 中
**原因**：MCP 工具是懒加载的，需要发送请求触发初始化
**解决**：在 DeerFlow Web UI 中发送一条消息

---

**WING**
**2026-04-17 初稿**
**2026-04-20 实际验证完成**
