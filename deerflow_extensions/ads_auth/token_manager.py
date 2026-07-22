import json
import logging
import os
import tempfile

from deerflow_extensions.ads_auth.config import ADS_BASE_URL, get_mcp_config_path

_logger = logging.getLogger(__name__)

_ads_tokens: dict[str, str] = {}


async def save_token(user_id: str, token: str):
    _ads_tokens[user_id] = token


async def get_token(user_id: str) -> str | None:
    return _ads_tokens.get(user_id)


async def remove_token(user_id: str):
    _ads_tokens.pop(user_id, None)


async def sync_to_mcp_config(username: str, password: str) -> bool:
    """同步 ADS URL 和凭据到 MCP config.json。返回 True 表示成功。"""
    config_path = get_mcp_config_path()

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        _logger.warning("[ADS sync] config.json not found at %s", config_path)
        return False
    except json.JSONDecodeError:
        _logger.warning("[ADS sync] config.json at %s is invalid JSON", config_path)
        return False
    except (PermissionError, OSError) as e:
        _logger.warning("[ADS sync] Cannot read config.json at %s: %s", config_path, e)
        return False

    if not isinstance(config, dict):
        _logger.warning(
            "[ADS sync] config.json is not a dict (type=%s)", type(config).__name__
        )
        return False

    # 安全创建嵌套结构
    config.setdefault("ads", {})
    if not isinstance(config["ads"], dict):
        _logger.warning("[ADS sync] config.json 'ads' key is not a dict")
        return False
    config["ads"].setdefault("server", {})
    # credentials 可能不是 dict（如字符串），需要覆盖
    if not isinstance(config["ads"].get("credentials"), dict):
        config["ads"]["credentials"] = {}
    config["ads"]["credentials"].setdefault("new", {})

    config["ads"]["server"]["url"] = ADS_BASE_URL
    config["ads"]["credentials"]["new"]["username"] = username
    config["ads"]["credentials"]["new"]["password"] = password

    # 原子写入：tempfile.mkstemp + os.replace
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(config_path), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(config, f, indent=2)
            os.replace(tmp, config_path)
            _logger.info("[ADS sync] config.json updated — url=%s", ADS_BASE_URL)
            return True
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    except (PermissionError, OSError) as e:
        _logger.error("[ADS sync] Failed to write config.json: %s", e)
        return False
