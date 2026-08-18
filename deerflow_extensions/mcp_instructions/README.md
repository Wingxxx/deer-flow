# MCP Instructions

读取 MCP server 在 initialize 握手响应中声明的 `instructions`（如 mcp-agent-mcp 的 SERVER_INSTRUCTIONS），经双点 monkey-patch 注入 agent system prompt，让 LLM 遵循服务器声明的实体标识使用规则（如"口述可读标识、工具参数才是主键"）。

## 目录结构

```
mcp_instructions/
├── __init__.py                # 导出 install_mcp_instructions / get_registry
├── fetcher.py                 # async 并发握手抓取 per-server instructions
├── startup.py                 # registry + 渲染 + 双点 monkey-patch (Level 3)
├── tests/
│   └── test_mcp_instructions.py  # 21 个单元测试（容错/超时/并发上限/截断/幂等/风暴防护全覆盖）
└── README.md                  # 本文件
```

## 核心文件职责

| 文件 | 职责 |
|------|------|
| `fetcher.py` | `fetch_all_instructions()` — 并发握手（`asyncio.gather` + `Semaphore` 上限，stdio 子进程风暴防护），抓取侧即按 per-server limit 截断（registry 不驻留超大文本）；单 server `wait_for` 超时只包 `initialize()`，同一 task 内直接 await 清理防孤儿子进程（anyio cancel scope 要求 enter/exit 同 task，`asyncio.shield` 换 task 会 RuntimeError）；复用核心 `ExtensionsConfig` / `build_servers_config` / `get_initial_oauth_headers`（只 import 不修改） |
| `startup.py` | `install_mcp_instructions()` — 双点 patch：`tool_search.get_deferred_tools_prompt_section`（subagent lazy-import 路径）+ `prompt.get_deferred_tools_prompt_section`（lead/embedded client LOAD_GLOBAL 路径）；请求路径零同步 IO（后台线程刷新）；`_installed` 守卫 + wrapper marker 防叠层 |

## 使用方式

**自动注入（推荐）：** 通过 `deerflow_extensions/boot.py` 注册后，gateway 启动时自动 monkey-patch。无需任何配置即可工作。

**手动测试：**
```python
from deerflow_extensions.mcp_instructions import install_mcp_instructions
install_mcp_instructions()
```

**环境变量**（缺省即启用，不触碰核心 config 体系）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `MCP_INSTRUCTIONS_ENABLED` | `1` | `0` 一键停用 |
| `MCP_INSTRUCTIONS_HANDSHAKE_TIMEOUT` | `30` | 单 server 握手超时（秒），node 冷启动慢时调大 |
| `MCP_INSTRUCTIONS_PER_SERVER_LIMIT` | `2000` | 单 server instructions 截断（字符）；**抓取侧即截断**（registry 内存防护），渲染侧再截（第二道闸） |
| `MCP_INSTRUCTIONS_MAX_CONCURRENCY` | `4` | 同时握手/ spawn 的服务器数上限（stdio 服务器会拉起子进程，无上限 = 进程风暴） |
| `MCP_INSTRUCTIONS_TOTAL_BUDGET` | `8000` | 总注入预算（字符，含 header 开销） |
| `MCP_INSTRUCTIONS_REFRESH_COOLDOWN` | `300` | 刷新冷却（秒），失败同样推进冷却防风暴 |

## 依赖

- `langchain_mcp_adapters.sessions.create_session`（0.2.2；≥0.3 时扩展自动停用——上游已原生注入工具描述，避免双重注入）
- `deerflow.config.extensions_config.ExtensionsConfig` / `deerflow.mcp.client.build_servers_config` / `deerflow.mcp.oauth.get_initial_oauth_headers`（只 import 不修改）

## 侵入等级

**Level 3 (monkey-patch)** — 对标 `tool_output_enrichment` / `data_collection` 模式。核心源码零改动，仅运行时替换模块属性（LOAD_GLOBAL 调用时解析）。

## 部署注意事项

- **多 worker（gunicorn/uvicorn）**：每进程独立 registry 与独立握手（握手成本 × worker 数）。
- **PyInstaller frozen 部署**：boot 在 app.py 模块级执行；若 node 相对路径 `./mcp-agent-mcp/dist/index.js` 在部署 cwd 下 spawn 失败 → fetch 返回空 → 功能静默降级不 crash。
- **mcp_resilience**：若未来重启用（当前源码已删、boot 未注册），fetcher 与工具加载各自握手一次（双 spawn 成本）。
