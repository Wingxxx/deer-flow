import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

import yaml
from dotenv import dotenv_values, find_dotenv, set_key
from fastapi import APIRouter, HTTPException, Request
from filelock import FileLock, Timeout
from httpx import AsyncClient, HTTPStatusError, TimeoutException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = ["router", "_CHANNEL_META", "_set_channel_enabled_in_config", "_get_config_path"]

_ENV_LOCK_PATH: str | None = None
router = APIRouter(prefix="/api/env-settings", tags=["env-settings"])


class ChannelInfo(BaseModel):
    id: str
    name: str
    enabled: bool = Field(default=False)
    running: bool = Field(default=False)
    credentials: dict[str, str] = Field(default={}, description="key → masked value")
    error: str = Field(default="")


class ChannelUpdateRequest(BaseModel):
    channel: str = Field(min_length=1)
    credentials: dict[str, str] = Field(default={}, description="key → plain-text value")


class ProviderInfo(BaseModel):
    id: str = Field(description="Provider identifier")
    name: str = Field(description="Provider display name")
    env_prefix: str = Field(default="", description="Environment variable prefix")
    deeprag_provider_id: str = Field(default="", description="DeepRAG provider identifier")
    deeprag_prefix: str = Field(default="", description="DeepRAG env prefix")
    default_base_url: str = Field(description="Default API base URL")
    default_models: list[str] = Field(description="Preset model list")
    key_exists: bool = Field(description="Whether API key is set")
    key_masked: str = Field(default="", description="Masked API key")
    base_url: str = Field(default="", description="Current base URL")
    model: str = Field(default="", description="Current model")
    deprecated_model: str | None = Field(default=None, description="Current model is deprecated")
    migration_hint: str | None = Field(default=None, description="Suggestion for migration")


class ProviderSettingsResponse(BaseModel):
    providers: dict[str, ProviderInfo] = Field(description="Map of provider ID to provider info")


class ProviderSettingsUpdateRequest(BaseModel):
    provider: str = Field(description="Provider identifier")
    api_key: str = Field(description="Plain-text API key", min_length=1)
    base_url: str | None = Field(default=None, description="Custom base URL")
    model: str = Field(description="Selected model", min_length=1)


class EnvSettingsUpdateResponse(BaseModel):
    success: bool = Field(default=True)
    message: str = Field(default="配置已保存")


class VerifyRequest(BaseModel):
    api_key: str | None = Field(default=None, description="API key to verify (uses saved key from .env if empty)")
    base_url: str | None = Field(default=None, description="Base URL to verify against (uses saved URL or default if empty)")


class VerifyResponse(BaseModel):
    valid: bool = Field(description="Whether the API key is valid")
    message: str = Field(description="Human-readable verification result")


class DeleteResponse(BaseModel):
    success: bool = Field(default=True)
    message: str = Field(default="配置已清除")


class ChannelVerifyRequest(BaseModel):
    credentials: dict[str, str] = Field(default={}, description="key → plain-text value")


class ChannelSettingsResponse(BaseModel):
    channels: dict[str, ChannelInfo]


# ── 延迟加载 providers.json ──────────────────────────────────────────────────

_providers_cache: dict | None = None
_providers_load_error: str | None = None


def _get_providers() -> dict:
    """延迟加载 providers.json，失败时返回空 dict 而非崩溃。

    所有使用 PROVIDERS 常量的函数改为调用此函数。
    """
    global _providers_cache, _providers_load_error
    if _providers_cache is not None:
        return _providers_cache
    if _providers_load_error is not None:
        return {}

    json_path = Path(__file__).parent / "providers.json"
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
            raw = data.get("providers", data)  # 兼容 {providers: [...]} 和 [...] 两种格式
            if isinstance(raw, list):
                _providers_cache = {p["id"]: p for p in raw}
            elif isinstance(raw, dict):
                _providers_cache = raw
            else:
                _providers_load_error = f"providers.json: 未知格式 (type={type(raw).__name__})"
                logger.error(_providers_load_error)
                return {}
        return _providers_cache
    except FileNotFoundError:
        _providers_load_error = f"providers.json 文件未找到: {json_path}"
        logger.error(_providers_load_error)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        _providers_load_error = f"providers.json 格式错误: {e}"
        logger.error(_providers_load_error)
    return {}


def _validate_provider_templates() -> None:
    """启动时校验所有 provider 都有对应的 config template。"""
    providers = _get_providers()
    missing = set(providers.keys()) - set(PROVIDER_CONFIG_TEMPLATE.keys())
    if missing:
        logger.warning(
            "providers.json 中厂商 %s 缺少 PROVIDER_CONFIG_TEMPLATE 条目，"
            "这些厂商将无法自动注册模型到 config.yaml", missing
        )


# ── 已停用模型名 → 迁移映射 ──────────────────────────────────────────────────
# 旧模型名已由厂商下线，用户 .env 中若仍使用这些旧名，API 调用将失败。
# GET API 返回 deprecated_model + migration_hint 供前端展示迁移提示。
DEPRECATED_MODEL_MAP: dict[str, str] = {
    "deepseek-chat": "deepseek-v4-pro",
    "deepseek-reasoner": "deepseek-v4-flash",
    "kimi-k2.5": "kimi-k3",
    "kimi-k2.5-thinking": "kimi-k3",
    "doubao-pro-32k-250315": "doubao-seed-2-1-pro-260628",
    "MiniMax-M2.5-highspeed": "MiniMax-M2.5",
    "glm-4-plus": "glm-4.7",
    "glm-4-air": "glm-4.5-air",
    "glm-4-flash": "glm-4.5",
    "Qwen/Qwen2.5-72B-Instruct-128K": "Pro/Qwen/Qwen3.5-397B-A17B",
    "deepseek-ai/DeepSeek-V3": "Pro/deepseek-ai/DeepSeek-V3.2",
}

# Each provider's config.yaml model entry template.
# Key: provider_id → (use class path, extra fields dict)
PROVIDER_CONFIG_TEMPLATE = {
    "deepseek":      {"use": "langchain_deepseek:ChatDeepSeek",                              "extra": {}},
    "moonshot":      {"use": "langchain_openai:ChatOpenAI",                                  "extra": {}},
    "volcengine":    {"use": "deerflow.models.patched_deepseek:PatchedChatDeepSeek",         "extra": {}},
    "dashscope":     {"use": "langchain_openai:ChatOpenAI",                                  "extra": {}},
    "minimax":       {"use": "langchain_openai:ChatOpenAI",                                  "extra": {}},
    "zhipuai":       {"use": "langchain_openai:ChatOpenAI",                                  "extra": {}},
    "siliconflow":   {"use": "langchain_openai:ChatOpenAI",                                  "extra": {}},
}


_CHANNEL_META: dict[str, dict] = {
    "wecom": {
        "name": "企业微信",
        "env_prefix": "WECOM",
        "credential_fields": [
            {"key": "bot_id", "label": "企业微信 Bot ID"},
            {"key": "bot_secret", "label": "企业微信 Bot Secret"},
        ],
    },
    "feishu": {
        "name": "飞书",
        "env_prefix": "FEISHU",
        "credential_fields": [
            {"key": "app_id", "label": "飞书 App ID"},
            {"key": "app_secret", "label": "飞书 App Secret"},
        ],
    },
    "dingtalk": {
        "name": "钉钉",
        "env_prefix": "DINGTALK",
        "credential_fields": [
            {"key": "client_id", "label": "钉钉 Client ID"},
            {"key": "client_secret", "label": "钉钉 Client Secret"},
        ],
    },
    "wechat": {
        "name": "微信",
        "env_prefix": "WECHAT",
        "credential_fields": [
            {"key": "bot_token", "label": "微信 Bot Token"},
        ],
    },
}


def _find_project_root(start_path: Path | None = None) -> Path | None:
    """通过向上遍历查找项目根目录。

    以 deepRag/ 子目录作为锚点（dev 部署下位于项目根下）。
    frozen 部署下 PyInstaller 会将 deepRag/ 打包进 _internal/，
    遍历时跳过 _internal 目录避免误判。
    回退：查找 config.yaml 或 backend/config.yaml。

    Args:
        start_path: 起始搜索路径，默认从 router.py 位置出发。
                    测试时可传入临时目录模拟 frozen 目录结构。
    """
    current = Path(os.path.abspath(start_path or Path(__file__).resolve())).parent
    frozen = getattr(sys, 'frozen', False)
    for _ in range(8):  # 8 级覆盖 frozen 最深嵌套 + 3 级余量
        # frozen 模式下，PyInstaller 将 deepRag/ 打包进 _internal/，
        # 跳过此目录避免将 _internal/ 误判为项目根
        if frozen and current.name == "_internal":
            current = current.parent
            continue
        if (current / "deepRag").is_dir():
            return current
        if (current / "config.yaml").is_file():
            return current
        if (current / "backend" / "config.yaml").is_file():
            return current  # Docker 场景：config 在 backend/ 子目录
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _get_config_path() -> str | None:
    """查找 config.yaml 文件路径（与 DeerFlow 优先级一致）。"""
    env_path = os.environ.get("DEER_FLOW_CONFIG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    # 向上遍历查找包含 config.yaml 的项目根
    project_root = _find_project_root()
    if project_root is not None:
        for candidate in ("config.yaml", "backend/config.yaml"):
            candidate_path = project_root / candidate
            if candidate_path.is_file():
                return str(candidate_path)
    # 回退（极端情况，保持向后兼容）
    for candidate in ("config.yaml", "backend/config.yaml"):
        candidate_path = os.path.join(os.path.dirname(__file__), "..", "..", candidate)
        if os.path.isfile(candidate_path):
            return os.path.normpath(candidate_path)
    return None


def _slugify(name: str) -> str:
    """将模型名转为 slug（小写字母数字和短横线）。空字符串回退到 hex。"""
    slug = re.sub(r"[^a-zA-Z0-9]", "-", name).lower()
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        slug = f"unnamed-{hashlib.md5(name.encode()).hexdigest()[:8]}"
    return slug


def _register_model_to_config(provider_id: str, model_name: str, base_url: str) -> str | None:
    """向 config.yaml 注册模型条目（替换语义：先清除同厂商旧条目再追加新条目）。返回注册的 name 或 None。"""
    config_path = _get_config_path()
    logger.info("_register_model_to_config: config_path=%s, provider_id=%s, model_name=%s, base_url=%s",
                 config_path, provider_id, model_name, base_url)
    if not config_path:
        logger.warning("config.yaml not found, skipping model registration")
        return None

    providers = _get_providers()
    meta = providers.get(provider_id)
    if not meta:
        logger.warning("Provider %s not found in providers.json, skipping model registration", provider_id)
        return None
    template = PROVIDER_CONFIG_TEMPLATE.get(provider_id)
    if not template:
        logger.warning("No config template for provider %s", provider_id)
        return None

    model_slug = _slugify(model_name)
    entry_name = f"{provider_id}-{model_slug}"
    prefix = f"{provider_id}-"

    with _get_config_lock(config_path):
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to read config.yaml: %s", e, exc_info=True)
            return None

        # 防御：config.yaml 结构异常时跳过模型注册，不阻断 Key 保存
        if not isinstance(cfg, dict):
            logger.warning("config.yaml 顶层结构异常（type=%s），跳过模型注册", type(cfg).__name__)
            return None
        models = cfg.get("models", [])
        if not isinstance(models, list):
            logger.warning("config.yaml models 不是列表（type=%s），跳过模型注册", type(models).__name__)
            return None
        logger.info("Current models in config.yaml: %d entries", len(models))

        # 替换语义：过滤掉同厂商所有旧条目
        filtered = [m for m in models if not (isinstance(m, dict) and isinstance(m.get("name"), str) and m.get("name").startswith(prefix))]

        # 构造新条目
        new_entry = {
            "name": entry_name,
            "display_name": f"{model_name} ({meta['name']})",
            "use": template["use"],
            "model": model_name,
            "api_key": f"${meta['env_prefix']}_API_KEY",
        }
        if base_url:
            new_entry["base_url"] = base_url
        new_entry.update(template["extra"])

        # 幂等优化：若新条目已存在且为同厂商唯一模型，跳过写入
        # (列表顺序敏感的比较 candidate == models 会因 filtered 打乱
        #  原顺序而导致伪阴性——不必要的 YAML 写入丢失注释)
        provider_entries = sum(
            1 for m in models
            if isinstance(m, dict)
            and isinstance(m.get("name"), str)
            and m.get("name").startswith(prefix)
        )
        if provider_entries == 1 and any(
            isinstance(m, dict) and m.get("name") == entry_name for m in models
        ):
            logger.info(
                "Model %s already in config.yaml (idempotent, no change), skipping write",
                entry_name,
            )
            return entry_name

        cfg["models"] = filtered + [new_entry]

        try:
            with open(config_path, "w") as f:
                yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info("Registered model %s to config.yaml (total models: %d, removed old: %d)",
                        entry_name, len(filtered) + 1, len(models) - len(filtered))
        except Exception as e:
            logger.error("Failed to write config.yaml: %s", e, exc_info=True)
            return None

    return entry_name


def _remove_models_from_config(provider_id: str) -> int:
    """从 config.yaml 删除该厂商注册的所有模型条目。返回删除数。"""
    config_path = _get_config_path()
    logger.info("_remove_models_from_config: config_path=%s, provider_id=%s", config_path, provider_id)
    if not config_path:
        logger.warning("config.yaml not found, cannot remove models")
        return 0

    prefix = f"{provider_id}-"

    with _get_config_lock(config_path):
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to read config.yaml for removal: %s", e, exc_info=True)
            return 0

        # 防御：config.yaml 结构异常时跳过模型移除，不阻断配置清除
        if not isinstance(cfg, dict):
            logger.warning("config.yaml 顶层结构异常（type=%s），跳过模型移除", type(cfg).__name__)
            return 0
        models = cfg.get("models", [])
        if not isinstance(models, list):
            logger.warning("config.yaml models 不是列表（type=%s），跳过模型移除", type(models).__name__)
            return 0
        before = len(models)
        logger.info("Before removal: %d models in config.yaml", before)
        models = [m for m in models if not (isinstance(m, dict) and isinstance(m.get("name"), str) and m.get("name").startswith(prefix))]
        removed = before - len(models)

        if removed == 0:
            logger.info("No models to remove for provider %s", provider_id)
            return 0

        cfg["models"] = models
        try:
            with open(config_path, "w") as f:
                yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info("Removed %d model(s) for %s from config.yaml (remaining: %d)", removed, provider_id, len(models))
        except Exception as e:
            logger.error("Failed to write config.yaml after removal: %s", e, exc_info=True)
            return 0

    return removed


def _get_env_path() -> Path:
    env_path = find_dotenv()
    if env_path:
        return Path(env_path)
    # 回退：哨兵定位项目根（frozen 部署下 cwd 无 .env 时兜底，写操作自动创建文件）
    project_root = _find_project_root()
    if project_root is not None:
        return project_root / ".env"
    raise FileNotFoundError(".env file not found in project tree")


def _get_env_lock() -> FileLock:
    lock_path = _ENV_LOCK_PATH or str(_get_env_path().with_suffix(".lock"))
    return FileLock(lock_path, timeout=5)


def _get_config_lock(config_path: str | None = None) -> FileLock:
    """config.yaml 写操作互斥锁。

    Args:
        config_path: 显式传入的 config.yaml 路径。若为 None 则内部调用
                     _get_config_path()（向后兼容无参调用场景）。
    """
    if config_path is None:
        config_path = _get_config_path()
    if not config_path:
        raise RuntimeError("config.yaml not found, cannot acquire lock")
    lock_path = Path(config_path).with_suffix(".config.lock")
    return FileLock(lock_path, timeout=5)


def _mask_value(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:3] + "****" + value[-4:]


def _read_env_value(key: str) -> str:
    try:
        env_path = _get_env_path()
        values = dotenv_values(env_path)
        return values.get(key, "")
    except FileNotFoundError:
        return ""


def _write_env_value(key: str, value: str) -> None:
    env_path = _get_env_path()
    set_key(str(env_path), key, value, quote_mode="always")
    os.environ[key] = value
    logger.info("Updated %s in .env file", key)


def _unset_env_value(key: str) -> None:
    env_path = _get_env_path()
    set_key(str(env_path), key, "", quote_mode="always")
    os.environ.pop(key, None)
    logger.info("Cleared %s from .env file", key)


# ── DeepRAG .env 同步 ─────────────────────────────────────────────────────


def _get_deeprag_env_path() -> Path:
    """解析 DeepRAG .env 文件路径。

    优先级:
    1. 环境变量 DEEPRAG_ENV_PATH
    2. 向上遍历查找包含 deepRag/ 的项目根
    3. 回退到硬编码路径（极端情况）
    """
    env_path = os.environ.get("DEEPRAG_ENV_PATH")
    if env_path:
        return Path(env_path)
    project_root = _find_project_root()
    if project_root is not None:
        return project_root / "deepRag" / ".env"
    logger.warning(
        "无法通过哨兵定位项目根目录，回退到硬编码路径。"
        "建议设置 DEEPRAG_ENV_PATH 环境变量。"
    )
    return Path(__file__).resolve().parents[2] / "deepRag" / ".env"


def _get_deeprag_env_lock() -> FileLock:
    """DeepRAG .env 独立文件锁（与 deer-flow 锁隔离）。"""
    lock_path = str(_get_deeprag_env_path().with_suffix(".lock"))
    return FileLock(lock_path, timeout=5)


def _sync_to_deeprag_env(provider_id: str, action: str) -> None:
    """将 DeerFlow 厂商环境变量同步写入 DeepRAG 的 .env 文件。

    Args:
        provider_id: 厂商标识（deepseek / moonshot / ...）
        action: "save" — 写入；"delete" — 清除
    """
    providers = _get_providers()
    if provider_id not in providers:
        return
    meta = providers[provider_id]
    # deer-flow .env 读取用 env_prefix，deepRag .env 写入用 deeprag_prefix
    env_prefix = meta["env_prefix"]
    deeprag_prefix = meta.get("deeprag_prefix", env_prefix)
    suffixes = ("API_KEY", "BASE_URL", "MODEL")

    try:
        deeprag_env_path = _get_deeprag_env_path()
        if action == "save":
            with _get_deeprag_env_lock():
                for suffix in suffixes:
                    deer_key = f"{env_prefix}_{suffix}"
                    deeprag_key = f"{deeprag_prefix}_{suffix}"
                    value = _read_env_value(deer_key)
                    # 回退：BASE_URL/MODEL 为空时使用 PROVIDERS 默认值
                    if not value:
                        if suffix == "BASE_URL":
                            value = meta.get("default_base_url", "")
                        elif suffix == "MODEL":
                            value = meta.get("default_models", [""])[0]
                    if value:
                        set_key(str(deeprag_env_path), deeprag_key, value, quote_mode="always")
                        logger.info("[DeepRAG] Wrote %s to %s", deeprag_key, deeprag_env_path)
        elif action == "delete":
            if not deeprag_env_path.is_file():
                logger.info("[DeepRAG] %s 不存在，跳过 delete 同步", deeprag_env_path)
                return
            with _get_deeprag_env_lock():
                for suffix in suffixes:
                    deeprag_key = f"{deeprag_prefix}_{suffix}"
                    set_key(str(deeprag_env_path), deeprag_key, "", quote_mode="always")
                    logger.info("[DeepRAG] Cleared %s from %s", deeprag_key, deeprag_env_path)
                # 若被删除的厂商是当前 DeepRAG 活跃厂商，清空 API_PROVIDER
                deeprag_values = dotenv_values(str(deeprag_env_path))
                deeprag_provider_id = meta.get("deeprag_provider_id", provider_id)
                if deeprag_values.get("API_PROVIDER") == deeprag_provider_id:
                    set_key(str(deeprag_env_path), "API_PROVIDER", "", quote_mode="always")
                    logger.info("[DeepRAG] Cleared API_PROVIDER from %s", deeprag_env_path)
        logger.info("[DeepRAG] Synced %s (%s) → %s", provider_id, action, deeprag_env_path)
    except FileNotFoundError:
        logger.warning("[DeepRAG] .env file not found at %s, skip sync for %s", _get_deeprag_env_path(), provider_id)
    except Exception as e:
        logger.warning("[DeepRAG] Sync failed for %s (%s): %s", provider_id, action, e)


def _get_deeprag_current_provider() -> str | None:
    """读取 DeepRAG 当前使用的厂商（API_PROVIDER 值）。"""
    try:
        values = dotenv_values(str(_get_deeprag_env_path()))
        provider = values.get("API_PROVIDER", "").strip()
        return provider if provider else None
    except Exception:
        return None


def _switch_deeprag_provider(provider_id: str) -> tuple[bool, str]:
    """手动切换 DeepRAG 当前使用的厂商。

    仅当 DeerFlow 中已配置该厂商 API Key 时才允许切换。
    同步写入 API_PROVIDER + 三项配置到 deepRag/.env。

    Returns:
        (success, message)
    """
    providers = _get_providers()
    if provider_id not in providers:
        return False, f"未知厂商: {provider_id}"

    meta = providers[provider_id]
    env_prefix = meta["env_prefix"]
    deeprag_provider_id = meta.get("deeprag_provider_id", provider_id)
    deeprag_prefix = meta.get("deeprag_prefix", env_prefix)

    # 校验 DeerFlow 中已配置该厂商的 API Key
    api_key = _read_env_value(f"{env_prefix}_API_KEY")
    if not api_key:
        return False, f"请先在 DeerFlow 中配置 {meta['name']} 的 API Key"

    try:
        deeprag_env_path = _get_deeprag_env_path()
        with _get_deeprag_env_lock():
            set_key(str(deeprag_env_path), "API_PROVIDER", deeprag_provider_id, quote_mode="always")
            suffixes = ("API_KEY", "BASE_URL", "MODEL")
            for suffix in suffixes:
                deer_key = f"{env_prefix}_{suffix}"
                deeprag_key = f"{deeprag_prefix}_{suffix}"
                value = _read_env_value(deer_key)
                if not value:
                    if suffix == "BASE_URL":
                        value = meta.get("default_base_url", "")
                    elif suffix == "MODEL":
                        value = meta.get("default_models", [""])[0]
                if value:
                    set_key(str(deeprag_env_path), deeprag_key, value, quote_mode="always")
        logger.info("[DeepRAG] Switched provider to %s", deeprag_provider_id)
        return True, f"DeepRAG 已切换至 {meta['name']}"
    except FileNotFoundError:
        return False, f"DeepRAG .env 文件不存在: {deeprag_env_path}"
    except Exception as e:
        logger.warning("[DeepRAG] Switch failed: %s", e)
        return False, f"切换失败: {e}"


def _validate_provider(provider_id: str) -> None:
    if provider_id not in _get_providers():
        raise HTTPException(status_code=404, detail=f"厂商 '{provider_id}' 不存在")


def _build_provider_info(provider_id: str, meta: dict) -> ProviderInfo:
    prefix = meta["env_prefix"]
    api_key = _read_env_value(f"{prefix}_API_KEY")
    base_url = _read_env_value(f"{prefix}_BASE_URL")
    model = _read_env_value(f"{prefix}_MODEL")
    exists = api_key != ""

    # 检测当前 model 是否已停用
    deprecated_model: str | None = None
    migration_hint: str | None = None
    if model and model in DEPRECATED_MODEL_MAP:
        deprecated_model = model
        migration_hint = (
            f"模型 '{model}' 已停用，建议更换为 '{DEPRECATED_MODEL_MAP[model]}'"
        )

    return ProviderInfo(
        id=provider_id,
        name=meta["name"],
        env_prefix=meta["env_prefix"],
        deeprag_provider_id=meta.get("deeprag_provider_id", provider_id),
        deeprag_prefix=meta.get("deeprag_prefix", meta["env_prefix"]),
        default_base_url=meta["default_base_url"],
        default_models=meta["default_models"],
        key_exists=exists,
        key_masked=_mask_value(api_key) if exists else "",
        base_url=base_url,
        model=model,
        deprecated_model=deprecated_model,
        migration_hint=migration_hint,
    )


def _build_channel_info(channel_id: str, meta: dict) -> ChannelInfo:
    prefix = meta["env_prefix"]
    credentials = {}
    for field in meta["credential_fields"]:
        key = field["key"]
        env_key = f"{prefix}_{key.upper()}"
        value = _read_env_value(env_key)
        credentials[key] = _mask_value(value) if value else ""

    enabled = False
    running = False
    try:
        from app.channels.service import get_channel_service
        service = get_channel_service()
        if service:
            status = service.get_status()
            ch = status["channels"].get(channel_id, {})
            enabled = ch.get("enabled", False)
            running = ch.get("running", False)
    except Exception:
        pass

    return ChannelInfo(
        id=channel_id,
        name=meta["name"],
        enabled=enabled,
        running=running,
        credentials=credentials,
    )


async def _test_wecom_connect(bot_id: str, bot_secret: str) -> tuple[bool, str]:
    try:
        from aibot import WSClient, WSClientOptions
        client = WSClient(WSClientOptions(bot_id=bot_id, secret=bot_secret))

        loop = asyncio.get_running_loop()
        auth_future = loop.create_future()

        def _on_authenticated():
            if not auth_future.done():
                auth_future.set_result(True)

        def _on_error(error: Exception):
            if not auth_future.done():
                auth_future.set_exception(error)

        client.on("authenticated", _on_authenticated)
        client.on("error", _on_error)

        await client.connect()

        try:
            await asyncio.wait_for(auth_future, timeout=10.0)
            return (True, "连接成功")
        except TimeoutError:
            return (False, "认证超时，请检查 Bot ID 和 Secret")
        finally:
            client.disconnect()
    except ImportError:
        return (False, "wecom-aibot-python-sdk 未安装")
    except Exception as e:
        logger.warning("WeCom connect test failed: %s", e)
        return (False, "连接失败，请检查 Bot ID 和 Secret 是否正确")


async def _test_feishu_connect(app_id: str, app_secret: str) -> tuple[bool, str]:
    try:
        import lark_oapi as lark

        client = lark.Client.builder().app_id(app_id).app_secret(app_secret).domain("https://open.feishu.cn").build()
        resp = await client.auth.v3.tenant_access_token.ainternal(
            lark.api.auth.v3.InternalTenantAccessTokenRequest.builder().build()
        )
        if resp.success():
            return (True, "连接成功")
        elif resp.msg and "invalid" in resp.msg.lower():
            return (False, "认证失败，请检查 App ID 和 App Secret 是否正确")
        else:
            logger.warning("Feishu connect test failed, resp.msg: %s", resp.msg)
            return (False, "认证失败，请检查 App ID 和 App Secret 是否正确")
    except ImportError:
        return (False, "lark-oapi 未安装")
    except Exception as e:
        logger.warning("Feishu connect test failed: %s", e)
        return (False, "连接失败，请检查 App ID 和 App Secret 是否正确")


async def _test_dingtalk_connect(client_id: str, client_secret: str) -> tuple[bool, str]:
    try:
        import dingtalk_stream  # noqa: F401
    except ImportError:
        return (False, "dingtalk-stream 未安装")

    try:
        async with AsyncClient(timeout=10) as http:
            resp = await http.get(
                "https://oapi.dingtalk.com/gettoken",
                params={"appkey": client_id, "appsecret": client_secret},
            )
            data = resp.json()
            if data.get("errcode") == 0 and data.get("access_token"):
                return (True, "连接成功")
            errmsg = data.get("errmsg", "未知错误")
            logger.warning("DingTalk connect test failed, errmsg: %s", errmsg)
            return (False, "认证失败，请检查 Client ID 和 Client Secret 是否正确")
    except Exception as e:
        logger.warning("DingTalk connect test failed: %s", e)
        return (False, "连接失败，请检查 Client ID 和 Client Secret 是否正确")


async def _test_wechat_connect(bot_token: str) -> tuple[bool, str]:
    token = bot_token.strip()
    if len(token) < 8:
        return (False, "Bot Token 长度不足，请检查配置")
    try:
        async with AsyncClient(timeout=10) as http:
            resp = await http.get(
                "https://ilinkai.weixin.qq.com/ilink/bot/get_bot_info",
                headers={
                    "Authorization": f"Bearer {token}",
                    "AuthorizationType": "ilink_bot_token",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("errcode", 0) != 0:
                errmsg = data.get("errmsg", "认证失败")
                logger.warning("WeChat connect test failed, errmsg: %s", errmsg)
                return (False, "认证失败，请检查 Bot Token 是否正确")
            return (True, "连接成功")
    except TimeoutException:
        return (False, "连接超时")
    except HTTPStatusError:
        return (False, "认证失败（HTTP 401），请检查 Bot Token")
    except Exception as e:
        logger.warning("WeChat connect test failed: %s", e)
        return (False, "连接失败，请检查 Bot Token 是否正确")


def _sanitize_channel_credentials(
    credentials: dict[str, str],
    credential_fields: list[dict],
) -> dict[str, str]:
    cleaned = {}
    for field in credential_fields:
        key = field["key"]
        raw = credentials.get(key, "")
        if isinstance(raw, str):
            raw = raw.strip()
        elif raw is not None:
            # 防御：非 str 值统一转字符串（防 _mask_value(len) TypeError 链）
            raw = str(raw).strip()
        if not raw:
            raise HTTPException(
                status_code=422,
                detail=f"'{field['label']}' 不能为空",
            )
        cleaned[key] = raw
    return cleaned


def _set_channel_enabled_in_config(channel_id: str, enabled: bool) -> bool:
    """在 config.yaml 中设置 channels.<channel_id>.enabled = true/false。

    如果 channels 区块或 channel 区块不存在则自动创建。
    - 启用渠道时：仅设置 enabled = true，凭据由 runtime-config.json 管理
    - 禁用渠道时：清理已有的凭据引用字段，避免 Gateway 启动时因
      $VAR 未设置而报错
    返回是否写入成功，失败时仅日志警告（不阻止主流程）。
    """
    config_path = _get_config_path()
    if not config_path:
        logger.warning("config.yaml not found, skip channel enabled toggle")
        return False

    with _get_config_lock(config_path):
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to read config.yaml: %s", e, exc_info=True)
            return False

        # 防御：config.yaml 结构异常时跳过渠道开关设置，不阻断主流程
        if not isinstance(cfg, dict):
            logger.warning("config.yaml 顶层结构异常（type=%s），跳过渠道开关设置", type(cfg).__name__)
            return False
        channels = cfg.setdefault("channels", {})
        if not isinstance(channels, dict):
            logger.warning("config.yaml channels 结构异常（type=%s），跳过渠道开关设置", type(channels).__name__)
            return False
        channel_cfg = channels.setdefault(channel_id, {})
        if not isinstance(channel_cfg, dict):
            logger.warning("config.yaml channels.%s 结构异常（type=%s），重置为空配置",
                           channel_id, type(channel_cfg).__name__)
            channel_cfg = {}
            channels[channel_id] = channel_cfg

        if channel_cfg.get("enabled") == enabled:
            changed = False
        else:
            channel_cfg["enabled"] = enabled
            changed = True

        # 禁用渠道时，清理已有的凭据引用字段以避免 Gateway 启动时
        # resolve_env_variables() 因 $VAR 未设置而报错。
        # 启用渠道时仅写 enabled = true（凭据由 runtime-config.json 管理）。
        meta = _CHANNEL_META.get(channel_id)
        if meta and not enabled:
            for field in meta["credential_fields"]:
                key = field["key"]
                if key in channel_cfg:
                    del channel_cfg[key]
                    changed = True

        if not changed:
            return True

        channels[channel_id] = channel_cfg
        cfg["channels"] = channels

        try:
            with open(config_path, "w") as f:
                yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info("[Audit] config.yaml channels.%s.enabled set to %s", channel_id, enabled)
        except Exception as e:
            logger.error("Failed to write config.yaml: %s", e, exc_info=True)
            return False

    return True


_RESTART_REASON_MAP: dict[str | None, str] = {
    None: "未知错误",
    "unknown_channel": "渠道配置丢失，请重新保存",
    "internal_error": "内部错误",
    "credential_invalid": "凭证校验失败",
    "network_timeout": "连接超时",
}


def _fmt_reason(reason: str | None) -> str:
    return _RESTART_REASON_MAP.get(reason, reason or "未知错误")


_channel_test_fns: dict[str, Callable] = {
    "wecom": _test_wecom_connect,
    "feishu": _test_feishu_connect,
    "dingtalk": _test_dingtalk_connect,
    "wechat": _test_wechat_connect,
}


def _get_test_fn(channel_id: str):
    fn = _channel_test_fns.get(channel_id)
    if fn is None:
        raise HTTPException(status_code=400, detail=f"渠道 '{channel_id}' 不支持连通性验证")
    return fn


@router.get(
    "/providers",
    response_model=ProviderSettingsResponse,
    summary="读取所有厂商环境变量设置",
    description="返回所有 AI 厂商的 API Keys 状态（值已掩码处理）",
)
async def get_provider_settings() -> ProviderSettingsResponse:
    providers = {}
    for provider_id, meta in _get_providers().items():
        providers[provider_id] = _build_provider_info(provider_id, meta)
    return ProviderSettingsResponse(providers=providers)


@router.put(
    "/providers",
    response_model=EnvSettingsUpdateResponse,
    summary="更新厂商环境变量",
    description="将指定厂商的 API Key / Base URL / Model 写入 .env，并在 config.yaml 中注册模型",
)
async def update_provider_settings(request: ProviderSettingsUpdateRequest) -> EnvSettingsUpdateResponse:
    _validate_provider(request.provider)
    providers = _get_providers()
    meta = providers[request.provider]
    prefix = meta["env_prefix"]
    key = request.api_key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="API Key 不能为空")
    try:
        with _get_env_lock():
            _write_env_value(f"{prefix}_API_KEY", key)
            base_url = request.base_url or meta["default_base_url"]
            if request.base_url is not None:
                _write_env_value(f"{prefix}_BASE_URL", request.base_url)
            model = request.model.strip()
            _write_env_value(f"{prefix}_MODEL", model)
        registered = _register_model_to_config(request.provider, model, base_url)
        _sync_to_deeprag_env(request.provider, "save")
        msg = f"{meta['name']} 配置已保存"
        if registered:
            msg += "，模型已注册到 config.yaml，刷新后可在聊天中使用"
        else:
            msg += "（config.yaml 未找到，仅保存 Key）"
        return EnvSettingsUpdateResponse(success=True, message=msg)
    except Exception as e:
        logger.error("Failed to save API Key: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存 API Key 失败: {str(e)}")


@router.delete(
    "/providers/{provider}",
    response_model=DeleteResponse,
    summary="清除厂商配置",
    description="从 .env 文件中删除指定厂商的 API_KEY、BASE_URL、MODEL 三个变量，并移除 config.yaml 中对应的模型条目",
)
async def delete_provider_settings(provider: str) -> DeleteResponse:
    _validate_provider(provider)
    providers = _get_providers()
    meta = providers[provider]
    prefix = meta["env_prefix"]
    try:
        removed = _remove_models_from_config(provider)
    except Timeout:
        logger.warning("[Audit] provider.%s.delete | config lock timeout, skipping model removal", provider)
        removed = 0
    except RuntimeError:
        logger.warning("[Audit] provider.%s.delete | config.yaml unavailable, skipping model removal", provider)
        removed = 0
    try:
        with _get_env_lock():
            _unset_env_value(f"{prefix}_API_KEY")
            _unset_env_value(f"{prefix}_BASE_URL")
            _unset_env_value(f"{prefix}_MODEL")
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.error("Failed to clear env for %s: %s", provider, e, exc_info=True)
    _sync_to_deeprag_env(provider, "delete")
    msg = f"已清除 {meta['name']} 的配置"
    if removed:
        msg += f"，已从聊天模型列表中移除 {removed} 个模型"
    return DeleteResponse(success=True, message=msg)


@router.post(
    "/providers/{provider}/verify",
    response_model=VerifyResponse,
    summary="验证厂商 API Key",
    description="通过向该厂商 API 发送测试请求验证 Key 连通性",
)
async def verify_provider_key(provider: str, request: VerifyRequest = None) -> VerifyResponse:
    _validate_provider(provider)
    providers = _get_providers()
    meta = providers[provider]
    prefix = meta["env_prefix"]
    api_key = request.api_key.strip() if request and request.api_key else _read_env_value(f"{prefix}_API_KEY")
    if not api_key:
        return VerifyResponse(valid=False, message="API Key 未配置")
    base_url = (request.base_url.strip() if request and request.base_url else None) or _read_env_value(f"{prefix}_BASE_URL") or meta["default_base_url"]
    verify_url = base_url.rstrip("/") + "/models"
    try:
        async with AsyncClient(timeout=10) as client:
            resp = await client.get(
                verify_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                return VerifyResponse(valid=True, message=f"{meta['name']} API Key 有效且可访问")
            elif resp.status_code == 401:
                return VerifyResponse(valid=False, message=f"{meta['name']} API Key 无效 (401)")
            elif resp.status_code == 403:
                return VerifyResponse(valid=False, message=f"{meta['name']} API Key 无权限 (403)")
            elif resp.status_code == 404:
                return VerifyResponse(valid=True, message=f"{meta['name']} API Key 格式正确（端点返回 404，密钥可能有效）")
            elif resp.status_code == 429:
                return VerifyResponse(valid=False, message=f"{meta['name']} API 请求过于频繁，请稍后重试")
            else:
                return VerifyResponse(valid=False, message=f"验证失败 (HTTP {resp.status_code})")
    except Exception as e:
        logger.error("Verify %s failed: %s", provider, e, exc_info=True)
        return VerifyResponse(valid=False, message=f"网络错误: {str(e)}")


# ── DeepRAG 厂商切换 ───────────────────────────────────────────────────────


@router.get(
    "/deeprag/current-provider",
    summary="获取 DeepRAG 当前厂商",
    description="返回 DeepRAG .env 中 API_PROVIDER 的值",
)
async def get_deeprag_current_provider() -> dict:
    provider = _get_deeprag_current_provider()
    return {"provider": provider}


@router.put(
    "/deeprag/switch-provider",
    summary="切换 DeepRAG 当前厂商",
    description="将 DeepRAG 的 API_PROVIDER 切换为指定厂商。要求 DeerFlow 中已配置该厂商的 API Key。",
)
async def switch_deeprag_provider(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体格式错误")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体格式错误")

    provider_id = (body.get("provider") or "").strip()
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider 字段不能为空")

    success, message = _switch_deeprag_provider(provider_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}


@router.get(
    "/channels",
    response_model=ChannelSettingsResponse,
    summary="读取所有渠道配置",
    description="返回所有 IM 渠道的凭据状态和运行状态（Key 已掩码处理）",
)
async def get_channels() -> ChannelSettingsResponse:
    channels = {}
    for channel_id, meta in _CHANNEL_META.items():
        channels[channel_id] = _build_channel_info(channel_id, meta)
    return ChannelSettingsResponse(channels=channels)


@router.put(
    "/channels",
    response_model=EnvSettingsUpdateResponse,
    summary="更新渠道凭据",
    description="保存渠道凭据到 .env，含值不变跳过 + 输入裁剪 + Test-Before-Switch 安全重启 + 审计日志",
)
async def update_channel_settings(request: ChannelUpdateRequest) -> EnvSettingsUpdateResponse:
    channel_id = request.channel
    if channel_id not in _CHANNEL_META:
        raise HTTPException(status_code=404, detail=f"渠道 '{channel_id}' 不存在")

    meta = _CHANNEL_META[channel_id]
    prefix = meta["env_prefix"]
    fields = meta["credential_fields"]

    # 输入裁剪
    cleaned = _sanitize_channel_credentials(request.credentials, fields)

    # 值不变跳过
    unchanged = True
    for field in fields:
        key = field["key"]
        env_key = f"{prefix}_{key.upper()}"
        existing = _read_env_value(env_key)
        if existing != cleaned.get(key, ""):
            unchanged = False
            break
    if unchanged:
        return EnvSettingsUpdateResponse(success=True, message="配置未变化，无需更新")

    try:
        with _get_env_lock():
            for field in fields:
                key = field["key"]
                env_key = f"{prefix}_{key.upper()}"
                _write_env_value(env_key, cleaned[key])

        # 审计日志
        masked_keys = {k: _mask_value(cleaned[k]) for k in cleaned}
        logger.info("[Audit] channel.%s.save | credentials=%s", channel_id, masked_keys)

        # Test-Before-Switch 安全重启
        msg = f"{meta['name']} 配置已保存"
        try:
            from app.channels.service import get_channel_service
            service = get_channel_service()
            if service and channel_id in service._config:
                channel_running = channel_id in service._channels and service._channels[channel_id].is_running

                if channel_running:
                    test_fn = _get_test_fn(channel_id)
                    ok, err = await test_fn(**cleaned)
                    if ok:
                        service._config[channel_id].update(cleaned)
                        ok, reason = await service.restart_channel(channel_id)
                        msg += "，渠道已自动重启" if ok else f"（新参数仍无法启动渠道：{_fmt_reason(reason)}）"
                    else:
                        msg += f"（新参数校验失败：{err}，旧渠道正常运行不受影响）"
                else:
                    service._config[channel_id].update(cleaned)
                    ok, reason = await service.restart_channel(channel_id)
                    msg += "，渠道已自动重启" if ok else f"（新参数仍无法启动渠道：{_fmt_reason(reason)}）"
            else:
                msg += "（ChannelService 未运行，重启 DeerFlow 后生效）"
        except HTTPException:
            raise
        except Exception as e:
            msg += "（渠道热重启失败，请手动重启）"
            logger.warning("[Audit] channel.%s.restart_failed | %s", channel_id, e)

        # 自动设置 config.yaml 中 channels.<channel_id>.enabled = true
        try:
            if _set_channel_enabled_in_config(channel_id, True):
                msg += "，已修改 config.yaml"
            else:
                msg += "（config.yaml 写入失败，如需开机自启请手动设置）"
        except Timeout:
            msg += "（config.yaml 写入超时，请稍后重试）"
        except RuntimeError:
            msg += "（config.yaml 不可用，开机自启设置未保存）"

        return EnvSettingsUpdateResponse(success=True, message=msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to save channel %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.delete(
    "/channels/{channel}",
    response_model=DeleteResponse,
    summary="清除渠道配置",
    description="清除渠道凭据，同步停止运行中的渠道，清理内存配置",
)
async def delete_channel_settings(channel: str) -> DeleteResponse:
    if channel not in _CHANNEL_META:
        raise HTTPException(status_code=404, detail=f"渠道 '{channel}' 不存在")

    meta = _CHANNEL_META[channel]
    prefix = meta["env_prefix"]
    fields = meta["credential_fields"]

    try:
        with _get_env_lock():
            for field in fields:
                env_key = f"{prefix}_{field['key'].upper()}"
                _unset_env_value(env_key)
    except FileNotFoundError:
        pass

    msg = f"已清除 {meta['name']} 的配置"

    try:
        from app.channels.service import get_channel_service
        service = get_channel_service()
        if service:
            if channel in service._channels:
                await service._channels[channel].stop()
                del service._channels[channel]
                msg += "，渠道已停止运行"
            if channel in service._config:
                for field in fields:
                    service._config[channel][field["key"]] = ""
    except Exception:
        pass

    logger.info("[Audit] channel.%s.delete", channel)

    try:
        _set_channel_enabled_in_config(channel, False)
        msg += "，已禁用开机自启"
    except Exception as e:
        logger.warning("[Audit] channel.%s.delete | config.yaml update failed: %s", channel, e)
        msg += ("（config.yaml 写入失败，如需禁用开机自启请手动设置"
                " channels.%s.enabled: false）" % channel)

    return DeleteResponse(success=True, message=msg)


@router.post(
    "/channels/{channel}/verify",
    response_model=VerifyResponse,
    summary="验证渠道连通性",
    description="通过 SDK 连接测试验证渠道凭据",
)
async def verify_channel_settings(channel: str, request: ChannelVerifyRequest = None) -> VerifyResponse:
    if channel not in _CHANNEL_META:
        raise HTTPException(status_code=404, detail=f"渠道 '{channel}' 不存在")

    meta = _CHANNEL_META[channel]
    prefix = meta["env_prefix"]
    fields = meta["credential_fields"]

    credentials = {}
    if request and request.credentials:
        credentials = request.credentials
    else:
        for field in fields:
            env_key = f"{prefix}_{field['key'].upper()}"
            credentials[field["key"]] = _read_env_value(env_key)

    has_all = all(credentials.get(f["key"]) for f in fields)
    if not has_all:
        return VerifyResponse(valid=False, message="凭据未完整配置")

    try:
        test_fn = _get_test_fn(channel)
    except HTTPException:
        return VerifyResponse(valid=False, message=f"渠道 '{channel}' 不支持连通性验证")

    valid, message = await test_fn(**credentials)
    result = "valid" if valid else "invalid"
    logger.info("[Audit] channel.%s.verify | result=%s", channel, result)
    return VerifyResponse(valid=valid, message=message)
