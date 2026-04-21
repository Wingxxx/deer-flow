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

## 八、故障排查（2026-04-21 新增）

### 问题 1：重启容器后 ADS MCP 识别不到

**症状**：DeerFlow 无法识别 ADS MCP 相关内容，LangGraph 日志中没有 `Configured MCP server: ads`。

**根本原因**：ADS MCP 源码目录缺少 `dist/` 和 `node_modules/`（未执行 `npm run build`），容器挂载的是空目录。

**排查命令**：
```bash
# 检查 dist/ 是否存在
ls "C:/Users/wing/Documents/Wing/git/ds2server/ds2server/ads-agent/mcp/dist/"

# 检查 node_modules/ 是否存在
ls "C:/Users/wing/Documents/Wing/git/ds2server/ds2server/ads-agent/mcp/node_modules/"
```

**解决方案**：
```bash
cd "C:/Users/wing/Documents/Wing/git/ds2server/ds2server/ads-agent/mcp"
npm install
npm run build
# 验证
ls dist/index.js
```

### 问题 2：`Errno 30 Read-only file system` 无法切换 ADS MCP 开关

**症状**：在 DeerFlow Web UI 中尝试关闭/开启 ADS MCP 开关时报错：
```
Failed to update MCP configuration: [Errno 30] Read-only file system: '/app/backend/extensions_config.json'
```

**根本原因**：**两层问题叠加**。

#### 第一层：环境变量路径问题

`docker/.env` 中的 `DEER_FLOW_EXTENSIONS_CONFIG_PATH` 设置为 Windows 主机路径：
```env
DEER_FLOW_EXTENSIONS_CONFIG_PATH=C:\Users\wing\Documents\Wing\emto\2026\2026.3\DeerFlow\deer-flow\extensions_config.json
```

这个 Windows 路径在容器内不存在，导致 `resolve_config_path()` 抛出 `FileNotFoundError`。

#### 第二层：异常掩盖问题

`update_mcp_configuration()` 的 `except Exception` 捕获了 `FileNotFoundError`，然后代码尝试 fallback 到 `/app/extensions_config.json` 写入，但由于某些原因写失败，OS 返回 `Errno 30`（只读错误）。

**解决方案**：在 `docker-compose-dev.yaml` 中显式设置 `DEER_FLOW_EXTENSIONS_CONFIG_PATH` 为容器内路径，**覆盖** `.env` 中的 Windows 路径：

```yaml
gateway:
  environment:
    - DEER_FLOW_EXTENSIONS_CONFIG_PATH=/app/extensions_config.json
  env_file:
    - ../.env  # .env 中的 Windows 路径会被上面的环境变量覆盖

langgraph:
  environment:
    - DEER_FLOW_EXTENSIONS_CONFIG_PATH=/app/extensions_config.json
  env_file:
    - ../.env
```

**关键理解**：
- `env_file` 加载变量后，`environment` 中的同名变量会**覆盖** `env_file` 中的值
- 设置为容器内路径 `/app/extensions_config.json`（已通过 volume 挂载为可读写）

### 问题 3：ADS MCP 工具加载后没有出现在 Agent 中

**原因**：MCP 工具是懒加载的，需要发送请求触发初始化。

**解决**：在 DeerFlow Web UI 中发送一条消息。

---

### 旧故障排查（保留参考）

### 旧问题 1：`Cannot find module '@modelcontextprotocol/sdk'`
**原因**：只挂载了 `dist` 目录，没有挂载 `node_modules`
**解决**：修改 volume 挂载为整个 MCP 目录

### 旧问题 2：修改 volume 后 ADS MCP 仍然找不到
**原因**：容器没有重建，volume 挂载未生效
**解决**：执行 `docker compose up -d` 完全重建容器

---

## 九、ADS MCP 维护清单

### 每次修改配置后
- [ ] 确认 ADS MCP `dist/` 和 `node_modules/` 存在
- [ ] 重建容器：`docker compose -f docker-compose-dev.yaml down && docker compose -f docker-compose-dev.yaml up -d`
- [ ] 验证日志：`docker logs deer-flow-langgraph --tail 30 | grep ads`

### 每次 ADS MCP 升级后
- [ ] 在 ADS MCP 源码目录执行 `npm run build`
- [ ] 重建 DeerFlow 容器

### 部署前检查
- [ ] 确认 `docker-compose-dev.yaml` 中 `DEER_FLOW_EXTENSIONS_CONFIG_PATH=/app/extensions_config.json` 已设置
- [ ] 确认 ADS Server 地址可达（`curl http://192.168.1.54`）

---

## 十、ADS MCP 两层配置陷阱（2026-04-21 新增）

### 核心问题：ADS MCP 有独立的内部配置文件

ADS MCP Server 有**自己的配置文件**，会忽略 `extensions_config.json` 中的 `env.ADS_API_BASE_URL`。

| 配置文件 | 容器内路径 | 用途 | 谁读取 |
|----------|-----------|------|--------|
| `extensions_config.json` | `/app/extensions_config.json` | DeerFlow 启动 MCP Server 的配置 | DeerFlow (gateway/langgraph) |
| `ADS MCP 内部配置` | `/app/ads-mcp/.ads-mcp/config.json` | MCP Server 自己的 API 地址、凭证 | ADS MCP Server 本身 |

### 症状

修改了 `extensions_config.json` 中的 URL 后，ADS MCP 仍然连接旧地址。

### 诊断方法

```bash
# 检查 ADS MCP 内部配置的 URL
docker exec deer-flow-gateway cat /app/ads-mcp/.ads-mcp/config.json

# 如果显示 "url": "http://127.0.0.1:80" 说明未生效
```

### 完整解决方案

**第一步**：修改 `extensions_config.json`（DeerFlow 层配置）：
```json
{
  "mcpServers": {
    "ads": {
      "enabled": true,
      "type": "stdio",
      "command": "node",
      "args": ["/app/ads-mcp/dist/index.js"],
      "env": {
        "ADS_API_BASE_URL": "https://192.168.1.54"
      },
      "description": "ADS云桌面/广告派送系统..."
    }
  }
}
```

**第二步**：修改 ADS MCP 源目录的内部配置（Windows 源文件）：
```bash
notepad "C:\Users\wing\Documents\Wing\git\ds2server\ds2server\ads-agent\mcp\.ads-mcp\config.json"
```
将 `"url": "http://127.0.0.1:80"` 改为 `"url": "https://192.168.1.54"`

**第三步**：修改 `docker-compose-dev.yaml`（ADS MCP 挂载为可读写 + 启动时 sed 替换）：
```yaml
gateway:
  volumes:
    # ADS MCP 目录必须可读写（不能用 :ro）
    - C:/Users/wing/Documents/Wing/git/ds2server/ds2server/ads-agent/mcp:/app/ads-mcp
  command: sh -c "{ sed -i 's|http://127.0.0.1:80|https://192.168.1.54|g' /app/ads-mcp/.ads-mcp/config.json /app/ads-mcp/config.json && cd backend && ...; } > /app/logs/gateway.log 2>&1"
```

**注意**：`langgraph` 服务的 ADS MCP 挂载可以是 `:ro`（只读），因为 gateway 会先修改。

---

## 十一、docker-compose-dev.yaml 当前 frontend 配置（2026-04-21 生效）

```yaml
frontend:
  build:
    context: ../
    dockerfile: frontend/Dockerfile
    target: prod  # ✅ 使用 prod target（预编译产物）
    args:
      PNPM_STORE_PATH: ${PNPM_STORE_PATH:-/root/.local/share/pnpm/store}
      NPM_REGISTRY: ${NPM_REGISTRY:-}
  container_name: deer-flow-frontend
  command: sh -c "pnpm start > /app/logs/frontend.log 2>&1"
  working_dir: /app/frontend
  volumes:
    - ../frontend/src:/app/frontend/src
    - ../frontend/public:/app/frontend/public
    - ../frontend/next.config.js:/app/frontend/next.config.js:ro
    - ../logs:/app/logs
    - ${PNPM_STORE_PATH:-~/.local/share/pnpm/store}:/root/.local/share/pnpm/store
  environment:
    - NODE_ENV=development
    - WATCHPACK_POLLING=true
    - CI=true
    - DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://gateway:8001
    - DEER_FLOW_INTERNAL_LANGGRAPH_BASE_URL=http://langgraph:2024
  env_file:
    - ../.env  # ✅ 指向根目录 .env（包含 BETTER_AUTH_SECRET）
  networks:
    - deer-flow-dev
  mem_limit: 2g      # ✅ 2GB（dev server + 编译需要）
  memswap_limit: 2g
  restart: unless-stopped
```

---

**WING**
**2026-04-17 初稿**
**2026-04-20 实际验证完成**
**2026-04-21 问题修复：ADS MCP 两层配置 + Next.js SSR 挂死**
**2026-04-21 文档更新：完整配置生效**
