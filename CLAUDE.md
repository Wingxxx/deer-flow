# CLAUDE.md

本文件为 AI 编程助手（Claude Code、Codex、Cursor、Windsurf 等）提供 DeerFlow 项目指导。

## 项目概述

DeerFlow 是一个基于 LangGraph 的 AI Super Agent 系统，采用全栈架构：

- **Frontend** (Next.js 16, 端口 3000) → 通过 **Nginx** 反向代理 (端口 2026)
- **Gateway API** (FastAPI, 端口 8001) → REST API：模型、MCP、skills、内存、文件上传
- **LangGraph Server** (端口 2024) → Agent 运行时和工作流执行

详细架构说明见下方子模块文档。

## 子模块文档

```
@./backend/CLAUDE.md    # 后端：LangGraph agent 系统、harness/app 架构、middleware 链
@./frontend/CLAUDE.md    # 前端：Next.js 16、TanStack Query、thread hooks
@./docker/CLAUDE.md     # Docker：Compose 配置、环境变量
```

## 项目文档目录

详细文档位于 `docs/` 目录：

```
docs/
├── config/           # 配置相关文档
├── mcp/              # MCP 集成文档（ADS、RAGFlow 等）
├── changelog/        # 代码变更记录
├── operations/       # 运维与故障排查指南
├── plans/            # 技术方案计划
├── skills/           # Skill 相关文档
└── pr-evidence/      # PR 测试截图
```

| 文档 | 路径 | 说明 |
|------|------|------|
| 运维指南 | `@./docs/operations/OPERATIONS.md` | Docker/WSL 内存、502 故障排查 |
| ADS MCP 集成 | `@./docs/mcp/ADS-MCP对接DeerFlow整合指南-实测版.md` | ADS MCP 对接配置与验证 |
| 代码变更记录 | `@./docs/changelog/CODE_CHANGE_SUMMARY_BY_FILE.md` | 按文件分类的变更总结 |
| Skill 名称冲突修复 | `@./docs/skills/SKILL_NAME_CONFLICT_FIX.md` | Skill 名称冲突解决方案 |

## 常用命令

```bash
# Docker（在 deer-flow/docker 目录）
docker compose up -d              # 启动所有服务
docker compose up -d --build       # 重建并启动
docker compose up -d --build frontend  # 仅重建 frontend（节省时间）
docker compose down               # 停止所有服务
docker logs <容器名> --tail 50    # 查看日志
docker stats --no-stream           # 查看资源使用

# 后端（在 deer-flow/backend 目录）
make dev      # 运行 LangGraph Server (端口 2024)
make gateway  # 运行 Gateway API (端口 8001)
make test     # 运行测试

# 前端（在 deer-flow/frontend 目录）
pnpm dev     # 开发服务器 (端口 3000)
pnpm build   # 生产构建
pnpm check   # Lint + 类型检查
```

## Docker/WSL 运维与故障排查

### WSL 内存增长 → 黑屏

**症状**：`vmmemws`（WSL2）占用大量内存，系统变得无响应或黑屏。

**根因**：
- 反复执行 `docker compose up --build` 会累积旧镜像和构建缓存
- 构建缓存可增长至 **65GB+**
- WSL2 不会自动将内存释放给 Windows

**预防**：
```bash
# 每周：轻量清理（删除停止的容器、未使用的网络、缓存）
docker system prune -f

# 每月：深度清理（删除所有未使用的镜像、容器、卷、缓存）
docker system prune -a --volumes -f

# 可选：通过 C:\Users\wing\.wslconfig 设置 WSL2 内存限制：
# [wsl2]
# memory=4GB
# processors=4
# swap=2GB
```

### Frontend 容器内存：2.9GB（正常：200-500MB）

**根因**：`docker-compose.yaml` 未设置 `mem_limit`，Dockerfile 未设置 `NODE_OPTIONS` 内存限制。

**已修复**：
- `docker-compose.yaml`：`mem_limit: 512m`
- `Dockerfile`：`ENV NODE_OPTIONS="--max-old-space-size=384"`

验证命令：
```bash
docker inspect deer-flow-frontend --format '{{.HostConfig.Memory}}'
# 应显示：536870912（512MB 字节数）
```

### 502 Bad Gateway / IsADirectoryError

**症状**：Gateway 或 LangGraph 启动失败：
```
IsADirectoryError: [Errno 21] Is a directory: '/app/backend/config.yaml'
RuntimeError: Failed to load configuration during gateway startup
```

**根因**：`docker/.env` 中的路径配置错误。`DEER_FLOW_CONFIG_PATH` 等环境变量必须是**主机路径**（Windows 路径），而不是容器内路径。Docker 会将主机路径当作文件挂载，如果路径不存在则创建同名**目录**。

**正确的 .env 配置**（docker/.env）：
```env
HOME=C:\Users\wing
BETTER_AUTH_SECRET=<你的密钥>
DEER_FLOW_CONFIG_PATH=C:\path\to\deer-flow\config.yaml
DEER_FLOW_EXTENSIONS_CONFIG_PATH=C:\path\to\deer-flow\extensions_config.json
DEER_FLOW_HOME=C:\path\to\deer-flow
DEER_FLOW_REPO_ROOT=C:\path\to\deer-flow
DEER_FLOW_DOCKER_SOCKET=/var/run/docker.sock
PORT=2026
```

**注意**：Docker Compose 会自动将这些主机路径映射到 docker-compose.yaml volumes 中定义的容器内路径。

## 故障排查清单

1. **检查容器状态**：
   ```bash
   docker ps
   ```

2. **检查容器日志**：
   ```bash
   docker logs deer-flow-gateway --tail 50
   docker logs deer-flow-langgraph --tail 50
   docker logs deer-flow-frontend --tail 50
   ```

3. **检查内存使用**：
   ```bash
   docker stats --no-stream
   ```

4. **重启服务**：
   ```bash
   docker compose down
   docker compose up -d
   ```

5. **深度清理**（内存/磁盘问题时）：
   ```bash
   docker system prune -a --volumes -f
   ```

## 重要开发准则

### 文档更新策略
**重要：代码变更后必须更新相关文档**

变更时：
- 用户面向变更更新 `README.md`（功能、设置、使用说明）
- 开发面向变更更新子模块的 `CLAUDE.md`（架构、命令、工作流）
- 保持文档与代码同步

### 测试驱动开发
每个功能或 bug 修复必须有单元测试。提交前运行 `make test`（后端）或 `pnpm test`（前端）。
