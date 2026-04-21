# DeerFlow 运维与故障排查指南

## 概述

本文档包含 DeerFlow 生产/开发环境运行的运维知识和故障排查经验。

## 目录

- [Docker/WSL 内存管理](#dockerwsl-内存管理)
- [Frontend 内存问题](#frontend-内存问题)
- [502 Bad Gateway](#502-bad-gateway)
- [Docker 环境配置](#docker-环境配置)
- [维护命令](#维护命令)

---

## Docker/WSL 内存管理

### 问题：WSL 内存增长 → 黑屏

**症状**：
- `vmmemws` 进程占用大量内存
- Windows 变得无响应或黑屏
- 系统内存耗尽

**根因**：
- 反复执行 `docker compose up --build` 会累积旧 Docker 镜像和构建缓存
- 构建缓存可增长至 **65GB+**
- WSL2 不会自动将内存释放回 Windows

**预防**：

```bash
# 每周：轻量清理（删除停止的容器、未使用的网络、缓存）
docker system prune -f

# 每月：深度清理（删除所有未使用的镜像、容器、卷、缓存）
docker system prune -a --volumes -f

# 可选：通过 C:\Users\wing\.wslconfig 设置 WSL2 内存限制
# [wsl2]
# memory=4GB
# processors=4
# swap=2GB
```

**清理前状态**：
```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          16        4         35.55GB   28.21GB (79%)
Build Cache     128       0         30.24GB   21.44GB
Volumes         12        4         3.649GB   1.88GB (51%)
────────────────────────────────────────────────────
总计可回收：约 51GB+
```

---

## Frontend 内存问题

### 问题：Frontend 容器使用 2.9GB 内存

**症状**：
- `docker stats` 显示 frontend 容器使用 2.9GB（正常：200-500MB）
- 系统内存压力
- 可能触发 OOM killer

**根因**：
- `docker-compose.yaml` 未设置内存限制
- Dockerfile 未设置 `NODE_OPTIONS` 内存上限
- Node.js 默认允许无限制的堆内存增长

**已修复**：

1. `docker-compose.yaml` - 添加内存限制：
```yaml
services:
  frontend:
    mem_limit: 512m
    memswap_limit: 512m
```

2. `Dockerfile` - 添加 Node.js 内存上限：
```dockerfile
ENV NODE_OPTIONS="--max-old-space-size=384"
```

3. `next.config.js` - 禁用 source maps：
```javascript
productionBrowserSourceMaps: false,
```

4. `query-client-provider.tsx` - 配置 QueryClient 缓存：
```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      gcTime: 1000 * 60 * 3,      // 3 分钟
      staleTime: 1000 * 60,        // 1 分钟
      refetchOnWindowFocus: false,
    },
  },
});
```

**修复结果**：
```
MEM USAGE / LIMIT: 89.38MiB / 512MiB   17.46%
```

---

## 502 Bad Gateway

### 问题：Gateway/LangGraph 启动失败

**症状**：
```
IsADirectoryError: [Errno 21] Is a directory: '/app/backend/config.yaml'
RuntimeError: Failed to load configuration during gateway startup
```

**根因**：
`docker/.env` 文件中的路径配置错误。`DEER_FLOW_CONFIG_PATH` 等环境变量必须是**主机路径**，而不是容器内路径。

当 Docker 看到不存在的主机路径时，会在挂载点创建一个同名**目录**而不是文件。

**错误的 .env**：
```env
# 错误 - 这些是容器内路径，不是主机路径！
DEER_FLOW_HOME=/app/backend/.deer-flow
DEER_FLOW_CONFIG_PATH=/app/backend/config.yaml
```

**正确的 .env**：
```env
# 正确 - 这些是 Windows 主机路径
HOME=C:\Users\wing
BETTER_AUTH_SECRET=<你的密钥>
DEER_FLOW_CONFIG_PATH=C:\path\to\deer-flow\config.yaml
DEER_FLOW_EXTENSIONS_CONFIG_PATH=C:\path\to\deer-flow\extensions_config.json
DEER_FLOW_HOME=C:\path\to\deer-flow
DEER_FLOW_REPO_ROOT=C:\path\to\deer-flow
DEER_FLOW_DOCKER_SOCKET=/var/run/docker.sock
PORT=2026
```

**工作原理**：
1. Docker Compose 从 `.env` 读取主机路径
2. 通过 `volumes:` 将其映射到容器内路径
3. 示例：`${DEER_FLOW_CONFIG_PATH}:/app/backend/config.yaml:ro` 将主机文件映射到容器路径

---

## Docker 环境配置

### 文件结构

```
deer-flow/
├── docker/
│   ├── docker-compose.yaml    # 服务定义
│   └── .env                  # 环境变量（不要提交到 git！）
├── config.yaml               # 主应用配置
├── extensions_config.json     # MCP & skills 配置
└── backend/
    └── .deer-flow/          # 运行时数据（启动时创建）
```

### 必填环境变量 (.env)

| 变量 | 用途 | 示例 |
|----------|---------|---------|
| `HOME` | 用户主目录 | `C:\Users\wing` |
| `BETTER_AUTH_SECRET` | 认证密钥 | `your-secret-key` |
| `DEER_FLOW_CONFIG_PATH` | config.yaml 的主机路径 | `C:\path\to\config.yaml` |
| `DEER_FLOW_EXTENSIONS_CONFIG_PATH` | extensions config 的主机路径 | `C:\path\to\extensions_config.json` |
| `DEER_FLOW_HOME` | 项目根目录的主机路径 | `C:\path\to\deer-flow` |
| `DEER_FLOW_REPO_ROOT` | 同 DEER_FLOW_HOME | `C:\path\to\deer-flow` |
| `DEER_FLOW_DOCKER_SOCKET` | Docker socket（sandbox 模式） | `/var/run/docker.sock` |
| `PORT` | nginx 对外端口 | `2026` |

### 重要说明

1. **不要将 .env 提交到 git** - 包含密钥
2. **路径必须是绝对 Windows 路径** - Docker Compose 会解析
3. **反斜杠或正斜杠都可以** - Windows 上两者都有效

---

## 维护命令

### 启动/停止

```bash
# 启动所有服务（在 docker/ 目录）
cd deer-flow/docker
docker compose up -d

# 重建并启动
docker compose up -d --build

# 仅重建 frontend（仅前端变更时节省时间）
docker compose up -d --build frontend

# 停止所有服务
docker compose down
```

### 监控

```bash
# 检查容器状态
docker ps

# 检查容器资源使用
docker stats --no-stream

# 检查特定容器日志
docker logs deer-flow-gateway --tail 50
docker logs deer-flow-langgraph --tail 50
docker logs deer-flow-frontend --tail 50
```

### 清理

```bash
# 轻量清理 - 删除停止的容器、未使用的网络、缓存
docker system prune -f

# 深度清理 - 删除所有未使用的镜像、容器、卷、缓存
docker system prune -a --volumes -f

# 删除特定构建缓存
docker builder prune -a
```

### 故障排查

```bash
# 验证 .env 是否正确加载
docker compose config | Select-String DEER_FLOW

# 检查容器内存限制是否生效
docker inspect deer-flow-frontend --format '{{.HostConfig.Memory}}'
# 应返回：536870912（512MB 字节数）

# 检查配置文件是否存在于容器内
docker exec deer-flow-gateway ls -la /app/backend/config.yaml

# 重启特定服务
docker compose restart gateway
```

---

## 快速故障排查流程图

```
容器无法启动？
│
├─► 检查状态：docker ps
│   └─► 容器未运行？检查日志：docker logs <名称>
│
├─► 502 Bad Gateway？
│   ├─► 检查 gateway 日志：docker logs deer-flow-gateway
│   ├─► 检查 langgraph 日志：docker logs deer-flow-langgraph
│   └─► IsADirectoryError？修复 .env 路径（见上文）
│
├─► 内存问题？
│   ├─► 检查使用：docker stats --no-stream
│   ├─► 轻量清理：docker system prune -f
│   └─► 深度清理：docker system prune -a --volumes -f
│
└─► 配置未加载？
    ├─► 验证 .env 存在于 docker/ 目录
    ├─► 验证路径是主机路径（不是容器路径）
    └─► 重启：docker compose down && docker compose up -d
```

---

## 最佳实践

1. **不要重建所有内容**：仅前端变更时使用 `docker compose up -d --build frontend`
2. **定期清理**：每周运行 `docker system prune -f`
3. **监控内存**：偶尔运行 `docker stats` 检查异常
4. **不要提交 .env**：包含敏感密钥
5. **先检查日志**：大多数问题在容器日志中可见
6. **先尝试重启**：许多问题可通过 `docker compose down && docker compose up -d` 解决
