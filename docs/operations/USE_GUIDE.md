# DeerFlow 部署使用指南

## 目录

- [1. 产物清单](#1-产物清单)
- [2. 服务器前置条件](#2-服务器前置条件)
- [3. 启动前的配置](#3-启动前的配置)
- [4. 启动服务](#4-启动服务)
- [5. 停止服务](#5-停止服务)
- [6. 查看运行状态](#6-查看运行状态)
- [7. 端口说明与访问](#7-端口说明与访问)
- [8. 数据采集](#8-数据采集)
- [9. MCP 工具](#9-mcp-工具)
- [10. 常见问题](#10-常见问题)

---

## 1. 产物清单

```
release/
├── README.md                      # 本指南
├── config.yaml                    # 主配置文件
├── config.example.yaml            # 配置模板
├── .env.example                   # 环境变量模板（部署后根据此文件创建 .env）
├── extensions_config.json         # MCP 服务器配置
├── extensions_config.example.json # MCP 配置模板
│
├── backend-bin/                   # 后端服务
│   └── deerflow-gateway/
│       └── deerflow-gateway       # 可执行文件（入口）
│
├── frontend/                      # 前端服务（standalone 自包含，无 node_modules）
│   └── .next/                     # 构建产物 + 运行时依赖
│       └── standalone/server.js   # 前端入口
│
├── scripts/                       # 工具脚本
│   ├── deerflow.sh                 # 服务管理（启动/停止）
│   ├── wait-for-port.sh           # 端口等待（供 deerflow.sh 调用）
│   └── wait-for-deeprag.sh        # DeepRAG 就绪检测（供 deerflow.sh 调用）
│
├── nginx/                         # Nginx 配置（放入 /etc/nginx/conf.d/ 即可用）
│   ├── server.conf
│   └── deeprag.conf
├── skills/                        # Agent Skills
├── mcp-agent-mcp/                 # ADS MCP（可选）
├── deepRag/                       # [新增] DeepRAG 知识库检索服务
│   ├── bin/deep-rag-backend/      # PyInstaller 二进制（入口）
│   ├── frontend/                  # 静态前端
│   ├── Knowledge-Base/            # 放置知识库文档
│   ├── Knowledge-Base-Chunks/     # 知识库向量索引（运行时生成）
│   ├── Knowledge-Base-File-Summary/ # 文件摘要（运行时生成）
│   └── .env.example               # 环境变量模板
│
└── data_collection_logs/          # 数据采集输出（运行时自动生成）
```

---

## 2. 服务器前置条件

开始前请确认服务器已安装以下软件：

| 依赖 | 用途 | 安装命令（Ubuntu/Debian） |
|------|------|--------------------------|
| **Node.js 18+** | 前端 standalone 运行 + ADS MCP | `curl -fsSL https://deb.nodesource.com/setup_20.x \| bash - && apt install -y nodejs` |
| **lsof** | deerflow.sh 端口检测 | `apt install -y lsof` |
| **curl** | deerflow.sh + wait-for-deeprag.sh 健康检查 | `apt install -y curl` |

> 后端为 PyInstaller 编译的 ELF 二进制，自带 Python 运行时，**服务器无需安装 Python/pnpm/uv**。
> DeepRAG 同样为 PyInstaller 编译的 ELF 二进制，**无需额外运行时依赖**。

---

## 3. 启动前的配置

### 3.1 创建 .env 文件

从模板复制并编辑：

```bash
cp .env.example .env
vi .env
```

至少需要配置一个模型的 API Key：

```bash
# DeepSeek API Key（默认模型，必须）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

其他可选 Key 参考 `.env.example` 中的注释。

### 3.2 检查 config.yaml

`config.yaml` 已配置好，确认关键字段：

```yaml
models:
  - name: deepseek-chat
    api_key: $DEEPSEEK_API_KEY   # 引用 .env 中的变量
    supports_thinking: true       # 启用 Pro / Ultra 模式

skills:
  path: ./skills                  # Skills 目录（相对路径）

data_collection:
  enabled: true
  output_dir: ./data_collection_logs
```

如需添加更多模型，在 `models` 段落后追加（格式参考 `config.example.yaml`）。

### 3.3 检查 MCP 配置

`extensions_config.json` 定义了 MCP 工具服务器：

```json
{
  "mcpServers": {
    "ads": {
      "enabled": true,
      "type": "stdio",
      "command": "node",
      "args": ["../mcp-agent-mcp/dist/index.js"],
      "description": "ADS云桌面管理系统"
    },
    "deeprag": {
      "enabled": true,
      "type": "http",
      "url": "http://127.0.0.1:86/mcp/",
      "description": "DeepRAG 知识库检索"
    }
  }
}
```

- **ADS MCP**：相对路径 `../mcp-agent-mcp/dist/index.js`，如路径不符则需修改
- **DeepRAG**：HTTP 连接本地 MCP 服务器（端口 86），由 deerflow.sh 自动管理

### 3.4 启动前清单

| 项目 | 必须 | 说明 |
|------|------|------|
| `release/.env.example` → 创建 `.env` | ✅ | 根据模板创建，填入 API Key |
| `release/config.yaml` | ✅ | 已自动配置 |
| `release/extensions_config.json` | ✅ | 已自动配置 |
| `release/backend-bin/deerflow-gateway/deerflow-gateway` | ✅ | 后端可执行文件 |
| `release/frontend/.next/` | ✅ | 前端构建 |
| `release/deepRag/bin/deep-rag-backend/deep-rag-backend` | ⚠️ | 如不存在则 --skip-deeprag 启动 |

---

## 4. 启动服务

> **推荐使用 `scripts/deerflow.sh` 管理服务**，无需手动分别启停前后端。

### 4.1 一键启动（推荐）

在 release 目录下执行：

```bash
cd /path/to/release/

# 启动（后台运行）
./scripts/deerflow.sh
```

启动后会自动等待 DeepRAG、Gateway、Frontend 全部就绪，输出以下信息即表示成功：

```
✓ DeepRAG 已就绪 (API: localhost:5172, MCP: localhost:8172)
✓ Gateway 已就绪 (localhost:8001)
✓ Frontend 已就绪 (localhost:3000)
```

日志文件：`logs/gateway.log`、`logs/frontend.log`、`logs/deeprag.log`

> DeepRAG 启动耗时约 30-60 秒（加载模型依赖）。如果不需要 DeepRAG，可用 `--skip-deeprag` 参数跳过。

### 4.2 分别启动（手动控制）

如需要分开启动以分别查看日志：

**启动后端：**

```bash
cd /path/to/release/
DEER_FLOW_CONFIG_PATH=$(pwd)/config.yaml ./backend-bin/deerflow-gateway/deerflow-gateway
```

启动成功日志：

```
INFO:     Started server process [3]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
[DataCollection] System installed via monkey-patch (agent only)
[DataCollection] System installed successfully at startup
```

**启动前端（新开终端）：**

```bash
cd /path/to/release/frontend
PORT=3000 node .next/standalone/server.js
```

启动成功日志：

```
▲ Next.js 16.1.7
✓ Ready in 131ms
- Local: http://localhost:3000
```

---

## 5. 停止服务

### 5.1 一键停止（推荐）

```bash
cd /path/to/release/
./scripts/deerflow.sh --stop
```

该命令会依次停止 DeepRAG、Gateway 和 Frontend。

### 5.2 手动停止

```bash
pkill -f "deerflow-gateway"     # 停止后端
pkill -f "server\.js"            # 停止前端（standalone 进程）

# 或按端口强制停止
kill -9 $(lsof -ti :8001) 2>/dev/null   # 后端
kill -9 $(lsof -ti :3000) 2>/dev/null   # 前端
```

---

## 6. 查看运行状态

```bash
# 进程检查
ps aux | grep -E "deerflow-gateway|next"

# 端口检查
lsof -i :8001 -i :3000 -i :5172 -i :8172

# 后端连通性测试
curl -s -o /dev/null -w "Backend: HTTP %{http_code}\n" http://localhost:8001/

# DeepRAG 连通性测试
curl -s -o /dev/null -w "DeepRAG API: HTTP %{http_code}\n" http://localhost:5172/api/health 2>/dev/null || echo "DeepRAG: 未运行"

# 前端连通性测试
curl -s -o /dev/null -w "Frontend: HTTP %{http_code}\n" http://localhost:3000/
```

后端返回 `HTTP 401`（需登录），前端返回 `HTTP 200`，表示服务正常。

---

## 7. 端口说明与访问

| 端口 | 服务 | 说明 |
|------|------|------|
| **8001** | Gateway API | 后端 REST API + Agent 运行时 |
| **3000** | Frontend | 前端 Web 页面 |
| **5172** | DeepRAG API | DeepRAG 知识库后端 API |
| **8172** | DeepRAG MCP | DeepRAG MCP Server（Streamable HTTP） |
| **2026** | Nginx | DeerFlow 反向代理 |
| **86** | Nginx | DeepRAG 反向代理（前端 + API + MCP 统一入口） |

### 访问入口

- **直接访问**：`http://服务器IP:3000/`
- **代理访问**（配置了 Nginx）：`http://服务器IP:2026/`

### Nginx 反向代理（可选）

如果服务器已有 Nginx，可将 release 中的 Nginx server 块配置挂载到系统 Nginx：

```bash
# 1. 确认系统 Nginx 已启用 conf.d
grep 'conf\.d' /etc/nginx/nginx.conf
# 应输出类似: include /etc/nginx/conf.d/*.conf;
# 如果没有，手动添加此行到 /etc/nginx/nginx.conf 的 http 块内

# 2. 复制 server 配置到 conf.d
cp /usr/xccloud/deerflow/nginx/server.conf /etc/nginx/conf.d/deerflow.conf

# 3. 重新加载配置
nginx -s reload
```

> **如果没有 Nginx 也不想装**：直接访问 `http://服务器IP:3000/` 即可，`server.conf` 只是提供一个可选的代理入口。

首次访问需完成管理员账户设置（`/setup` 页面）。

---

## 8. 数据采集

数据采集模块已集成在后端中，启动后自动运行。

### 配置

`config.yaml` 中：

```yaml
data_collection:
  enabled: true
  output_dir: ./data_collection_logs
```

### 输出目录

```
data_collection_logs/
├── daily/
│   └── train_data_20260508.jsonl
├── archive/
└── raw/
```

### 验证

后端启动日志包含以下内容即表示采集正常：

```
[DataCollection] System installed via monkey-patch (agent only)
[DataCollection] System installed successfully at startup
```

---

## 9. MCP 工具

MCP 工具由 Agent 在对话中自动调用，定义在 `extensions_config.json` 中。

### 验证工具可用性

需先通过 `/setup` 创建管理员账户，然后调用 API：

```bash
curl -X POST http://localhost:8001/api/langgraph/tools \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin_token>" \
  -d '{}'
```

响应中应包含 MCP 工具（如 `ads_*`、`deeprag_*` 等）。

---

## 10. 常见问题

### 10.1 前端访问返回 401

首次部署需设置管理员账户：访问 `http://服务器IP:3000/setup` 按引导创建。

### 10.2 Pro / Ultra 模式不可选

`config.yaml` 中模型缺少 `supports_thinking: true`：

```yaml
models:
  - name: deepseek-chat
    ...
    supports_thinking: true
```

### 10.3 ADS MCP 报 ENOENT

`extensions_config.json` 中 `args` 路径指向的目录不存在：

```json
"args": ["../mcp-agent-mcp/dist/index.js"]
```

请确保 `mcp-agent-mcp/` 在 release 同级，或修改路径。

### 10.4 后端启动报 "No config file found"

未设 `DEER_FLOW_CONFIG_PATH` 环境变量：

```bash
DEER_FLOW_CONFIG_PATH=/path/to/release/config.yaml \
  ./backend-bin/deerflow-gateway/deerflow-gateway
```

### 10.5 前端启动报 "Cannot find module"

standalone 模式出此错误说明 `.next/` 构建不完整。重新执行编译脚本或确认 `next.config.js` 中有 `output: "standalone"`。

### 10.6 数据采集日志报 "Flush failed"

检查 `config.yaml` 中 `output_dir` 路径是否存在且有写权限。

### 10.7 如何更新版本？

1. 在开发机上重新编译生成 `release/`
2. 上传新 `release/` 目录到服务器
3. 复制旧版 `release/.env` 到新版
4. 复制旧版 `release/config.yaml` 中的模型配置到新版（如需保留自定义模型）
5. 停旧服务，启新服务

### 10.8 DeepRAG 启动失败

检查以下路径是否存在：

```bash
ls -la release/deepRag/bin/deep-rag-backend/deep-rag-backend
```

日志排查：

```bash
tail -30 logs/deeprag.log
```

常见原因：
- DeepRAG 未打包进 release（缺少 `deepRag/bin/`），需重新执行 `build-release.sh`
- 端口 5172/8172 被占用，检查 `ss -tlnp "( sport = :5172 )"`
- 可用 `--skip-deeprag` 跳过 DeepRAG 启动，仅运行 DeerFlow

### 10.9 DeepRAG MCP 不可用

检查 `extensions_config.json` 中 deeprag URL：

```json
"url": "http://127.0.0.1:86/mcp/"
```

确认 nginx 86 端口配置已加载：

```bash
cp /usr/xccloud/deerflow/nginx/deeprag.conf /etc/nginx/conf.d/
nginx -s reload
```

确认 nginx 中 deeprag.conf 的 `/mcp/` proxy_pass 带 trailing slash：

```nginx
proxy_pass http://deeprag-mcp/;   # 必须有结尾斜杠
```
