import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest
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
    return mw


@pytest.fixture
def sample_state():
    return {
        "config": {"configurable": {"thread_id": "test-thread-123"}},
        "messages": [{"type": "user", "content": "hello"}],
        "max_steps": 25,
        "rag_context": "",
    }


class TestAsyncMiddlewareMethods:
    @pytest.mark.anyio
    async def test_abefore_model_delegates_to_sync(self, middleware, mock_collector, sample_state):
        result = await middleware.abefore_model(sample_state)
        assert result is sample_state
        mock_collector.record_agent_input.assert_called_once()

    @pytest.mark.anyio
    async def test_aafter_model_delegates_to_sync(self, middleware, mock_collector, sample_state):
        mock_msg = MagicMock()
        mock_msg.type = "ai"
        mock_msg.content = "response"
        mock_msg.additional_kwargs = {}
        mock_msg.response_metadata = {}
        state_with_msg = {**sample_state, "messages": [mock_msg]}

        result = await middleware.aafter_model(state_with_msg)
        assert result is state_with_msg
        mock_collector.record_model_output.assert_called_once()

    @pytest.mark.anyio
    async def test_aafter_agent_delegates_to_sync(self, middleware, mock_collector, sample_state):
        result = await middleware.aafter_agent(sample_state)
        assert result is sample_state
        mock_collector.record_final_response.assert_called_once()


class TestSyncMiddlewareMethods:
    def test_before_model_records_agent_input(self, middleware, mock_collector, sample_state):
        middleware.before_model(sample_state)
        mock_collector.record_agent_input.assert_called_once()
        call_kwargs = mock_collector.record_agent_input.call_args.kwargs
        assert call_kwargs["session_id"] == "test-thread-123"

    def test_before_model_initializes_session_state(self, middleware, mock_collector, sample_state):
        middleware.before_model(sample_state)
        assert "test-thread-123" in middleware._step_counts
        assert "test-thread-123" in middleware._llm_calls
        assert "test-thread-123" in middleware._tool_calls

    def test_after_model_records_model_output(self, middleware, mock_collector, sample_state):
        mock_msg = MagicMock()
        mock_msg.type = "ai"
        mock_msg.content = "response"
        mock_msg.additional_kwargs = {}
        mock_msg.response_metadata = {}
        state_with_msg = {**sample_state, "messages": [mock_msg]}

        middleware.before_model(sample_state)
        middleware.after_model(state_with_msg)
        mock_collector.record_model_output.assert_called_once()

    def test_after_agent_records_final_response(self, middleware, mock_collector, sample_state):
        middleware.before_model(sample_state)
        middleware.after_agent(sample_state)
        mock_collector.record_final_response.assert_called_once()

    def test_after_agent_cleans_session_state(self, middleware, mock_collector, sample_state):
        middleware.before_model(sample_state)
        middleware.after_agent(sample_state)
        assert "test-thread-123" not in middleware._step_counts


class TestMiddlewareWithNoneCollector:
    def test_before_model_with_none_collector(self):
        mw = DataCollectionMiddleware()
        mw.collector = None
        state = {"config": {}}
        result = mw.before_model(state)
        assert result is state

    @pytest.mark.anyio
    async def test_abefore_model_with_none_collector(self):
        mw = DataCollectionMiddleware()
        mw.collector = None
        state = {"config": {}}
        result = await mw.abefore_model(state)
        assert result is state

    @pytest.mark.anyio
    async def test_aafter_model_with_none_collector(self):
        mw = DataCollectionMiddleware()
        mw.collector = None
        state = {"config": {}}
        result = await mw.aafter_model(state)
        assert result is state

    @pytest.mark.anyio
    async def test_aafter_agent_with_none_collector(self):
        mw = DataCollectionMiddleware()
        mw.collector = None
        state = {"config": {}}
        result = await mw.aafter_agent(state)
        assert result is state


class TestWrapToolCall:
    def test_wrap_tool_call_correctly_extracts_tool_info(self, middleware, mock_collector):
        mock_request = MagicMock()
        mock_request.tool_call = {
            "name": "bash",
            "args": {"command": "ls -la"},
            "id": "call_123",
            "metadata": {"session_id": "test-session"},
        }

        def mock_handler(req):
            return MagicMock(content="result")

        middleware.wrap_tool_call(mock_request, mock_handler)

        assert mock_collector.record_tool_call.call_count == 2

        request_call = mock_collector.record_tool_call.call_args_list[0].kwargs
        assert request_call["session_id"] == "test-session"
        assert request_call["tool_name"] == "bash"
        assert request_call["tool_params"] == {"command": "ls -la"}
        assert request_call["call_id"] == "call_123"
        assert request_call["phase"] == "request"

        result_call = mock_collector.record_tool_call.call_args_list[1].kwargs
        assert result_call["session_id"] == "test-session"
        assert result_call["tool_name"] == "bash"
        assert result_call["tool_params"] == {"command": "ls -la"}
        assert result_call["call_id"] == "call_123"
        assert result_call["phase"] == "result"
        assert result_call["error"] is None

    def test_wrap_tool_call_captures_multiple_tools(self, middleware, mock_collector):
        tools = [
            {"name": "read_file", "args": {"path": "/etc/hosts"}, "id": "call_1", "metadata": {}},
            {"name": "write_file", "args": {"path": "/tmp/test", "content": "hello"}, "id": "call_2", "metadata": {}},
            {"name": "bash", "args": {"command": "echo hi"}, "id": "call_3", "metadata": {}},
        ]

        for i, tool_spec in enumerate(tools):
            mock_request = MagicMock()
            mock_request.tool_call = tool_spec

            def mock_handler(req):
                return MagicMock(content=f"result_{i}")

            middleware._step_counts["unknown"] = i
            middleware.wrap_tool_call(mock_request, mock_handler)

        assert mock_collector.record_tool_call.call_count == 6

    def test_wrap_tool_call_with_missing_metadata(self, middleware, mock_collector):
        mock_request = MagicMock()
        mock_request.tool_call = {
            "name": "bash",
            "args": {"command": "pwd"},
            "id": "call_456",
        }

        def mock_handler(req):
            return MagicMock(content="result")

        middleware.wrap_tool_call(mock_request, mock_handler)

        call_args = mock_collector.record_tool_call.call_args_list[0].kwargs
        assert call_args["session_id"] == "unknown"
        assert call_args["tool_name"] == "bash"
        assert call_args["tool_params"] == {"command": "pwd"}

    def test_wrap_tool_call_with_empty_tool_call(self, middleware, mock_collector):
        mock_request = MagicMock()
        mock_request.tool_call = {}

        def mock_handler(req):
            return MagicMock(content="result")

        middleware.wrap_tool_call(mock_request, mock_handler)

        call_args = mock_collector.record_tool_call.call_args_list[0].kwargs
        assert call_args["tool_name"] == "unknown"
        assert call_args["tool_params"] == {}


class TestWrapToolCallAsync:
    @pytest.mark.anyio
    async def test_awrap_tool_call_correctly_extracts_tool_info(self, middleware, mock_collector):
        mock_request = MagicMock()
        mock_request.tool_call = {
            "name": "read_file",
            "args": {"path": "/tmp/test.txt"},
            "id": "async_call_123",
            "metadata": {"session_id": "async-session"},
        }

        async def mock_handler(req):
            return MagicMock(content="async result")

        await middleware.awrap_tool_call(mock_request, mock_handler)

        assert mock_collector.record_tool_call.call_count == 2

        request_call = mock_collector.record_tool_call.call_args_list[0].kwargs
        assert request_call["session_id"] == "async-session"
        assert request_call["tool_name"] == "read_file"
        assert request_call["tool_params"] == {"path": "/tmp/test.txt"}
        assert request_call["call_id"] == "async_call_123"
        assert request_call["phase"] == "request"

    @pytest.mark.anyio
    async def test_awrap_tool_call_with_none_collector(self):
        mw = DataCollectionMiddleware()
        mw.collector = None
        mock_request = MagicMock()
        mock_request.tool_call = {
            "name": "bash",
            "args": {},
            "id": "call_none",
        }

        async def mock_handler(req):
            return MagicMock(content="result")

        result = await mw.awrap_tool_call(mock_request, mock_handler)
        mock_result = await result
        assert hasattr(mock_result, "content")


class TestMiddlewareAsyncConcurrency:
    @pytest.mark.anyio
    async def test_concurrent_abefore_model_calls(self, middleware, mock_collector):
        states = [
            {
                "config": {"configurable": {"thread_id": f"thread-{i}"}},
                "messages": [{"type": "user", "content": f"hello {i}"}],
                "max_steps": 25,
            }
            for i in range(10)
        ]

        tasks = [middleware.abefore_model(state) for state in states]
        await asyncio.gather(*tasks)

        assert mock_collector.record_agent_input.call_count == 10

    @pytest.mark.anyio
    async def test_concurrent_aafter_agent_calls(self, middleware, mock_collector):
        states = [
            {
                "config": {"configurable": {"thread_id": f"thread-{i}"}},
                "messages": [],
                "max_steps": 25,
            }
            for i in range(10)
        ]

        tasks = [middleware.aafter_agent(state) for state in states]
        await asyncio.gather(*tasks)

        assert mock_collector.record_final_response.call_count == 10


class TestMiddlewareIdentity:
    """Test middleware identity extraction, caching, and cleanup with new return-value API."""

    def test_prepare_identity_with_runtime_context(self):
        """_prepare_identity_for_collector returns identity dict extracted from runtime.context."""
        mw = DataCollectionMiddleware()
        mock_run = MagicMock()
        mock_run.context = {"user_id": "user-123", "channel_user_id": "chan-456"}
        mw.collector = MagicMock()
        mw._collect_user_identity = True
        mw._collect_channel_user_id = True
        mw._pseudonymize_identity = False  # raw for test

        result = mw._prepare_identity_for_collector(
            {"config": {"configurable": {"thread_id": "tid-1"}}}, mock_run, "tid-1"
        )

        assert result == {"user_id": "user-123", "channel_user_id": "chan-456"}
        assert mw._session_identity.get("tid-1") == {"user_id": "user-123", "channel_user_id": "chan-456"}

    def test_prepare_identity_no_runtime_does_not_crash(self):
        """_prepare_identity_for_collector with runtime=None returns None."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()
        mw._collect_user_identity = True

        result = mw._prepare_identity_for_collector({}, None, "tid-2")

        assert result is None

    def test_prepare_identity_with_pseudonymize(self):
        """_prepare_identity_for_collector applies pseudonymization and returns result."""
        mw = DataCollectionMiddleware()
        mw._pseudonymize_identity = True
        mw._identity_salt = "test-salt"
        mw._collect_user_identity = True
        mw.collector = MagicMock()
        mock_run = MagicMock()
        mock_run.context = {"user_id": "user-123"}

        result = mw._prepare_identity_for_collector({}, mock_run, "tid-3")

        assert result is not None
        assert "user_id" in result
        assert result["user_id"] != "user-123"  # pseudonymized
        assert len(result["user_id"]) == 64  # hex digest

        cached = mw._session_identity.get("tid-3", {})
        assert "user_id" in cached
        assert cached["user_id"] == result["user_id"]

    def test_restore_identity_from_cache(self):
        """_restore_identity_for_collector returns cached identity dict."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()
        mw._session_identity["tid-4"] = {"user_id": "cached-user"}

        result = mw._restore_identity_for_collector("tid-4")

        assert result == {"user_id": "cached-user"}

    def test_restore_identity_unknown_session_returns_none(self):
        """_restore_identity_for_collector with unknown session returns None."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()

        result = mw._restore_identity_for_collector("unknown-session")

        assert result is None

    def test_restore_identity_empty_session_returns_none(self):
        """_restore_identity_for_collector with empty session id returns None."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()

        result = mw._restore_identity_for_collector("")

        assert result is None

    def test_after_agent_cleans_session_identity(self):
        """after_agent pops the session from _session_identity."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()
        mw._session_identity["tid-5"] = {"user_id": "test"}
        mw._step_counts["tid-5"] = 0
        mw._session_start["tid-5"] = 0.0
        mw._llm_calls["tid-5"] = 0
        mw._tool_calls["tid-5"] = 0
        mw._accumulated_tokens["tid-5"] = {}

        state = {"config": {"configurable": {"thread_id": "tid-5"}}, "messages": []}
        mw.after_agent(state)

        assert "tid-5" not in mw._session_identity

    # ── New tests: hook-level identity passing ──

    def test_before_model_passes_identity_to_record(self):
        """before_model passes the identity= kwarg to record_agent_input."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()
        mw._collect_user_identity = True
        mw._collect_channel_user_id = True
        mw._pseudonymize_identity = False

        mock_run = MagicMock()
        mock_run.context = {"user_id": "hook-user", "channel_user_id": "hook-chan"}

        state = {
            "config": {"configurable": {"thread_id": "tid-hook"}},
            "messages": [{"type": "user", "content": "hello"}],
            "max_steps": 25,
            "rag_context": "",
        }

        mw.before_model(state, mock_run)

        call_kwargs = mw.collector.record_agent_input.call_args.kwargs
        assert "identity" in call_kwargs
        assert call_kwargs["identity"] == {"user_id": "hook-user", "channel_user_id": "hook-chan"}

    def test_after_model_passes_identity_to_both_records(self):
        """after_model passes identity= to both record_model_output and record_intermediate_state."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()
        mw._collect_user_identity = True
        mw._pseudonymize_identity = False

        mock_run = MagicMock()
        mock_run.context = {"user_id": "after-user"}

        state = {
            "config": {"configurable": {"thread_id": "tid-after"}},
            "messages": [{"type": "user", "content": "hello"}],
            "max_steps": 25,
            "rag_context": "",
        }

        mw.before_model(state, mock_run)

        mock_msg = MagicMock()
        mock_msg.type = "ai"
        mock_msg.content = "response"
        mock_msg.additional_kwargs = {}
        mock_msg.response_metadata = {}
        after_state = {**state, "messages": [mock_msg]}

        mw.after_model(after_state, mock_run)

        model_kwargs = mw.collector.record_model_output.call_args.kwargs
        assert "identity" in model_kwargs
        assert model_kwargs["identity"] == {"user_id": "after-user"}

        inter_kwargs = mw.collector.record_intermediate_state.call_args.kwargs
        assert "identity" in inter_kwargs
        assert inter_kwargs["identity"] == {"user_id": "after-user"}

    def test_wrap_tool_call_passes_identity_to_both_phases(self):
        """wrap_tool_call passes identity= to both request and result record_tool_call."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()
        mw._collect_user_identity = True
        mw._pseudonymize_identity = False

        mock_run = MagicMock()
        mock_run.context = {"user_id": "tool-user"}

        state = {
            "config": {"configurable": {"thread_id": "tid-tool"}},
            "messages": [{"type": "user", "content": "hello"}],
            "max_steps": 25,
        }

        mw.before_model(state, mock_run)

        mock_request = MagicMock()
        mock_request.tool_call = {
            "name": "bash",
            "args": {"cmd": "ls"},
            "id": "call-tool",
            "metadata": {"session_id": "tid-tool"},
        }

        def handler(req):
            return MagicMock(content="result")

        mw.wrap_tool_call(mock_request, handler)

        assert mw.collector.record_tool_call.call_count == 2
        request_kwargs = mw.collector.record_tool_call.call_args_list[0].kwargs
        assert "identity" in request_kwargs
        assert request_kwargs["identity"] == {"user_id": "tool-user"}

        result_kwargs = mw.collector.record_tool_call.call_args_list[1].kwargs
        assert "identity" in result_kwargs
        assert result_kwargs["identity"] == {"user_id": "tool-user"}

    def test_after_agent_passes_identity_to_final_response(self):
        """after_agent passes identity= to record_final_response."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()
        mw._collect_user_identity = True
        mw._pseudonymize_identity = False

        mock_run = MagicMock()
        mock_run.context = {"user_id": "final-user"}

        state = {
            "config": {"configurable": {"thread_id": "tid-final"}},
            "messages": [{"type": "user", "content": "hello"}],
            "max_steps": 25,
        }

        mw.before_model(state, mock_run)
        mw.after_agent(state, mock_run)

        call_kwargs = mw.collector.record_final_response.call_args.kwargs
        assert "identity" in call_kwargs
        assert call_kwargs["identity"] == {"user_id": "final-user"}

    def test_restore_returns_copy_not_reference(self):
        """_restore_identity_for_collector returns a copy, not a reference."""
        mw = DataCollectionMiddleware()
        mw.collector = MagicMock()
        mw._session_identity["tid-copy"] = {"user_id": "original"}

        result = mw._restore_identity_for_collector("tid-copy")
        assert result == {"user_id": "original"}

        # Mutate the returned dict — should not affect the cache
        result["user_id"] = "mutated"
        assert mw._session_identity["tid-copy"]["user_id"] == "original"

    def test_load_config_failure_disables_identity(self):
        """When load_config raises, identity collection is disabled (fail-closed)."""
        with patch("deerflow_extensions.data_collection.middleware.load_config", side_effect=RuntimeError("boom")):
            mw = DataCollectionMiddleware()
            assert mw._collect_user_identity is False
            assert mw._collect_channel_user_id is False
            assert mw._pseudonymize_identity is False
            if mw.collector is not None:
                assert mw.collector.collect_flags["user_identity"] is False
                assert mw.collector.collect_flags["channel_user_identity"] is False
