"""Configuration module for data collection.

Configuration source priority (highest to lowest):
  1. Standalone YAML file (e.g., data_collection.yaml)
  2. DeerFlow config.yaml `data_collection` section
  3. Environment variables (DATA_COLLECTION_*)
  4. DEFAULT_CONFIG defaults
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "output_dir": "./data_collection_logs",
    "buffer_size": 500,
    "flush_interval_sec": 5.0,
    "max_file_size_mb": 100,
    "collect_agent_input": True,
    "collect_model_output": True,
    "collect_tool_calls": True,
    "collect_intermediate_state": False,
    "collect_final_response": True,
    "role_extract_mode": "auto",
    # ── User identity collection (opt-in, privacy-safe) ──
    # Whether to record the authenticated user_id in training data.
    # DISABLED by default. Set to True only after internal privacy review
    # and with pseudonymize_identity enabled.
    "collect_user_identity": False,
    # Whether to record the IM channel platform user_id (channel_user_id).
    # INDEPENDENTLY controlled from collect_user_identity.
    # DISABLED by default. channel_user_id may contain raw platform
    # identifiers (e.g., "user@example.com") — treat with extra care.
    "collect_channel_user_id": False,
    # When True, user_id/channel_user_id are HMAC-SHA256 hashed with
    # pseudonym_salt before writing to disk. This is pseudonymization,
    # NOT anonymization — same input always produces same hash,
    # enabling per-user analytics without exposing raw identifiers.
    # Default: True (enabled when identity collection is on).
    "pseudonymize_identity": True,
    # Salt for the pseudonymization HMAC. Set via DATA_COLLECTION_PSEUDONYM_SALT
    # environment variable. An empty salt produces a WARNING at startup and
    # means hashes will NOT be linkable across sessions.
    "pseudonym_salt": "",
}

_ENV_VAR_MAP: dict[str, tuple[str, callable]] = {
    "DATA_COLLECTION_ENABLED": ("enabled", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_OUTPUT_DIR": ("output_dir", str),
    "DATA_COLLECTION_BUFFER_SIZE": ("buffer_size", int),
    "DATA_COLLECTION_FLUSH_INTERVAL": ("flush_interval_sec", float),
    "DATA_COLLECTION_ROLE_EXTRACT_MODE": ("role_extract_mode", str),
    "DATA_COLLECTION_COLLECT_USER_IDENTITY": ("collect_user_identity", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_COLLECT_CHANNEL_USER_ID": ("collect_channel_user_id", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_PSEUDONYM_SALT": ("pseudonym_salt", str),
}


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load data collection configuration from available sources.

    Priority:
      1. Standalone YAML file specified by config_path
      2. DeerFlow config.yaml `data_collection` section
      3. Environment variable overrides
      4. DEFAULT_CONFIG fallback values

    Args:
        config_path: Optional path to a standalone YAML configuration file.

    Returns:
        Merged configuration dictionary.
    """
    config = dict(DEFAULT_CONFIG)

    # Priority 1: Standalone YAML file
    if config_path and os.path.exists(config_path):
        try:
            import yaml as _yaml
            with open(config_path, encoding="utf-8") as f:
                external = _yaml.safe_load(f) or {}
                external_dc = external.get("data_collection", {})
                if external_dc:
                    config.update(external_dc)
                    return _apply_env_overrides(config)
        except Exception:
            pass

    # Priority 2: DeerFlow config.yaml data_collection section
    try:
        from deerflow.config.app_config import get_app_config

        app_cfg = get_app_config()
        app_cfg_dict = app_cfg.model_dump() if hasattr(app_cfg, "model_dump") else {}
        dc = app_cfg_dict.get("data_collection", {})
        if dc:
            config.update(dc)
    except Exception:
        pass

    # Priority 3: Environment variable overrides (always applied)
    config = _apply_env_overrides(config)

    # Semantic validation warnings (fail-open: warn only, never raise)
    if config.get("collect_user_identity") and not config.get("pseudonymize_identity"):
        logger.warning(
            "[DataCollection] collect_user_identity=ON but pseudonymize_identity=OFF — "
            "raw user_id will be written in plaintext to daily JSONL files."
        )
    if config.get("pseudonymize_identity") and not config.get("pseudonym_salt"):
        logger.warning(
            "[DataCollection] pseudonym_salt is empty — hashes will NOT be linkable "
            "across sessions. Set DATA_COLLECTION_PSEUDONYM_SALT env var."
        )

    return config


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides to the config dict in-place.

    Only env vars that are actually set in the environment will override.
    """
    for env_name, (key, converter) in _ENV_VAR_MAP.items():
        if env_name in os.environ:
            try:
                config[key] = converter(os.environ[env_name])
            except (ValueError, TypeError):
                pass
    return config
