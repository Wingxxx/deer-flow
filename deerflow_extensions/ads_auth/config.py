import os
import sys
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader: set env vars from KEY=VAL lines if not already set."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        if key not in os.environ:
            os.environ[key] = val


# Try to find .env relative to this file (deerflow_extensions/ads_auth/config.py -> project root)
_proj_root = Path(__file__).resolve().parent.parent.parent
_load_dotenv(_proj_root / ".env")

ADS_BASE_URL: str = os.getenv("ADS_BASE_URL", "http://ads:8080")

MCP_CONFIG_PATH: str = os.getenv("ADS_MCP_CONFIG_PATH", "~/.config/deer-flow/ads-mcp.json")

# ── ADS 认证用户默认角色 ──────────────────────────────────────────────

_ADS_DEFAULT_ROLE_CACHE: str | None = None


def get_ads_default_role() -> str:
    """返回 ADS 认证用户的默认 system_role。

    通过 ADS_DEFAULT_ROLE 环境变量配置，合法值: "admin" | "user"，默认 "admin"。
    模块级缓存，首调用后零开销。
    """
    global _ADS_DEFAULT_ROLE_CACHE
    if _ADS_DEFAULT_ROLE_CACHE is not None:
        return _ADS_DEFAULT_ROLE_CACHE
    role = os.getenv("ADS_DEFAULT_ROLE", "admin").strip().lower()
    if role not in ("admin", "user"):
        import logging
        logging.getLogger(__name__).warning(
            "ADS_DEFAULT_ROLE=%r 无效，降级为 admin", role
        )
        role = "admin"
    _ADS_DEFAULT_ROLE_CACHE = role
    return _ADS_DEFAULT_ROLE_CACHE
