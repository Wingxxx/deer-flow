"""Configuration module for data collection.

Configuration source priority (highest to lowest):
  1. Standalone YAML file (e.g., data_collection.yaml)
  2. DeerFlow config.yaml `data_collection` section
  3. Environment variables (DATA_COLLECTION_*)
  4. DEFAULT_CONFIG defaults
"""

import logging
import os
import secrets
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
    # ── User identity collection (privacy-safe) ──
    # Whether to record the authenticated user_id in training data.
    # ENABLED by default. Identity is HMAC-pseudonymized when
    # pseudonymize_identity=True (also the default).
    "collect_user_identity": True,
    # Whether to record the IM channel platform user_id (channel_user_id).
    # ENABLED by default together with collect_user_identity.
    "collect_channel_user_id": True,
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
    "DATA_COLLECTION_MAX_FILE_SIZE_MB": ("max_file_size_mb", lambda v: max(int(v), 1)),
    "DATA_COLLECTION_ROLE_EXTRACT_MODE": ("role_extract_mode", str),
    "DATA_COLLECTION_COLLECT_AGENT_INPUT": ("collect_agent_input", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_COLLECT_MODEL_OUTPUT": ("collect_model_output", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_COLLECT_TOOL_CALLS": ("collect_tool_calls", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_COLLECT_INTERMEDIATE_STATE": ("collect_intermediate_state", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_COLLECT_FINAL_RESPONSE": ("collect_final_response", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_COLLECT_USER_IDENTITY": ("collect_user_identity", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_COLLECT_CHANNEL_USER_ID": ("collect_channel_user_id", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_PSEUDONYMIZE_IDENTITY": ("pseudonymize_identity", lambda v: v.lower() == "true"),
    "DATA_COLLECTION_PSEUDONYM_SALT": ("pseudonym_salt", str),
}


def _load_or_create_salt(output_dir: str) -> str:
    """Load pseudonym salt from file, or create and persist a new one.

    Priority: env var DATA_COLLECTION_PSEUDONYM_SALT > persisted file > auto-generate.
    Returns 64-char hex string.
    """
    salt_file = os.path.join(output_dir, ".pseudonym_salt")
    try:
        if os.path.exists(salt_file):
            with open(salt_file, "r", encoding="utf-8") as f:
                salt = f.read().strip()
                if salt and len(salt) >= 32:
                    return salt
    except Exception:
        pass
    # Generate new salt and persist
    salt = secrets.token_hex(32)
    try:
        os.makedirs(output_dir, exist_ok=True)
        with open(salt_file, "w", encoding="utf-8") as f:
            f.write(salt)
        logger.info(
            "[DataCollection] Generated and persisted new pseudonym_salt to %s. "
            "Set DATA_COLLECTION_PSEUDONYM_SALT to override.",
            salt_file,
        )
    except Exception as e:
        logger.warning(
            "[DataCollection] Failed to persist salt file: %s. "
            "Salt will NOT survive restart.", e
        )
    return salt


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

    # Auto-generate salt when none configured (secure-by-default)
    if config.get("pseudonymize_identity") and not config.get("pseudonym_salt"):
        output_dir = config.get("output_dir", "./data_collection_logs")
        config["pseudonym_salt"] = _load_or_create_salt(output_dir)

    # Plaintext identity gate — requires explicit confirmation
    if config.get("collect_user_identity") and not config.get("pseudonymize_identity"):
        allow_plaintext = os.environ.get("DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY", "").lower() == "true"
        if not allow_plaintext:
            raise ValueError(
                "collect_user_identity=ON but pseudonymize_identity=OFF. "
                "This would write raw user_id in plaintext to daily JSONL files. "
                "Set DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true to explicitly "
                "acknowledge this risk, or set pseudonymize_identity=true."
            )
        logger.critical(
            "[DataCollection] PLAINTEXT IDENTITY MODE — raw user_id will be written to JSONL. "
            "DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true confirmed."
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
