# Docker 配置补丁

## D2：`docker-compose-dev.yaml` — Volume 挂载 + PYTHONPATH

**文件**: `docker/docker-compose-dev.yaml`
**风险**: ✅ 低

### D2a — deerflow_extensions volume（行 134）

```yaml
      - ../deerflow_extensions:/app/deerflow_extensions
```

### D2b — training_logs volume（行 135）

```yaml
      - ../training_logs:/data/deerflow/training_logs
```

### D2c — PYTHONPATH（已由 entrypoint.sh 接管）

**状态**: ✅ 设计演进，无需在 docker-compose-dev.yaml 中维护。

原 D2c 补丁要求将 command 中 `PYTHONPATH=.` 改为 `PYTHONPATH=/app`。当前版本改为在 `deerflow_extensions/entrypoint.sh` 行 15 统一管理：

```bash
PYTHONPATH=/app:. python3 -c "from deerflow_extensions.boot import boot_all_extensions; boot_all_extensions()"
```

`docker-compose-dev.yaml` 中不再单独设置 PYTHONPATH，由 entrypoint 脚本统一接管。

> **文档维护**: 本补丁标记为"设计演进"，原 D2c 内容保留归档，后续维护关注 entrypoint.sh 中的 PYTHONPATH 设置。

---

## D3：`docker-compose.yaml`（生产环境）— Volume 挂载 + PYTHONPATH

**文件**: `docker/docker-compose.yaml`
**风险**: ✅ 低

### D3a — deerflow_extensions volume（行 83）

```yaml
      - ../deerflow_extensions:/app/deerflow_extensions
```

### D3b — training_logs volume

**状态**: ❌ 当前缺失，需在下次同步时补回。

```yaml
      - ../training_logs:/data/deerflow/training_logs
```

**原因**: 数据采集系统写入 `training_logs/` 目录，容器内需有对应卷挂载才能访问采集数据。

**修复**: 在 `deerflow_extensions` 卷挂载行下方追加此卷。

### D3c — PYTHONPATH（待修复）

**状态**: ❌ 当前仍为 `PYTHONPATH=.`，未改为 `/app`。

```bash
# 当前（未修改）：
command: sh -c "cd backend && PYTHONPATH=. uv run uvicorn ..."
```
应在下次同步时评估是否需要改为 `PYTHONPATH=/app`（与 entrypoint.sh 保持一致）。

---

## A4：`docker-compose-dev.yaml` — ADS 环境变量

**文件**: `docker/docker-compose-dev.yaml`
**风险**: ✅ 低

```yaml
      - ADS_BASE_URL=${ADS_BASE_URL:-http://ads:8080}
      - ADS_MCP_CONFIG_PATH=${ADS_MCP_CONFIG_PATH:-}
```

---

## 验证命令

```bash
# === D2a: volume deerflow_extensions ===
grep -n "deerflow_extensions" docker/docker-compose-dev.yaml

# === D2b: volume training_logs ===
grep -n "training_logs" docker/docker-compose-dev.yaml

# === D2c: PYTHONPATH ===
grep -n "PYTHONPATH" docker/docker-compose-dev.yaml

# === D3a: volume deerflow_extensions (prod) ===
grep -n "deerflow_extensions" docker/docker-compose.yaml

# === D3b: volume training_logs (prod) ===
grep -n "training_logs" docker/docker-compose.yaml

# === A4: docker-compose ADS_BASE_URL ===
grep -n "ADS_BASE_URL\|ADS_MCP" docker/docker-compose-dev.yaml
```
