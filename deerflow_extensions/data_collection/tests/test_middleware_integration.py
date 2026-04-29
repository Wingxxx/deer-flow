"""Integration tests for middleware + role_parser collaboration.

WING
"""

import asyncio
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from deerflow_extensions.data_collection.middleware import DataCollectionMiddleware


@pytest.fixture
def mock_collector():
    collector = MagicMock()
    collector.record_agent_input = MagicMock()
    collector.record_model_output = MagicMock()
    collector.record_tool_call = MagicMock()
    collector.record_intermediate_state = MagicMock()
    collector.record_final_response = MagicMock()
    return collector


@pytest.fixture
def middleware(mock_collector):
    mw = DataCollectionMiddleware()
    mw.collector = mock_collector
    mw.role_extract_mode = "auto"
    return mw


class TestMiddlewareRoleParserIntegration:
    """Test middleware correctly uses role_parser to extract user queries."""

    def test_before_model_with_human_type(self, middleware, mock_collector):
        """Test that messages with type='human' are correctly parsed.

        This is the LangGraph format where HumanMessage has type='human'.
        """
        state = {
            "config": {"configurable": {"thread_id": "test-thread-1"}},
            "messages": [{"type": "human", "content": [{"type": "text", "text": "学习关于图论并创建教程。"}]}],
            "max_steps": 25,
            "rag_context": "",
        }

        middleware.before_model(state)

        mock_collector.record_agent_input.assert_called_once()
        call_kwargs = mock_collector.record_agent_input.call_args.kwargs

        assert call_kwargs["session_id"] == "test-thread-1"
        assert call_kwargs["user_query"] == "[{'type': 'text', 'text': '学习关于图论并创建教程。'}]"
        assert call_kwargs["system_prompt"] == ""
        assert call_kwargs["history_context"] == []

    def test_before_model_with_user_role(self, middleware, mock_collector):
        """Test that messages with role='user' are correctly parsed."""
        state = {
            "config": {"configurable": {"thread_id": "test-thread-2"}},
            "messages": [{"role": "user", "content": "Hello, how are you?"}],
            "max_steps": 25,
            "rag_context": "",
        }

        middleware.before_model(state)

        mock_collector.record_agent_input.assert_called_once()
        call_kwargs = mock_collector.record_agent_input.call_args.kwargs

        assert call_kwargs["session_id"] == "test-thread-2"
        assert call_kwargs["user_query"] == "Hello, how are you?"

    def test_before_model_multiturn_conversation(self, middleware, mock_collector):
        """Test multi-turn conversation: history_context is correctly filled."""
        state = {
            "config": {"configurable": {"thread_id": "test-thread-3"}},
            "messages": [
                {"role": "user", "content": "First question"},
                {"role": "ai", "content": "First answer"},
                {"role": "ai", "content": "Second answer"},
                {"type": "human", "content": "Second question"},
            ],
            "max_steps": 25,
            "rag_context": "",
        }

        middleware.before_model(state)

        mock_collector.record_agent_input.assert_called_once()
        call_kwargs = mock_collector.record_agent_input.call_args.kwargs

        assert call_kwargs["user_query"] == "Second question"
        assert len(call_kwargs["history_context"]) == 2

    def test_before_model_with_system_prompt(self, middleware, mock_collector):
        """Test that system prompts are correctly extracted."""
        state = {
            "config": {"configurable": {"thread_id": "test-thread-4"}},
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"type": "human", "content": "Hello"},
            ],
            "max_steps": 25,
            "rag_context": "",
        }

        middleware.before_model(state)

        mock_collector.record_agent_input.assert_called_once()
        call_kwargs = mock_collector.record_agent_input.call_args.kwargs

        assert call_kwargs["system_prompt"] == "You are a helpful assistant."
        assert call_kwargs["user_query"] == "Hello"
        assert call_kwargs["history_context"] == []

    def test_before_model_langchain_human_message(self, middleware, mock_collector):
        """Test with actual LangChain HumanMessage objects."""
        state = {
            "config": {"configurable": {"thread_id": "test-thread-5"}},
            "messages": [
                SystemMessage(content="You are a coding assistant."),
                HumanMessage(content="Write a Python function"),
            ],
            "max_steps": 25,
            "rag_context": "",
        }

        middleware.before_model(state)

        mock_collector.record_agent_input.assert_called_once()
        call_kwargs = mock_collector.record_agent_input.call_args.kwargs

        assert call_kwargs["system_prompt"] == "You are a coding assistant."
        assert call_kwargs["user_query"] == "Write a Python function"

    def test_before_model_langchain_ai_message(self, middleware, mock_collector):
        """Test with actual LangChain AIMessage objects in history."""
        state = {
            "config": {"configurable": {"thread_id": "test-thread-6"}},
            "messages": [
                HumanMessage(content="Question 1"),
                AIMessage(content="Answer 1"),
                HumanMessage(content="Question 2"),
            ],
            "max_steps": 25,
            "rag_context": "",
        }

        middleware.before_model(state)

        mock_collector.record_agent_input.assert_called_once()
        call_kwargs = mock_collector.record_agent_input.call_args.kwargs

        assert call_kwargs["user_query"] == "Question 2"
        assert len(call_kwargs["history_context"]) == 1
        assert call_kwargs["history_context"][0]["content"] == "Answer 1"

    def test_before_model_empty_messages(self, middleware, mock_collector):
        """Test with empty messages list - should not crash."""
        state = {
            "config": {"configurable": {"thread_id": "test-thread-7"}},
            "messages": [],
            "max_steps": 25,
            "rag_context": "",
        }

        middleware.before_model(state)

        mock_collector.record_agent_input.assert_called_once()
        call_kwargs = mock_collector.record_agent_input.call_args.kwargs

        assert call_kwargs["user_query"] == ""

    def test_before_model_role_extract_mode_human(self, middleware, mock_collector):
        """Test role_extract_mode='human' only recognizes type='human'."""
        middleware.role_extract_mode = "human"

        state = {
            "config": {"configurable": {"thread_id": "test-thread-8"}},
            "messages": [
                {"role": "user", "content": "This should not be extracted"},
                {"type": "human", "content": "This should be extracted"},
            ],
            "max_steps": 25,
            "rag_context": "",
        }

        middleware.before_model(state)

        call_kwargs = mock_collector.record_agent_input.call_args.kwargs
        assert call_kwargs["user_query"] == "This should be extracted"

    def test_before_model_role_extract_mode_user(self, middleware, mock_collector):
        """Test role_extract_mode='user' only recognizes role='user'."""
        middleware.role_extract_mode = "user"

        state = {
            "config": {"configurable": {"thread_id": "test-thread-9"}},
            "messages": [
                {"role": "user", "content": "This should be extracted"},
                {"type": "human", "content": "This should not be extracted"},
            ],
            "max_steps": 25,
            "rag_context": "",
        }

        middleware.before_model(state)

        call_kwargs = mock_collector.record_agent_input.call_args.kwargs
        assert call_kwargs["user_query"] == "This should be extracted"


class TestMiddlewareAsyncIntegration:
    """Test async middleware methods work correctly."""

    @pytest.mark.anyio
    async def test_abefore_model_integration(self, mock_collector):
        """Test async before_model correctly delegates to sync version."""
        mw = DataCollectionMiddleware()
        mw.collector = mock_collector
        mw.role_extract_mode = "auto"

        state = {
            "config": {"configurable": {"thread_id": "test-thread-async"}},
            "messages": [{"type": "human", "content": "Async test"}],
            "max_steps": 25,
            "rag_context": "",
        }

        result = await mw.abefore_model(state)

        assert result is state
        mock_collector.record_agent_input.assert_called_once()
