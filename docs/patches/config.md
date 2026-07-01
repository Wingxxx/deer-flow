# 配置补丁

## A9：`.env.example` — ADS 配置示例

**文件**: `.env.example`
**行号**: L62-L68
**风险**: ✅ 极低

新增 ADS 统一认证的环境变量示例：

```bash
# ── ADS 统一认证 ──────────────────────────────────────────
# ADS_BASE_URL=http://ads:8080
# ADS_MCP_CONFIG_PATH=/path/to/ads-mcp/config.json
```

---

## 验证命令

```bash
# === A9: .env.example ADS ===
grep -n "ADS_BASE_URL\|ADS_MCP" .env.example
```

---

## D5：`backend/pyproject.toml` — filelock + pyahocorasick 依赖

**文件**: `backend/pyproject.toml`
**风险**: 🟡 中（上游频繁修改此文件，16 个提交）

两项追加依赖：

```toml
    "pyahocorasick>=2.3.1",
    "filelock>=3.0.0",
```

**原因**:
- `pyahocorasick`: AC 自动机敏感词检测引擎，topic_guardrail 扩展依赖
- `filelock`: 并发写入保护，env_settings 扩展依赖（`.env` 文件并发安全）

---

## 验证命令

```bash
# === D5: pyproject.toml 依赖 ===
grep -c "filelock\|pyahocorasick" backend/pyproject.toml
# 应输出 2
```

---

## C1：`config.example.yaml` — 配置精简

**文件**: `config.example.yaml`
**风险**: 🟢 低（模板文件，不影响运行时行为）

**改动**: 从上游原版大幅精简（`+6/-28`），移除了不必要的示例配置项，保留本 Fork 需要的核心配置。

**原因**: 上游 config.example.yaml 包含大量与本 Fork 无关的示例（如原版认证方式、多租户配置等），精简后降低配置误导风险。

> ⚠️ **同步警告**: 上游 `v2.0.0` → `upstream/main` 对此文件做了 `+171/-2` 的恢复性修改（重新添加了大量配置示例），未来同步时需决定是否再次精简。

**验证命令**:
```bash
git diff v2.0.0-rc1..HEAD --stat -- config.example.yaml
# 应显示 deletions > insertions（已精简）
```
