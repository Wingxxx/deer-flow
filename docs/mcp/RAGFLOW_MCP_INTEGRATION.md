# DeerFlow 对接 RagFlow MCP 修改记录

> **WING** 2026-04-17

> **⚠️ 当前状态：** `enabled: false`（已停用，2026-04-17）
>
> 重新启用：将 `extensions_config.json` 中 `ragflow.enabled` 改为 `true`，然后：
> ```bash
> docker compose -f docker/docker-compose-dev.yaml -p deer-flow-dev restart langgraph gateway
> ```

## 一、对接架构

```
DeerFlow Agent (MCP Client)
        │
        │ SSE / http://host.docker.internal:9382/sse
        ▼
RagFlow MCP Server (:9382)
        │
        │ HTTP + Bearer Token
        ▼
RagFlow API Server (:9380)
        │
        │ 向量检索 / 文档解析
        ▼
Elasticsearch + MySQL + Redis
```

---

## 二、关键配置文件

### 2.1 extensions_config.json

**路径：** `deer-flow/extensions_config.json`

```json
{
  "mcpServers": {
    "ragflow": {
      "enabled": true,
      "type": "sse",
      "url": "http://host.docker.internal:9382/sse",
      "headers": {
        "Authorization": "Bearer $RAGFLOW_MCP_API_KEY"
      },
      "description": "RagFlow 企业知识库检索服务，支持跨数据集语义检索、分页、阈值过滤"
    }
  },
  "skills": {}
}
```

**说明：**
- `url` 使用 `host.docker.internal` 而非 `localhost`，因为 DeerFlow 运行在 Docker 容器内
- `$RAGFLOW_MCP_API_KEY` 是环境变量引用，由 `.env` 文件提供
- MCP 工具为懒加载，首次 Agent 对话时才初始化连接

### 2.2 .env 变量

**路径：** `deer-flow/.env`

```bash
# DeerFlow Frontend
DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://localhost:8001

# RagFlow MCP Server Configuration
RAGFLOW_MCP_API_KEY=ragflow-7CVSA7RY6fQx7A9tj68Iv4nLUtkCq6ITuivd9z-nHaU

# DeepSeek API Configuration
DEEPSEEK_API_KEY=sk-...

# PyPI Mirror for uv
UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
APT_MIRROR=mirrors.aliyun.com
```

### 2.3 docker/.env

**路径：** `deer-flow/docker/.env`

```bash
UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
APT_MIRROR=mirrors.aliyun.com
```

### 2.4 config.yaml（DeepSeek 模型激活）

**路径：** `deer-flow/config.yaml`

关键改动：取消 DeepSeek 模型注释，激活 V3 模型：

```yaml
models:
  - name: deepseek-v3
    display_name: DeepSeek V3 (Thinking)
    use: deerflow.models.patched_deepseek:PatchedChatDeepSeek
    model: deepseek-chat
    api_key: $DEEPSEEK_API_KEY
```

### 2.5 docker-compose-dev.yaml 挂载

**路径：** `deer-flow/docker/docker-compose-dev.yaml`

需要确保 `config.yaml` 和 `extensions_config.json` 正确挂载：

```yaml
# gateway 服务
- ../config.yaml:/app/config.yaml
- ../extensions_config.json:/app/extensions_config.json

# langgraph 服务
- ../config.yaml:/app/config.yaml
- ../extensions_config.json:/app/extensions_config.json
```

---

## 三、MCP 工具加载机制

### 3.1 懒加载

MCP 工具在 DeerFlow 中采用懒加载策略：
- `ExtensionsConfig.from_file()` 在 `get_mcp_tools()` 调用时才执行
- 首次 Agent 对话时触发 MCP Client 初始化
- 后续对话复用已缓存的工具实例

### 3.2 日志验证

**LangGraph 日志路径：** `/app/logs/langgraph.log`

**关键日志序列：**
```
INFO - MCP tools not initialized, performing lazy initialization...
INFO - Initializing MCP tools...
INFO - Configured MCP server: ragflow
INFO - Initializing MCP client with 1 server(s)
INFO - Successfully loaded 1 tool(s) from MCP servers
INFO - Total tools loaded: 9, built-in tools: 2, MCP tools: 1, ACP tools: 0
```

### 3.3 MCP 工具清单

加载成功后，Agent 可使用以下 RagFlow MCP 工具：

| 工具名 | 功能 | 主要参数 |
|--------|------|---------|
| `ragflow_retrieval` | 企业知识库语义检索 | `question`, `dataset_ids`, `page_size`, `score_threshold`, `keyword` |

---

## 四、验证方法

### 4.1 配置加载验证

```bash
# 验证 DeerFlow API
curl http://localhost:2026/api/models

# 验证 MCP 配置（关键）
curl http://localhost:2026/api/mcp/config
# 期望返回：ragflow enabled: true, url: http://host.docker.internal:9382/sse
```

### 4.2 Agent 对话验证

通过 API 直接测试 Agent 对话：

```python
import requests

resp = requests.post(
    "http://localhost:2026/api/threads/test-thread/runs/wait",
    json={
        "input": {"messages": [{"type": "human", "content": "请在知识库中检索'项目计划'的文档"}]},
        "config": {"configurable": {"model_name": "deepseek-v3"}},
        "if_not_exists": "create",
    },
    timeout=120,
)
print(resp.json())
```

**成功标志：**
- Agent reasoning 显示：`我需要使用 ragflow_retrieval 工具`
- LangGraph 日志出现：`Successfully loaded 1 tool(s) from MCP servers`

### 4.3 RagFlow API 直连验证

```bash
# 从 DeerFlow 容器内测试（验证网络路径）
docker exec deer-flow-langgraph curl -s http://host.docker.internal:9380/api/v1/datasets \
  -H "Authorization: Bearer ragflow-7CVSA7RY6fQx7A9tj68Iv4nLUtkCq6ITuivd9z-nHaU"
```

---

## 五、已知问题与解决方案

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| MCP 工具未加载 | `extensions_config.json` 未挂载到正确路径 | 检查 `docker-compose-dev.yaml` 中 `../extensions_config.json:/app/extensions_config.json` 挂载 |
| 502 Bad Gateway | nginx DNS 缓存失效 | `docker compose -p deer-flow-dev restart nginx` |
| RAGFLOW_MCP_API_KEY 未解析 | 环境变量未传递到容器 | 检查 `.env` 文件存在且 `env_file` 配置正确 |
| config.yaml IsADirectoryError | 9p 文件系统缓存 bug | 移除挂载 → 重启 → 恢复挂载 |
| host.docker.internal 连接失败 | extra_hosts 覆盖了内置 DNS | 删除 `extra_hosts: host.docker.internal:host-gateway` |

---

## 六、RagFlow 数据集信息

- **数据集 ID：** `4cd55376370d11f1b6d9657226bf0ae3`
- **数据集名称：** `1`
- **文档数：** 1
- **Chunk 数：** 61
- **状态：** `1`（可用）

---

**WING**
**2026-04-17**
