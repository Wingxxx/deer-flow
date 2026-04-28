from deerflow_extensions.data_collection.scripts.validate_format import FormatValidator


def make_sample(messages):
    return {"messages": messages}


class TestValidate:
    def test_valid_messages_pass_validation(self):
        sample = make_sample([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ])
        issues = FormatValidator.validate(sample)
        assert issues == []

    def test_valid_sample_with_system(self):
        sample = make_sample([
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ])
        issues = FormatValidator.validate(sample)
        assert issues == []

    def test_valid_sample_with_tool_calls(self):
        sample = make_sample([
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "Beijing"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": '{"temperature": 22}',
                "tool_call_id": "call_1",
            },
            {"role": "assistant", "content": "It is 22°C in Beijing."},
        ])
        issues = FormatValidator.validate(sample)
        assert issues == []

    def test_missing_messages_field(self):
        issues = FormatValidator.validate({"not_messages": []})
        assert any("messages" in issue for issue in issues)

    def test_non_dict_sample(self):
        issues = FormatValidator.validate("not_a_dict")
        assert any("messages" in issue for issue in issues)

    def test_empty_messages_list(self):
        sample = make_sample([])
        issues = FormatValidator.validate(sample)
        assert any("non-empty" in issue for issue in issues)

    def test_missing_user_role(self):
        sample = make_sample([
            {"role": "assistant", "content": "Hello"},
        ])
        issues = FormatValidator.validate(sample)
        assert any("user" in issue for issue in issues)

    def test_missing_assistant_role(self):
        sample = make_sample([
            {"role": "user", "content": "Hello"},
        ])
        issues = FormatValidator.validate(sample)
        assert any("assistant" in issue for issue in issues)

    def test_missing_both_user_and_assistant(self):
        sample = make_sample([
            {"role": "system", "content": "Be helpful"},
        ])
        issues = FormatValidator.validate(sample)
        assert any("user" in issue for issue in issues)
        assert any("assistant" in issue for issue in issues)

    def test_tool_calls_in_user_message(self):
        sample = make_sample([
            {
                "role": "user",
                "content": "Hello",
                "tool_calls": [{"id": "call_1"}],
            },
            {"role": "assistant", "content": "Hi"},
        ])
        issues = FormatValidator.validate(sample)
        assert any("tool_calls" in issue and "user" in issue for issue in issues)

    def test_tool_calls_in_system_message(self):
        sample = make_sample([
            {
                "role": "system",
                "content": "Be helpful",
                "tool_calls": [{"id": "call_1"}],
            },
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ])
        issues = FormatValidator.validate(sample)
        assert any("tool_calls" in issue for issue in issues)

    def test_arguments_not_a_string(self):
        sample = make_sample([
            {"role": "user", "content": "Weather?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": {"city": "Beijing"},
                        },
                    }
                ],
            },
        ])
        issues = FormatValidator.validate(sample)
        assert any("arguments" in issue for issue in issues)

    def test_orphaned_tool_call_id(self):
        sample = make_sample([
            {"role": "user", "content": "Weather?"},
            {"role": "assistant", "content": None},
            {
                "role": "tool",
                "content": '{"temperature": 22}',
                "tool_call_id": "call_orphan",
            },
        ])
        issues = FormatValidator.validate(sample)
        assert any("tool_call_id" in issue for issue in issues)

    def test_invalid_role(self):
        sample = make_sample([
            {"role": "user", "content": "Hello"},
            {"role": "chatbot", "content": "Hi"},
        ])
        issues = FormatValidator.validate(sample)
        assert any("invalid role" in issue for issue in issues)

    def test_non_dict_message(self):
        sample = make_sample([
            {"role": "user", "content": "Hello"},
            "not_a_dict",
        ])
        issues = FormatValidator.validate(sample)
        assert any("not a dict" in issue for issue in issues)
