"""Tests for LlamaFactory format compatibility.

Verifies that the data collection and export pipeline produces
LlamaFactory-compatible output formats.

WING
"""

import json
import pytest

from deerflow_extensions.data_collection.scripts.clean_and_aggregate import (
    DataAggregator,
    DataCleaner,
)
from deerflow_extensions.data_collection.scripts.export_formats import (
    convert_messages_to_sharegpt,
    convert_messages_to_alpaca_simple,
    export_dataset,
)


class TestLlamaFactoryMessagesFormat:
    """Test that aggregated data matches LlamaFactory messages format."""

    def test_single_turn_conversation(self):
        """Test single turn: user -> assistant."""
        samples = [
            {
                "sample_type": "agent_input",
                "session_id": "test-1",
                "user_query": "What is graph theory?",
                "system_prompt": "You are a helpful tutor.",
                "create_time": "2026-04-29T10:00:00Z",
                "raw_response": "",
            },
            {
                "sample_type": "model_output",
                "session_id": "test-1",
                "raw_response": "Graph theory is a branch of mathematics...",
                "create_time": "2026-04-29T10:00:01Z",
            },
        ]

        result = DataAggregator._build_training_sample(samples)
        assert result is not None

        messages = result["messages"]
        assert len(messages) == 3  # system + user + assistant

        assert messages[0] == {"role": "system", "content": "You are a helpful tutor."}
        assert messages[1] == {"role": "user", "content": "What is graph theory?"}
        assert messages[2] == {"role": "assistant", "content": "Graph theory is a branch of mathematics..."}

    def test_multi_turn_conversation(self):
        """Test multi-turn: system + user + assistant + user + assistant.

        Note: Each agent_input adds system prompt, so we get duplicate system messages
        in multi-turn. This is a known behavior of the current aggregation logic.
        """
        samples = [
            {
                "sample_type": "agent_input",
                "session_id": "test-2",
                "user_query": "First question",
                "system_prompt": "You are a helpful assistant.",
                "create_time": "2026-04-29T10:00:00Z",
                "raw_response": "",
            },
            {
                "sample_type": "model_output",
                "session_id": "test-2",
                "raw_response": "First answer",
                "create_time": "2026-04-29T10:00:01Z",
            },
            {
                "sample_type": "agent_input",
                "session_id": "test-2",
                "user_query": "Second question",
                "system_prompt": "You are a helpful assistant.",
                "create_time": "2026-04-29T10:00:02Z",
                "raw_response": "",
            },
            {
                "sample_type": "model_output",
                "session_id": "test-2",
                "raw_response": "Second answer",
                "create_time": "2026-04-29T10:00:03Z",
            },
        ]

        result = DataAggregator._build_training_sample(samples)
        assert result is not None

        messages = result["messages"]

        roles = [m["role"] for m in messages]
        assert roles.count("system") == 2  # System appears twice
        assert roles.count("user") == 2
        assert roles.count("assistant") == 2

        contents = [m["content"] for m in messages]
        assert "Second question" in contents
        assert "Second answer" in contents

    def test_metadata_included(self):
        """Test that metadata is preserved."""
        samples = [
            {
                "sample_type": "agent_input",
                "session_id": "test-3",
                "user_query": "Hello",
                "system_prompt": "",
                "create_time": "2026-04-29T10:00:00Z",
                "raw_response": "",
            },
            {
                "sample_type": "model_output",
                "session_id": "test-3",
                "raw_response": "Hi there!",
                "create_time": "2026-04-29T10:00:01Z",
            },
        ]

        result = DataAggregator._build_training_sample(samples)
        assert result is not None
        assert "metadata" in result
        assert result["metadata"]["session_id"] == "test-3"
        assert result["metadata"]["create_time"] == "2026-04-29T10:00:00Z"

    def test_tool_calls_format(self):
        """Test that tool calls are formatted correctly for LlamaFactory."""
        samples = [
            {
                "sample_type": "agent_input",
                "session_id": "test-4",
                "user_query": "Search for graph theory",
                "system_prompt": "You can use tools.",
                "create_time": "2026-04-29T10:00:00Z",
                "raw_response": "",
            },
            {
                "sample_type": "model_output",
                "session_id": "test-4",
                "raw_response": "I'll search for that.",
                "response_type": "tool_calls",
                "tool_calls": [
                    {
                        "call_id": "call_123",
                        "tool_name": "search",
                        "arguments": {"query": "graph theory"},
                    }
                ],
                "create_time": "2026-04-29T10:00:01Z",
            },
            {
                "sample_type": "tool_call_result",
                "session_id": "test-4",
                "call_id": "call_123",
                "result": {"results": ["Graph theory is..."]},
                "create_time": "2026-04-29T10:00:02Z",
            },
            {
                "sample_type": "model_output",
                "session_id": "test-4",
                "raw_response": "Based on my search...",
                "response_type": "text",
                "create_time": "2026-04-29T10:00:03Z",
            },
        ]

        result = DataAggregator._build_training_sample(samples)
        assert result is not None

        messages = result["messages"]
        tool_call_msg = messages[2]  # After system, user, first assistant

        assert tool_call_msg["role"] == "assistant"
        assert "tool_calls" in tool_call_msg

        tool_call = tool_call_msg["tool_calls"][0]
        assert tool_call["id"] == "call_123"
        assert tool_call["type"] == "function"
        assert tool_call["function"]["name"] == "search"
        assert "graph theory" in tool_call["function"]["arguments"]


class TestShareGPTExportFormat:
    """Test conversion to ShareGPT format."""

    def test_sharegpt_role_mapping(self):
        """Test that roles are correctly mapped to ShareGPT format."""
        sample = {
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        }

        result = convert_messages_to_sharegpt(sample)

        assert "conversations" in result
        convs = result["conversations"]

        assert convs[0]["from"] == "human"
        assert convs[0]["value"] == "You are helpful."
        assert convs[1]["from"] == "human"
        assert convs[1]["value"] == "Hello"
        assert convs[2]["from"] == "gpt"
        assert convs[2]["value"] == "Hi there!"

    def test_sharegpt_preserves_metadata(self):
        """Test that metadata is preserved in ShareGPT export."""
        sample = {
            "messages": [
                {"role": "user", "content": "Test"},
                {"role": "assistant", "content": "Response"},
            ],
            "metadata": {"session_id": "test-session"},
        }

        result = convert_messages_to_sharegpt(sample)

        assert result["metadata"]["session_id"] == "test-session"


class TestAlpacaExportFormat:
    """Test conversion to Alpaca simple format."""

    def test_alpaca_simple_conversion(self):
        """Test conversion to Alpaca instruction/input/output format."""
        sample = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is Python?"},
                {"role": "assistant", "content": "Python is a programming language."},
            ]
        }

        result = convert_messages_to_alpaca_simple(sample)

        assert result is not None
        assert "instruction" in result
        assert "input" in result
        assert "output" in result
        assert "You are a helpful assistant." in result["instruction"]
        assert "What is Python?" in result["instruction"]
        assert result["output"] == "Python is a programming language."
        assert result["input"] == ""

    def test_alpaca_skips_tool_calls(self):
        """Test that samples with tool calls are skipped."""
        sample = {
            "messages": [
                {"role": "user", "content": "Search something"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "call_1", "type": "function"}],
                },
            ]
        }

        result = convert_messages_to_alpaca_simple(sample)

        assert result is None


class TestDataCleaning:
    """Test data cleaning pipeline."""

    def test_filter_incomplete_requires_user_query(self):
        """Test that samples without user_query are filtered out."""
        samples = [
            {
                "sample_type": "agent_input",
                "session_id": "test-1",
                "user_query": "Valid query",
                "raw_response": "Response",
            },
            {
                "sample_type": "agent_input",
                "session_id": "test-2",
                "user_query": "",  # Empty - should be filtered
                "raw_response": "Response",
            },
        ]

        result = DataCleaner.filter_incomplete(samples)

        assert len(result) == 1
        assert result[0]["session_id"] == "test-1"

    def test_deduplication(self):
        """Test that duplicate samples are removed."""
        samples = [
            {
                "sample_type": "agent_input",
                "session_id": "test-1",
                "user_query": "Same query",
                "raw_response": "Same response",
            },
            {
                "sample_type": "agent_input",
                "session_id": "test-2",
                "user_query": "Same query",
                "raw_response": "Same response",
            },
        ]

        result = DataCleaner.deduplicate(samples)

        assert len(result) == 1
