# env_bootstrap — 启动时自动探测环境变量

## 功能说明

DeerFlow 启动时自动探测并注入以下环境变量到 `.env` 文件和当前进程：

| 变量 | 默认值 | 探测方式 |
|------|--------|---------|
| `DEER_FLOW_PROJECT_ROOT` | 项目根目录绝对路径（不再写入 .env，仅内部缓存供 ADS_MCP_CONFIG_PATH resolver 使用） | `boot._resolve_project_root()` 统一使用 config.yaml 向上遍历；env_bootstrap 保留 `_internal/` 二次校正防御层 |
| `ADS_MCP_CONFIG_PATH` | `$DEER_FLOW_PROJECT_ROOT/mcp-agent-mcp/.mcp-server/config.json` | 基于 `DEER_FLOW_PROJECT_ROOT` 拼接（_BOOTSTRAP_VARS 中排序优先）。config 目录始终保持于项目根下 |
| `build_server_params` cwd 转发 | 自动注入 | monkey-patch `deerflow.mcp.client.build_server_params` |
| **extensions_config.json 路径绝对化** | 自动改写 | ADS MCP 的 `args[0]`、`env.ADS_CONFIG_PATH` 从相对路径改写为绝对路径，**删除不再需要的 `cwd` 字段**。写入前创建 `.bak` 备份，使用原子写入（temp file + rename）保证安全 |

## 写入策略

### 核心原则：只写 .env，不碰 os.environ

bootstrap 只写入 `.env` 文件，不操作 `os.environ`。进程环境变量由 DeerFlow 自身的
`load_dotenv()`（默认 `override=False`）从 `.env` 加载，config.yaml 中的 `${VAR}`
引用由 `resolve_env_variables()` 通过 `os.getenv()` 解析。

### 标准路径（ADS_MCP_CONFIG_PATH）

1. **os.environ 已有** → 跳过（用户显式设的值，永不覆盖）
2. **.env 文件已有** → 使用该值，不覆盖文件
3. **不存在** → 获取 `FileLock(.env.lock)` → 写入 `.env`

### DEER_FLOW_PROJECT_ROOT 已不再写入 .env

奥卡姆剃刀剪枝：`DEER_FLOW_PROJECT_ROOT` 仅作为内部缓存用于 `ADS_MCP_CONFIG_PATH` 的 resolver，不再写入 `.env` 文件。

之前将其写入 `.env` 是为了让 `extensions_config.json` 中的 `$DEER_FLOW_PROJECT_ROOT` 能被 `resolve_env_variables()` 解析。现在 ADS MCP 的路径已经在 `extensions_config.json` 中直接改写为绝对路径，这条链路已切断，不再需要。

## 文件结构

```
env_bootstrap/
├── __init__.py          # 空文件
├── bootstrap.py         # 核心逻辑：配置驱动变量注册表 + 幂等写入
├── startup.py           # 入口点 + _installed 守卫
├── README.md            # 本文档
```

## 配置驱动设计

新增自举变量只需在 `bootstrap.py` 中追加两行：

```python
_BOOTSTRAP_VARS.append(("NEW_VAR", "Description"))
_RESOLVER_NAMES["NEW_VAR"] = "_resolve_new_var"
```

## 故障排除

| 现象 | 原因 | 行为 |
|------|------|------|
| 变量未写入 .env | 已在 os.environ 或 .env 中存在 | 跳过写入（幂等） |
| 变量未写入 .env | .env 文件不存在或不可写 | 仅记录 INFO，不阻塞启动 |
| ADS_MCP_CONFIG_PATH 未设置 | DEER_FLOW_PROJECT_ROOT 未设置 | 跳过该变量，不阻塞启动 |
| DEER_FLOW_PROJECT_ROOT 未设置 | CWD 不在项目树中 / 找不到 config.yaml | 跳过该变量，不阻塞启动 |
| Frozen 模式 PROJECT_ROOT 解析为 `backend-bin/` 而非项目根 | PyInstaller --onedir 产物结构导致 `boot._resolve_project_root()` 可能返回二进制目录 | `boot._resolve_project_root()` 已直接通过 config.yaml 定位项目根；env_bootstrap 的 `_internal/` 检测仅在 boot 误判时作为防御层触发。修复后无此故障 |
| MCP 调用报 MODULE_NOT_FOUND（路径含 workspace） | extensions_config.json 中 ADS MCP 路径未被改写为绝对路径 | 检查启动日志是否有 `[EnvBootstrap] Rewrote extensions_config.json ADS paths:` |

## MCP cwd 转发

### 背景

`deerflow.mcp.client.build_server_params()` 在构造 stdio MCP 服务器的连接参数时，
只拷贝 Pydantic 模型的已声明字段（`command`、`args`、`env`），丢弃了 `model_extra`
中的 `cwd` 字段。这导致 MCP 子进程的 cwd 回退到线程工作区目录，而非
期望的项目根目录。

### 机制

`env_bootstrap` 在设置好环境变量后，通过 monkey-patch 包装 `build_server_params()`：
从 `McpServerConfig.model_extra` 读取 `cwd` 字段，注入到返回的参数字典中。

> **注意**：ADS MCP 现在已在 `extensions_config.json` 中使用绝对路径（且 `cwd` 字段已被删除），
> 因此 ADS MCP 不受此 patch 影响。patch 保留用于其他仍然使用 `cwd` 的 stdio MCP server。

### 适用范围

- **生效**：所有 `type: "stdio"` 的 MCP 服务器（ADS MCP 因使用了绝对路径而不受影响）
- **不生效**：`type: "sse"` / `"http"` 的远程 MCP 服务器（无本地 cwd）

### 失败时的行为

- `deerflow.mcp.client` 不可导入 → 静默跳过，MCP 工具回退到工作区 cwd
- `model_extra` 中无 `cwd` → 不注入，`tools.py` 回退到线程工作区目录
- `cwd` 为空字符串 → 跳过注入（与未配置行为一致）
