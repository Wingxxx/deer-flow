import os
import tempfile
from unittest.mock import patch

import pytest

from deerflow_extensions.data_collection.config import (
    DEFAULT_CONFIG,
    load_config,
    _apply_env_overrides,
)


class TestDefaultConfig:
    def test_default_config_is_complete(self):
        expected_keys = {
            "enabled",
            "output_dir",
            "buffer_size",
            "flush_interval_sec",
            "max_file_size_mb",
            "collect_agent_input",
            "collect_model_output",
            "collect_tool_calls",
            "collect_intermediate_state",
            "collect_final_response",
            "role_extract_mode",
            "collect_user_identity",
            "collect_channel_user_id",
            "pseudonymize_identity",
            "pseudonym_salt",
        }
        assert set(DEFAULT_CONFIG.keys()) == expected_keys

    def test_default_config_values(self):
        assert DEFAULT_CONFIG["enabled"] is True
        assert DEFAULT_CONFIG["output_dir"] == "./data_collection_logs"
        assert DEFAULT_CONFIG["buffer_size"] == 500
        assert DEFAULT_CONFIG["flush_interval_sec"] == 5.0
        assert DEFAULT_CONFIG["max_file_size_mb"] == 100
        assert DEFAULT_CONFIG["collect_agent_input"] is True
        assert DEFAULT_CONFIG["collect_model_output"] is True
        assert DEFAULT_CONFIG["collect_tool_calls"] is True
        assert DEFAULT_CONFIG["collect_intermediate_state"] is False
        assert DEFAULT_CONFIG["collect_final_response"] is True
        assert DEFAULT_CONFIG["role_extract_mode"] == "auto"
        assert DEFAULT_CONFIG["collect_user_identity"] is True
        assert DEFAULT_CONFIG["collect_channel_user_id"] is True
        assert DEFAULT_CONFIG["pseudonymize_identity"] is True
        # DEFAULT_CONFIG salt is still "" (auto-generated at load_config() time)
        assert DEFAULT_CONFIG["pseudonym_salt"] == ""


class TestLoadConfig:
    def test_load_config_returns_config_with_auto_salt(self):
        """load_config() auto-generates pseudonym_salt when empty + pseudonymize enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATA_COLLECTION_OUTPUT_DIR": tmpdir}, clear=True):
                cfg = load_config()
                assert cfg["enabled"] is True
                assert cfg["pseudonym_salt"] != ""
                assert len(cfg["pseudonym_salt"]) == 64
                # .pseudonym_salt file should exist
                salt_file = os.path.join(tmpdir, ".pseudonym_salt")
                assert os.path.exists(salt_file)

    def test_load_config_with_env_override_enabled(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_ENABLED": "false"}, clear=True):
            cfg = load_config()
            assert cfg["enabled"] is False

    def test_load_config_with_env_override_output_dir(self):
        test_dir = "/tmp/test_collection"
        with patch.dict(os.environ, {"DATA_COLLECTION_OUTPUT_DIR": test_dir}, clear=True):
            cfg = load_config()
            assert cfg["output_dir"] == test_dir

    def test_load_config_with_env_override_buffer_size(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_BUFFER_SIZE": "100"}, clear=True):
            cfg = load_config()
            assert cfg["buffer_size"] == 100

    def test_load_config_with_env_override_flush_interval(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_FLUSH_INTERVAL": "2.5"}, clear=True):
            cfg = load_config()
            assert cfg["flush_interval_sec"] == 2.5

    def test_load_config_with_invalid_env_value_falls_back(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_BUFFER_SIZE": "not_a_number"}, clear=True):
            cfg = load_config()
            assert cfg["buffer_size"] == DEFAULT_CONFIG["buffer_size"]

    def test_load_config_file_not_found_returns_default_with_auto_salt(self):
        cfg = load_config(config_path="/nonexistent/path/config.yaml")
        assert cfg["enabled"] is True
        # Auto-salt should be generated
        assert cfg["pseudonym_salt"] != ""
        assert len(cfg["pseudonym_salt"]) == 64

    def test_apply_env_overrides_partial(self):
        base = dict(DEFAULT_CONFIG)
        with patch.dict(os.environ, {"DATA_COLLECTION_ENABLED": "false"}, clear=True):
            result = _apply_env_overrides(base)
            assert result["enabled"] is False
            assert result["output_dir"] == DEFAULT_CONFIG["output_dir"]
            assert result["buffer_size"] == DEFAULT_CONFIG["buffer_size"]

    def test_env_var_override_collect_user_identity(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_COLLECT_USER_IDENTITY": "true"}, clear=True):
            cfg = load_config()
            assert cfg["collect_user_identity"] is True

    def test_env_var_override_collect_channel_user_id(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_COLLECT_CHANNEL_USER_ID": "true"}, clear=True):
            cfg = load_config()
            assert cfg["collect_channel_user_id"] is True

    def test_env_var_override_collect_user_identity_to_false(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_COLLECT_USER_IDENTITY": "false"}, clear=True):
            cfg = load_config()
            assert cfg["collect_user_identity"] is False

    def test_env_var_override_collect_channel_user_id_to_false(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_COLLECT_CHANNEL_USER_ID": "false"}, clear=True):
            cfg = load_config()
            assert cfg["collect_channel_user_id"] is False

    def test_env_var_override_pseudonym_salt(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_PSEUDONYM_SALT": "my-secret-salt"}, clear=True):
            cfg = load_config()
            assert cfg["pseudonym_salt"] == "my-secret-salt"

    def test_env_var_not_set_does_not_override(self):
        base = dict(DEFAULT_CONFIG)
        with patch.dict(os.environ, {}, clear=True):
            result = _apply_env_overrides(base)
            assert result == base

    # ── New Phase 1 tests: salt persistence ──

    def test_salt_file_persisted_on_first_load(self):
        """First load_config creates .pseudonym_salt with 64-char hex."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATA_COLLECTION_OUTPUT_DIR": tmpdir}, clear=True):
                cfg = load_config()
                salt_file = os.path.join(tmpdir, ".pseudonym_salt")
                assert os.path.exists(salt_file)
                with open(salt_file) as f:
                    content = f.read().strip()
                assert len(content) == 64
                assert content == cfg["pseudonym_salt"]

    def test_salt_loaded_from_existing_file(self):
        """Second load_config reads same salt from persisted file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            salt_file = os.path.join(tmpdir, ".pseudonym_salt")
            os.makedirs(tmpdir, exist_ok=True)
            with open(salt_file, "w") as f:
                f.write("a" * 64)

            with patch.dict(os.environ, {"DATA_COLLECTION_OUTPUT_DIR": tmpdir}, clear=True):
                cfg1 = load_config()
                cfg2 = load_config()
            assert cfg1["pseudonym_salt"] == "a" * 64
            assert cfg2["pseudonym_salt"] == "a" * 64

    def test_salt_regenerated_when_file_corrupt(self):
        """Corrupt salt file (<32 chars) triggers regeneration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            salt_file = os.path.join(tmpdir, ".pseudonym_salt")
            os.makedirs(tmpdir, exist_ok=True)
            with open(salt_file, "w") as f:
                f.write("short")

            with patch.dict(os.environ, {"DATA_COLLECTION_OUTPUT_DIR": tmpdir}, clear=True):
                cfg = load_config()
            # Should have generated a new 64-char salt, not kept "short"
            assert len(cfg["pseudonym_salt"]) == 64
            assert cfg["pseudonym_salt"] != "short"

    def test_env_salt_overrides_persisted_file(self):
        """DATA_COLLECTION_PSEUDONYM_SALT env var overrides persisted file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            salt_file = os.path.join(tmpdir, ".pseudonym_salt")
            os.makedirs(tmpdir, exist_ok=True)
            with open(salt_file, "w") as f:
                f.write("b" * 64)

            with patch.dict(os.environ, {
                "DATA_COLLECTION_OUTPUT_DIR": tmpdir,
                "DATA_COLLECTION_PSEUDONYM_SALT": "env-override-salt",
            }, clear=True):
                cfg = load_config()
            assert cfg["pseudonym_salt"] == "env-override-salt"

    def test_salt_not_generated_when_pseudonymize_disabled(self):
        """No salt file created when pseudonymize_identity is False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "DATA_COLLECTION_OUTPUT_DIR": tmpdir,
                "DATA_COLLECTION_PSEUDONYMIZE_IDENTITY": "false",
                "DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY": "true",
            }, clear=True):
                cfg = load_config()
            salt_file = os.path.join(tmpdir, ".pseudonym_salt")
            assert not os.path.exists(salt_file)
            assert cfg["pseudonym_salt"] == ""

    # ── New Phase 3 tests: env var overrides for new entries ──

    def test_env_var_override_collect_agent_input(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_COLLECT_AGENT_INPUT": "false"}, clear=True):
            cfg = load_config()
            assert cfg["collect_agent_input"] is False

    def test_env_var_override_collect_model_output(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_COLLECT_MODEL_OUTPUT": "false"}, clear=True):
            cfg = load_config()
            assert cfg["collect_model_output"] is False

    def test_env_var_override_collect_tool_calls(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_COLLECT_TOOL_CALLS": "false"}, clear=True):
            cfg = load_config()
            assert cfg["collect_tool_calls"] is False

    def test_env_var_override_collect_intermediate_state(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_COLLECT_INTERMEDIATE_STATE": "true"}, clear=True):
            cfg = load_config()
            assert cfg["collect_intermediate_state"] is True

    def test_env_var_override_collect_final_response(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_COLLECT_FINAL_RESPONSE": "false"}, clear=True):
            cfg = load_config()
            assert cfg["collect_final_response"] is False

    def test_env_var_override_max_file_size_mb(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_MAX_FILE_SIZE_MB": "50"}, clear=True):
            cfg = load_config()
            assert cfg["max_file_size_mb"] == 50

    def test_env_var_override_pseudonymize_identity(self):
        with patch.dict(os.environ, {
            "DATA_COLLECTION_PSEUDONYMIZE_IDENTITY": "false",
            "DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY": "true",
        }, clear=True):
            cfg = load_config()
            assert cfg["pseudonymize_identity"] is False

    # ── New Phase 3 tests: max_file_size_mb defensive clamp ──

    def test_max_file_size_mb_negative_clamped_to_one(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_MAX_FILE_SIZE_MB": "-1"}, clear=True):
            cfg = load_config()
            assert cfg["max_file_size_mb"] == 1

    def test_max_file_size_mb_zero_clamped_to_one(self):
        with patch.dict(os.environ, {"DATA_COLLECTION_MAX_FILE_SIZE_MB": "0"}, clear=True):
            cfg = load_config()
            assert cfg["max_file_size_mb"] == 1

    # ── New Phase 3 tests: plaintext identity gate ──

    def test_plaintext_identity_raises_without_allow_flag(self):
        """collect_user_identity=true + pseudonymize=false raises ValueError."""
        with patch.dict(os.environ, {
            "DATA_COLLECTION_PSEUDONYMIZE_IDENTITY": "false",
        }, clear=True):
            with pytest.raises(ValueError, match="DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY"):
                load_config()

    def test_plaintext_identity_allowed_with_flag(self):
        """Setting DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true bypasses the gate."""
        with patch.dict(os.environ, {
            "DATA_COLLECTION_PSEUDONYMIZE_IDENTITY": "false",
            "DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY": "true",
        }, clear=True):
            cfg = load_config()
            assert cfg["pseudonymize_identity"] is False
            assert cfg["collect_user_identity"] is True
