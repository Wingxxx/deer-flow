import os
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
        }
        assert set(DEFAULT_CONFIG.keys()) == expected_keys

    def test_default_config_values(self):
        assert DEFAULT_CONFIG["enabled"] is True
        assert DEFAULT_CONFIG["output_dir"] == "/data/deerflow/training_logs"
        assert DEFAULT_CONFIG["buffer_size"] == 500
        assert DEFAULT_CONFIG["flush_interval_sec"] == 5.0
        assert DEFAULT_CONFIG["max_file_size_mb"] == 100
        assert DEFAULT_CONFIG["collect_agent_input"] is True
        assert DEFAULT_CONFIG["collect_model_output"] is True
        assert DEFAULT_CONFIG["collect_tool_calls"] is True
        assert DEFAULT_CONFIG["collect_intermediate_state"] is False
        assert DEFAULT_CONFIG["collect_final_response"] is True


class TestLoadConfig:
    def test_load_config_returns_default_when_no_overrides(self):
        cfg = load_config()
        assert cfg == DEFAULT_CONFIG

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

    def test_load_config_file_not_found_returns_default(self):
        cfg = load_config(config_path="/nonexistent/path/config.yaml")
        assert cfg == DEFAULT_CONFIG

    def test_apply_env_overrides_partial(self):
        base = dict(DEFAULT_CONFIG)
        with patch.dict(os.environ, {"DATA_COLLECTION_ENABLED": "false"}, clear=True):
            result = _apply_env_overrides(base)
            assert result["enabled"] is False
            assert result["output_dir"] == DEFAULT_CONFIG["output_dir"]
            assert result["buffer_size"] == DEFAULT_CONFIG["buffer_size"]

    def test_env_var_not_set_does_not_override(self):
        base = dict(DEFAULT_CONFIG)
        with patch.dict(os.environ, {}, clear=True):
            result = _apply_env_overrides(base)
            assert result == base
