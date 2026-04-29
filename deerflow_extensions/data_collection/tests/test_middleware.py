import asyncio
from unittest.mock import MagicMock

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
