# DeerFlow Docker 网络配置变更记录

> **WING** 2026-04-17

## 一、问题背景

Docker Desktop Windows 版存在宿主机与容器之间的网络隔离问题：
- 容器内无法直接通过 `localhost` 或 `127.0.0.1` 访问宿主机服务
- `host.docker.internal` 是 Docker Desktop 内置 DNS，指向宿主机 IP
- 但错误配置 `extra_hosts` 会覆盖这个内置解析，导致 `host.docker.internal` 失效

---

## 二、网络架构

```
宿主机（Windows）
  ├── IP: 192.168.1.139（局域网）
  ├── RagFlow API Server :9380
  ├── RagFlow MCP Server  :9382
  │
  ▼ host.docker.internal（Docker Desktop 内置 DNS）
Docker bridge 网络（deer-flow-dev_deer-flow-dev）
  ├── 网段: 192.168.200.0/24
  ├── 网关: 192.168.200.1
  ├── deer-flow-nginx     :2026（入口）
  ├── deer-flow-frontend  :3000
  ├── deer-flow-gateway   :8001
  └── deer-flow-langgraph :2024
```

---

## 三、关键修改

### 3.1 删除 extra_hosts 配置

**文件：** `deer-flow/docker/docker-compose-dev.yaml`

**问题：** 原配置中 `extra_hosts: host.docker.internal:host-gateway` 覆盖了 Docker Desktop 内置 DNS，导致 `host.docker.internal` 无法解析到宿主机 IP。

**修复：** 删除 gateway 服务和 langgraph 服务中的 `extra_hosts` 配置行，保持默认的 Docker 内置解析。

**改动位置：**
```yaml
# 修复前（gateway 服务）
extra_hosts:
  - "host.docker.internal:host-gateway"

# 修复后（删除这两行）
```

### 3.2 Docker 项目名隔离

**文件：** `deer-flow/docker/docker-compose-dev.yaml`

**问题：** 默认项目名 `deer-flow` 与 RagFlow 的 `docker_ragflow` 项目冲突，导致网络池重叠、容器互相影响。

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

**预防：** upstream 服务重启后，记得重启 nginx。

### 3.4 9p 文件系统缓存问题

**问题：** Docker Desktop 的 9p 文件系统挂载存在缓存 bug，宿主机上修改文件后，容器内可能仍看到旧状态。严重时 `config.yaml` 被识别为目录（`IsADirectoryError`）。

**症状：** `docker logs langgraph` 报 `IsADirectoryError: /app/config.yaml`。

**修复步骤：**
1. 从 `docker-compose-dev.yaml` 中移除 `../config.yaml:/app/config.yaml` 挂载
2. 重启 langgraph 容器（此时容器内无 config.yaml，使用内置默认值）
3. 恢复挂载（可能需要等 9p 缓存过期）
4. 再次重启 langgraph

### 3.5 provisioner 服务移除

**文件：** `deer-flow/docker/docker-compose-dev.yaml`

**问题：** provisioner 服务需要 Kubernetes kubeconfig，9p bug 导致 `/root/.kube/config` 被识别为目录，触发 `RuntimeError: Kubeconfig path is a directory` 崩溃循环。

**影响：** provisioner 仅用于沙箱 Pod 管理，移除后不影响 DeerFlow Agent 核心功能（对话、检索、工具调用）。

**修复：** 从 `docker-compose-dev.yaml` 中永久删除 provisioner 服务定义。

---

## 四、相关文件清单

| 文件 | 路径 | 说明 |
|------|------|------|
| docker-compose-dev.yaml | deer-flow/docker/ | 项目名改为 deer-flow-dev、移除 provisioner、修复 extra_hosts |
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
