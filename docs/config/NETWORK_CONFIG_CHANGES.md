# DeerFlow Docker 网络配置变更记录

> **WING** 2026-04-17

## 一、问题背景

Docker Desktop Windows 版存在宿主机与容器之间的网络隔离问题：
- 容器内无法直接通过 `localhost` 或 `127.0.0.1` 访问宿主机服务
- `host.docker.internal` 是 Docker Desktop 内置 DNS，指向宿主机 IP
- Linux 环境下可能需要 `extra_hosts` 显式映射

---

## 二、网络架构

```
宿主机（Windows）
  ├── RagFlow API Server :9380
  ├── RagFlow MCP Server  :9382
  │
  ▼ host.docker.internal（Docker Desktop 内置 DNS）
Docker bridge 网络（deer-flow-dev_deer-flow-dev）
  ├── 网段: 192.168.200.0/24
  ├── deer-flow-nginx     :2026（入口）
  ├── deer-flow-frontend  :3000
  ├── deer-flow-gateway   :8001
  └── deer-flow-langgraph :2024
```

---

## 三、关键修改

### 3.1 extra_hosts 配置（保留）

**文件：** `deer-flow/docker/docker-compose-dev.yaml`

**说明：** `extra_hosts: host.docker.internal:host-gateway` 已在 gateway 和 langgraph 服务中配置。
在 Windows Docker Desktop 环境下，`host.docker.internal` 由 Docker Desktop 内置提供，理论上不需要额外配置。
但如果 `host.docker.internal` 解析失败（Connection refused），可尝试删除这两行。

```yaml
# gateway 服务 / langgraph 服务
extra_hosts:
  # For Linux: map host.docker.internal to host gateway
  - "host.docker.internal:host-gateway"
```

### 3.2 Docker 项目名隔离

**文件：** `deer-flow/docker/docker-compose-dev.yaml`

**问题：** 默认项目名 `deer-flow` 与 RagFlow 的 `docker_ragflow` 项目冲突。

**修复：** 统一使用 `-p deer-flow-dev` 启动参数，与 RagFlow 完全隔离。

**启动命令：**
```bash
cd deer-flow/docker
$env:HOME = $env:USERPROFILE
docker compose -f docker/docker-compose-dev.yaml -p deer-flow-dev up -d
```

### 3.3 nginx DNS 缓存问题

**问题：** nginx 在启动时解析 upstream 服务名（gateway、langgraph）为 IP 并缓存。如果 upstream 容器重启导致 IP 变化，nginx 会报 `502 Bad Gateway: Connection refused`。

**症状：** 宿主机 `curl localhost:2026` 返回 502，但容器内部 `curl gateway:8001` 正常。

**修复：** 重启 nginx 刷新 DNS 解析：
```bash
docker compose -f docker/docker-compose-dev.yaml -p deer-flow-dev restart nginx
```

### 3.4 9p 文件系统缓存问题

**问题：** Docker Desktop 的 9p 文件系统挂载存在缓存 bug，宿主机上修改文件后，容器内可能仍看到旧状态。严重时 `config.yaml` 被识别为目录（`IsADirectoryError`）。

**症状：** `docker logs langgraph` 报 `IsADirectoryError: /app/config.yaml`。

**修复步骤：**
1. 从 `docker-compose-dev.yaml` 中移除 `../config.yaml:/app/config.yaml` 挂载
2. 重启 langgraph 容器
3. 恢复挂载
4. 再次重启 langgraph

### 3.5 provisioner 服务（已禁用）

**文件：** `deer-flow/docker/docker-compose-dev.yaml`

**原因：** Docker Desktop 9p bug 导致 `~/.kube/config` 被识别为目录，触发 `RuntimeError: Kubeconfig path is a directory` 崩溃循环。

**当前状态：** provisioner 服务已注释禁用（`# provisioner:`）。

**影响：** provisioner 仅在 `config.yaml` 配置 `provisioner_url: http://provisioner:8002` 时激活。
默认配置使用 `LocalContainerBackend`，禁用后对 DeerFlow Agent 核心功能无影响。

**重新启用：**
1. 取消 provisioner 服务注释
2. 在 nginx.conf 中添加 provisioner 路由
3. 在 `config.yaml` sandbox 部分添加 `provisioner_url: http://provisioner:8002`

---

## 四、相关文件清单

| 文件 | 路径 | 说明 |
|------|------|------|
| docker-compose-dev.yaml | deer-flow/docker/ | 项目名 deer-flow-dev、provisioner 已禁用 |
| .env | deer-flow/ | UV_INDEX_URL、APT_MIRROR、DEEPSEEK_API_KEY、RAGFLOW_MCP_API_KEY |

---

## 五、快速恢复命令

```bash
# 1. 启动 DeerFlow（项目名隔离）
cd deer-flow/docker
$env:HOME = $env:USERPROFILE
docker compose -f docker/docker-compose-dev.yaml -p deer-flow-dev up -d

# 2. 如遇 502，重启 nginx
docker compose -f docker/docker-compose-dev.yaml -p deer-flow-dev restart nginx

# 3. 验证 API
curl http://localhost:2026/api/models
curl http://localhost:2026/api/mcp/config
```

---

**WING**
**2026-04-17**
