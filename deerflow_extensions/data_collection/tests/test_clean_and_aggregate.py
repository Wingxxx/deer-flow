import json

from deerflow_extensions.data_collection.scripts.clean_and_aggregate import (
    DataCleaner,
    DataAggregator,
)


def make_raw(
    session_id="sess-1",
    user_query="Hello",
    raw_response="Hi there!",
    sample_type="agent_input",
    create_time="2026-01-01T00:00:00",
    system_prompt="",
    tool_calls=None,
    error=None,
    call_id=None,
    result=None,
    response_type="text",
):
    d = {
        "session_id": session_id,
        "user_query": user_query,
        "raw_response": raw_response,
        "sample_type": sample_type,
        "create_time": create_time,
        "system_prompt": system_prompt,
    }
    if tool_calls is not None:
        d["tool_calls"] = tool_calls
    if error is not None:
        d["error"] = error
    if call_id is not None:
        d["call_id"] = call_id
    if result is not None:
        d["result"] = result
    if response_type:
        d["response_type"] = response_type
    return d


class TestDataCleaner:
    def test_deduplicate_removes_duplicates(self):
        samples = [
            make_raw(user_query="Hello", raw_response="Hi"),
            make_raw(user_query="Hello", raw_response="Hi"),
            make_raw(user_query="Bye", raw_response="Goodbye"),
        ]
        result = DataCleaner.deduplicate(samples)
        assert len(result) == 2

    def test_deduplicate_keeps_unique(self):
        samples = [
            make_raw(user_query="Hello", raw_response="Hi"),
            make_raw(user_query="Bye", raw_response="Goodbye"),
            make_raw(user_query="How are you?", raw_response="Fine"),
        ]
        result = DataCleaner.deduplicate(samples)
        assert len(result) == 3

    def test_deduplicate_empty_key_not_removed(self):
        samples = [
            make_raw(user_query="", raw_response=""),
            make_raw(user_query="", raw_response=""),
        ]
        result = DataCleaner.deduplicate(samples)
        assert len(result) == 2

    def test_filter_incomplete_removes_missing_session(self):
        samples = [
            make_raw(session_id=""),
            make_raw(session_id="sess-1"),
        ]
        result = DataCleaner.filter_incomplete(samples)
        assert len(result) == 1
        assert result[0]["session_id"] == "sess-1"

    def test_filter_incomplete_removes_missing_user_query(self):
        samples = [
            make_raw(user_query=""),
            make_raw(user_query="Hello"),
        ]
        result = DataCleaner.filter_incomplete(samples)
        assert len(result) == 1

    def test_filter_incomplete_removes_missing_raw_response(self):
        samples = [
            make_raw(raw_response=""),
            make_raw(raw_response="Hi"),
        ]
        result = DataCleaner.filter_incomplete(samples)
        assert len(result) == 1

    def test_filter_short_response_default_min(self):
        samples = [
            make_raw(raw_response="Hi"),
            make_raw(raw_response="Hello, how can I help you today?"),
        ]
        result = DataCleaner.filter_short_response(samples)
        assert len(result) == 1
        assert result[0]["raw_response"] == "Hello, how can I help you today?"

    def test_filter_short_response_custom_min(self):
        samples = [
            make_raw(raw_response="Hello"),
            make_raw(raw_response="Hi there! This is a longer response."),
        ]
        result = DataCleaner.filter_short_response(samples, min_chars=10)
        assert len(result) == 1
        assert "longer" in result[0]["raw_response"]

    def test_filter_short_response_empty_string(self):
        samples = [
            make_raw(raw_response=""),
            make_raw(raw_response="Hello"),
        ]
        result = DataCleaner.filter_short_response(samples)
        assert len(result) == 1

    def test_filter_error_cases_removes_samples_with_error(self):
        samples = [
            make_raw(error="APIError: timeout"),
            make_raw(error=""),
            make_raw(error=None),
        ]
        result = DataCleaner.filter_error_cases(samples)
        assert len(result) == 2

    def test_clean_pipeline(self):
        samples = [
            make_raw(error="timeout"),
            make_raw(user_query="", raw_response="Hi"),
            make_raw(user_query="Hello", raw_response="Hi"),
            make_raw(user_query="Hello", raw_response="Hi"),
            make_raw(user_query="How", raw_response="A"),
            make_raw(user_query="Bye", raw_response="Goodbye!"),
        ]
        result = DataCleaner.clean(samples)
        assert len(result) == 1
        assert result[0]["raw_response"] == "Goodbye!"


class TestDataAggregator:
    def test_aggregate_session_groups_by_session(self):
        samples = [
            make_raw(sample_type="agent_input", create_time="2026-01-01T00:00:00"),
            make_raw(
                session_id="sess-1",
                sample_type="model_output",
                create_time="2026-01-01T00:00:01",
            ),
            make_raw(
                session_id="sess-2",
                sample_type="agent_input",
                create_time="2026-01-01T00:00:00",
            ),
            make_raw(
                session_id="sess-2",
                sample_type="model_output",
                create_time="2026-01-01T00:00:01",
            ),
        ]
        result = DataAggregator.aggregate_session(samples)
        assert len(result) == 2

    def test_aggregate_session_sorts_by_create_time(self):
        samples = [
            make_raw(sample_type="model_output", create_time="2026-01-01T00:00:02"),
            make_raw(sample_type="agent_input", create_time="2026-01-01T00:00:01"),
        ]
        result = DataAggregator.aggregate_session(samples)
        assert len(result) == 1
        messages = result[0]["messages"]
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_aggregate_incomplete_session_returns_none(self):
        samples = [
            make_raw(sample_type="agent_input"),
        ]
        result = DataAggregator.aggregate_session(samples)
        assert len(result) == 0

    def test_build_training_sample_agent_input_only(self):
        samples = [
            make_raw(sample_type="agent_input"),
        ]
        result = DataAggregator._build_training_sample(samples)
        assert result is None

    def test_build_training_sample_full_conversation(self):
        samples = [
            make_raw(sample_type="agent_input", system_prompt="Be helpful"),
            make_raw(sample_type="model_output", raw_response="Hello! How can I help?"),
        ]
        result = DataAggregator._build_training_sample(samples)
        assert result is not None
        messages = result["messages"]
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Be helpful"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "Hello! How can I help?"

    def test_build_training_sample_with_tool_calls(self):
        samples = [
            make_raw(sample_type="agent_input"),
            make_raw(
                sample_type="model_output",
                raw_response="",
                response_type="tool_calls",
                tool_calls=[
                    {
                        "call_id": "call_1",
                        "tool_name": "get_weather",
                        "arguments": {"city": "Beijing"},
                    }
                ],
            ),
        ]
        result = DataAggregator._build_training_sample(samples)
        assert result is not None
        messages = result["messages"]
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] is None
        assert "tool_calls" in messages[1]
        assert messages[1]["tool_calls"][0]["function"]["name"] == "get_weather"

    def test_build_training_sample_with_tool_result(self):
        samples = [
            make_raw(sample_type="agent_input"),
            make_raw(
                sample_type="model_output",
                raw_response="",
                response_type="tool_calls",
                tool_calls=[
                    {
                        "call_id": "call_1",
                        "tool_name": "get_weather",
                        "arguments": {"city": "Beijing"},
                    }
                ],
            ),
            make_raw(
                session_id="sess-1",
                user_query="Hello",
                raw_response="",
                sample_type="tool_call_result",
                call_id="call_1",
                result={"temperature": 22},
            ),
            make_raw(
                sample_type="model_output",
                raw_response="It is 22°C in Beijing.",
                response_type="text",
            ),
        ]
        result = DataAggregator._build_training_sample(samples)
        assert result is not None
        messages = result["messages"]
        tool_msg = [m for m in messages if m["role"] == "tool"]
        assert len(tool_msg) == 1
        assert tool_msg[0]["tool_call_id"] == "call_1"

    def test_build_training_sample_metadata(self):
        samples = [
            make_raw(sample_type="agent_input", session_id="sess-meta"),
            make_raw(
                session_id="sess-meta",
                sample_type="model_output",
                raw_response="Hi",
            ),
        ]
        result = DataAggregator._build_training_sample(samples)
        assert result is not None
        assert result["metadata"]["session_id"] == "sess-meta"
        assert "create_time" in result["metadata"]

    def test_aggregate_session_empty_input(self):
        result = DataAggregator.aggregate_session([])
        assert result == []
