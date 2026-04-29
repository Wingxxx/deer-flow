"""Tests for role_parser module.

WING
"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from deerflow_extensions.data_collection.role_parser import (
    extract_content,
    get_role,
    extract_user_query,
    extract_system_prompt,
    extract_history,
    parse_messages,
)


class TestExtractContent:
    def test_dict_message(self):
        msg = {"content": "Hello world"}
        assert extract_content(msg) == "Hello world"

    def test_langchain_human_message(self):
        msg = HumanMessage(content="Hello world")
        assert extract_content(msg) == "Hello world"

    def test_empty_content_dict(self):
        msg = {"content": ""}
        assert extract_content(msg) == ""

    def test_missing_content(self):
        msg = {}
        assert extract_content(msg) == ""


class TestGetRole:
    def test_dict_with_type(self):
        msg = {"type": "human", "content": "test"}
        assert get_role(msg) == "human"

    def test_dict_with_role(self):
        msg = {"role": "user", "content": "test"}
        assert get_role(msg) == "user"

    def test_dict_type_priority(self):
        msg = {"type": "human", "role": "user", "content": "test"}
        assert get_role(msg) == "human"

    def test_langchain_human_message(self):
        msg = HumanMessage(content="test")
        assert get_role(msg) == "human"

    def test_langchain_ai_message(self):
        msg = AIMessage(content="test")
        assert get_role(msg) == "ai"

    def test_langchain_system_message(self):
        msg = SystemMessage(content="test")
        assert get_role(msg) == "system"

    def test_empty_msg(self):
        msg = {}
        assert get_role(msg) == ""


class TestExtractUserQuery:
    def test_single_user_message(self):
        messages = [HumanMessage(content="Hello")]
        assert extract_user_query(messages) == "Hello"

    def test_single_human_type_message(self):
        messages = [{"type": "human", "content": "Hello"}]
        assert extract_user_query(messages) == "Hello"

    def test_user_role_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        assert extract_user_query(messages) == "Hello"

    def test_last_user_message_selected(self):
        messages = [
            HumanMessage(content="First"),
            AIMessage(content="Response"),
            HumanMessage(content="Last question"),
        ]
        assert extract_user_query(messages) == "Last question"

    def test_no_user_message(self):
        messages = [
            SystemMessage(content="System"),
            AIMessage(content="Response"),
        ]
        assert extract_user_query(messages) == ""

    def test_empty_messages(self):
        assert extract_user_query([]) == ""

    def test_mixed_format_messages(self):
        messages = [
            SystemMessage(content="System"),
            {"type": "human", "content": "User 1"},
            AIMessage(content="AI response"),
            {"role": "user", "content": "User 2"},
        ]
        assert extract_user_query(messages) == "User 2"


class TestExtractSystemPrompt:
    def test_single_system_message(self):
        messages = [SystemMessage(content="You are helpful")]
        assert extract_system_prompt(messages) == "You are helpful"

    def test_system_with_type(self):
        messages = [{"type": "system", "content": "System prompt"}]
        assert extract_system_prompt(messages) == "System prompt"

    def test_system_not_first(self):
        messages = [
            HumanMessage(content="Hello"),
            SystemMessage(content="System"),
        ]
        assert extract_system_prompt(messages) == "System"

    def test_no_system_message(self):
        messages = [HumanMessage(content="Hello")]
        assert extract_system_prompt(messages) == ""


class TestExtractHistory:
    def test_simple_conversation(self):
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
        ]
        history = extract_history(messages)
        assert len(history) == 1
        assert history[0]["role"] == "ai"

    def test_excludes_current_user_query(self):
        messages = [
            HumanMessage(content="First question"),
            AIMessage(content="First answer"),
            HumanMessage(content="Second question"),
        ]
        history = extract_history(messages)
        assert len(history) == 1
        assert history[0]["content"] == "First answer"

    def test_preserves_order(self):
        messages = [
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
            AIMessage(content="A2"),
        ]
        history = extract_history(messages)
        assert len(history) == 2
        assert history[0]["content"] == "A1"
        assert history[1]["content"] == "A2"

    def test_limits_to_four(self):
        messages = [
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
            AIMessage(content="A2"),
            HumanMessage(content="Q3"),
            AIMessage(content="A3"),
            HumanMessage(content="Q4"),
            AIMessage(content="A4"),
        ]
        history = extract_history(messages)
        assert len(history) == 4

    def test_empty_messages(self):
        assert extract_history([]) == []


class TestParseMessages:
    def test_complete_parsing(self):
        messages = [
            SystemMessage(content="You are helpful"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
        ]
        result = parse_messages(messages)

        assert result["user_query"] == "Hello"
        assert result["system_prompt"] == "You are helpful"
        assert len(result["history"]) == 1
        assert result["history"][0]["role"] == "ai"

    def test_multiturn_conversation(self):
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
            AIMessage(content="A2"),
        ]
        result = parse_messages(messages)

        assert result["user_query"] == "Q2"
        assert result["system_prompt"] == "System"
        assert len(result["history"]) == 2

    def test_empty_messages(self):
        result = parse_messages([])
        assert result["user_query"] == ""
        assert result["system_prompt"] == ""
        assert result["history"] == []

    def test_no_system_prompt(self):
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
        ]
        result = parse_messages(messages)
        assert result["system_prompt"] == ""
        assert result["user_query"] == "Hello"
