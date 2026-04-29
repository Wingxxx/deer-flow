import asyncio
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from deerflow_extensions.data_collection.collector import (
    TrainingDataCollector,
    get_collector,
    set_collector,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    yield
    set_collector(None)


@pytest.fixture
def collector():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = {
            "enabled": True,
            "output_dir": tmpdir,
            "buffer_size": 10,
            "flush_interval_sec": 60.0,
            "max_file_size_mb": 100,
            "collect_agent_input": True,
            "collect_model_output": True,
            "collect_tool_calls": True,
            "collect_intermediate_state": True,
            "collect_final_response": True,
        }
        c = TrainingDataCollector(config=cfg)
        yield c


class TestTrainingDataCollector:
    def test_record_agent_input(self, collector):
        collector.record_agent_input(
            session_id="sess-1",
            user_query="Hello",
            system_prompt="Be helpful",
            history_context=[],
            rag_context="",
            agent_config={"model": "gpt-4"},
        )
        assert len(collector._buffer) == 1
        record = collector._buffer[0]
        assert record["sample_type"] == "agent_input"
        assert record["session_id"] == "sess-1"
        assert record["user_query"] == "Hello"
        assert record["system_prompt"] == "Be helpful"

    def test_record_model_output(self, collector):
        collector.record_model_output(
            session_id="sess-1",
            step_number=1,
            raw_response="I can help",
            response_type="text",
            finish_reason="stop",
            tool_calls=[],
            token_usage={"prompt_tokens": 10, "completion_tokens": 5},
            thinking_content=None,
            latency_ms=150.0,
        )
        assert len(collector._buffer) == 1
        record = collector._buffer[0]
        assert record["sample_type"] == "model_output"
        assert record["raw_response"] == "I can help"

    def test_record_tool_call_request(self, collector):
        collector.record_tool_call(
            session_id="sess-1",
            step_number=1,
            tool_name="get_weather",
            tool_params={"city": "Beijing"},
            call_id="call_123",
            tool_result=None,
            error=None,
            duration_ms=0.0,
            phase="request",
        )
        assert len(collector._buffer) == 1
        record = collector._buffer[0]
        assert record["sample_type"] == "tool_call_request"
        assert record["tool_name"] == "get_weather"

    def test_record_tool_call_result(self, collector):
        collector.record_tool_call(
            session_id="sess-1",
            step_number=1,
            tool_name="get_weather",
            tool_params={"city": "Beijing"},
            call_id="call_123",
            tool_result={"temperature": 22},
            error=None,
            duration_ms=45.0,
            phase="result",
        )
        assert len(collector._buffer) == 1
        record = collector._buffer[0]
        assert record["sample_type"] == "tool_call_result"
        assert record["result"] == {"temperature": 22}

    def test_record_intermediate_state(self, collector):
        collector.record_intermediate_state(
            session_id="sess-1",
            step_number=2,
            total_steps=3,
            message_count=5,
            accumulated_tokens={"total": 100},
            tools_called=["get_weather"],
            loop_detected=False,
        )
        assert len(collector._buffer) == 1
        record = collector._buffer[0]
        assert record["sample_type"] == "agent_intermediate_state"
        assert record["total_steps"] == 3

    def test_record_final_response(self, collector):
        collector.record_final_response(
            session_id="sess-1",
            final_response="Done",
            total_duration_ms=1200.0,
            total_llm_calls=3,
            total_tool_calls=2,
            total_tokens=500,
            resolution_status="success",
        )
        assert len(collector._buffer) == 1
        record = collector._buffer[0]
        assert record["sample_type"] == "final_response"
        assert record["final_response"] == "Done"
        assert record["resolution_status"] == "success"

    def test_record_none_values_do_not_crash(self, collector):
        collector.record_agent_input(
            session_id=None,
            user_query=None,
            system_prompt=None,
            history_context=None,
            rag_context=None,
            agent_config=None,
        )
        assert len(collector._buffer) == 1

    def test_record_empty_values_do_not_crash(self, collector):
        collector.record_agent_input(
            session_id="",
            user_query="",
            system_prompt="",
            history_context=[],
            rag_context="",
            agent_config={},
        )
        assert len(collector._buffer) == 1

    def test_record_model_output_with_tool_calls_empty(self, collector):
        collector.record_model_output(
            session_id="sess-1",
            step_number=1,
            raw_response="",
            response_type="tool_calls",
            finish_reason="tool_calls",
            tool_calls=[],
            token_usage={},
            thinking_content="",
            latency_ms=0.0,
        )
        assert len(collector._buffer) == 1

    @pytest.mark.anyio
    async def test_buffer_full_triggers_async_flush(self, collector):
        async def fake_flush():
            collector._buffer.clear()

        with patch.object(collector, "_flush", new=fake_flush):
            for i in range(collector.buffer_size):
                collector.record_agent_input(
                    session_id=f"sess-{i}",
                    user_query=f"query-{i}",
                    system_prompt="test",
                    history_context=[],
                )
            await asyncio.sleep(0.05)
            assert len(collector._buffer) == 0

    def test_disabled_collection_type_does_not_record(self, collector):
        collector.collect_flags["agent_input"] = False
        collector.record_agent_input(
            session_id="sess-1",
            user_query="Hello",
            system_prompt="Hi",
            history_context=[],
        )
        assert len(collector._buffer) == 0

    def test_record_creates_timestamp(self, collector):
        collector.record_agent_input(
            session_id="sess-1",
            user_query="test",
            system_prompt="test",
            history_context=[],
        )
        record = collector._buffer[0]
        assert "create_time" in record
        assert "T" in record["create_time"] and ("+" in record["create_time"] or "-" in record["create_time"][-6:])


class TestSingleton:
    def test_get_collector_returns_singleton(self):
        c1 = get_collector()
        c2 = get_collector()
        assert c1 is c2

    def test_set_collector_injects_mock(self):
        mock = MagicMock(spec=TrainingDataCollector)
        set_collector(mock)
        assert get_collector() is mock

    def test_set_collector_none_resets_singleton(self):
        c1 = get_collector()
        set_collector(None)
        c2 = get_collector()
        assert c2 is not c1


class TestFlush:
    @pytest.mark.anyio
    async def test_flush_writes_to_file(self, collector):
        collector.record_agent_input(
            session_id="sess-1",
            user_query="flush test",
            system_prompt="test",
            history_context=[],
        )
        await collector._flush()

        import glob
        daily_files = glob.glob(os.path.join(collector.output_dir, "daily", "*.jsonl"))
        assert len(daily_files) > 0

        with open(daily_files[0], "r") as f:
            content = f.read()
        assert "flush test" in content

    @pytest.mark.anyio
    async def test_flush_empty_buffer_does_nothing(self, collector):
        result = await collector._flush()
        assert result is None


class TestThreadSafety:
    def test_concurrent_record_writes_no_errors(self, collector):
        import threading

        collector._shutdown_flag = True

        errors = []

        def writer(session_prefix, count):
            try:
                for i in range(count):
                    collector.record_agent_input(
                        session_id=f"{session_prefix}-{i}",
                        user_query=f"query-{i}",
                        system_prompt="test",
                        history_context=[],
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(f"sess-{j}", 50))
            for j in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_record_and_flush(self, collector):
        import threading
        import time

        errors = []

        def writer(session_prefix, count):
            try:
                for i in range(count):
                    collector.record_agent_input(
                        session_id=f"{session_prefix}-{i}",
                        user_query=f"query-{i}",
                        system_prompt="test",
                        history_context=[],
                    )
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def flusher():
            try:
                for _ in range(20):
                    collector._flush_sync()
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)

        writer_thread = threading.Thread(target=writer, args=("sess-w", 100))
        flush_thread = threading.Thread(target=flusher)

        writer_thread.start()
        flush_thread.start()

        writer_thread.join()
        flush_thread.join()

        assert len(errors) == 0

    def test_buffer_lock_prevents_concurrent_modification(self, collector):
        import threading

        collector._shutdown_flag = True
        barrier = threading.Barrier(10)
        errors = []

        def writer(session_prefix):
            try:
                barrier.wait()
                for i in range(100):
                    collector.record_agent_input(
                        session_id=f"{session_prefix}-{i}",
                        user_query=f"query-{i}",
                        system_prompt="test",
                        history_context=[],
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(f"sess-{j}",))
            for j in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
