# env_bootstrap — 启动时自动探测环境变量

## 功能说明

DeerFlow 启动时自动探测并注入以下环境变量到 `.env` 文件和当前进程：

| 变量 | 默认值 | 探测方式 |
|------|--------|---------|
| `DEER_FLOW_PROJECT_ROOT` | 项目根目录绝对路径 | 复用 `boot._resolve_project_root()`（支持 PyInstaller frozen / 开发环境） |
| `ADS_MCP_CONFIG_PATH` | `~/.config/deer-flow/ads-mcp.json` 展开后的绝对路径 | `os.path.expanduser()` |

## 写入策略（幂等）

1. **os.environ 已有** → 跳过（用户显式设的值，永不覆盖）
2. **.env 文件已有** → 同步到 os.environ，不覆盖文件
3. **都不存在** → 获取 `FileLock(.env.lock)` → 写入 `.env` + `os.environ.setdefault`

## 文件结构

```
env_bootstrap/
├── __init__.py          # 空文件
├── bootstrap.py         # 核心逻辑：配置驱动变量注册表 + 幂等写入
├── startup.py           # 入口点 + _installed 守卫
├── README.md            # 本文档
└── tests/
    ├── __init__.py
    └── test_bootstrap.py  # 10 项测试（路径探测 / 幂等 / 值保留 / 降级）
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
| 变量未写入 .env | .env 文件不存在或不可写 | 仅设 os.environ，记录 warning |
| ADS_MCP_CONFIG_PATH 未设置 | HOME 环境变量未设置 | 跳过该变量，不阻塞启动 |
| DEER_FLOW_PROJECT_ROOT 未设置 | CWD 不在项目树中 | 跳过该变量，不阻塞启动 |
