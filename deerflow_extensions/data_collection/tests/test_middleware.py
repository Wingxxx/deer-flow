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
