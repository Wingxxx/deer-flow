import json
import os
import tempfile

import pytest

from deerflow_extensions.data_collection.scripts.export_formats import (
    convert_messages_to_sharegpt,
    convert_messages_to_alpaca_simple,
    export_dataset,
    OutputFormat,
)


def make_sample(messages, metadata=None):
    sample = {"messages": messages}
    if metadata:
        sample["metadata"] = metadata
    return sample


class TestConvertToShareGPT:
    def test_basic_conversion(self):
        sample = make_sample([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ])
        result = convert_messages_to_sharegpt(sample)
        assert "conversations" in result
        assert len(result["conversations"]) == 2
        assert result["conversations"][0] == {"from": "human", "value": "Hello"}
        assert result["conversations"][1] == {"from": "gpt", "value": "Hi there!"}

    def test_with_system_message(self):
        sample = make_sample([
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ])
        result = convert_messages_to_sharegpt(sample)
        assert result["conversations"][0] == {"from": "human", "value": "Be helpful"}

    def test_with_tool_messages(self):
        sample = make_sample([
            {"role": "user", "content": "Weather?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city":"Beijing"}'}}],
            },
            {"role": "tool", "content": '{"temp":22}', "tool_call_id": "call_1"},
            {"role": "assistant", "content": "It is 22°C."},
        ])
        result = convert_messages_to_sharegpt(sample)
        conversations = result["conversations"]
        assert conversations[0] == {"from": "human", "value": "Weather?"}
        assert "tool_calls" in conversations[1]
        assert conversations[2] == {"from": "tool", "value": '{"temp":22}', "tool_call_id": "call_1"}

    def test_preserves_metadata(self):
        sample = make_sample(
            [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}],
            metadata={"session_id": "abc123"},
        )
        result = convert_messages_to_sharegpt(sample)
        assert result["metadata"] == {"session_id": "abc123"}

    def test_empty_messages(self):
        sample = make_sample([])
        result = convert_messages_to_sharegpt(sample)
        assert result["conversations"] == []


class TestConvertToAlpacaSimple:
    def test_basic_conversion(self):
        sample = make_sample([
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI is artificial intelligence."},
        ])
        result = convert_messages_to_alpaca_simple(sample)
        assert result is not None
        assert result["instruction"] == "What is AI?"
        assert result["input"] == ""
        assert result["output"] == "AI is artificial intelligence."

    def test_with_system_prompt(self):
        sample = make_sample([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI is artificial intelligence."},
        ])
        result = convert_messages_to_alpaca_simple(sample)
        assert result is not None
        assert "You are a helpful assistant." in result["instruction"]
        assert "What is AI?" in result["instruction"]

    def test_skips_tool_call_samples(self):
        sample = make_sample([
            {"role": "user", "content": "Weather?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}],
            },
        ])
        result = convert_messages_to_alpaca_simple(sample)
        assert result is None

    def test_returns_none_without_user(self):
        sample = make_sample([
            {"role": "assistant", "content": "Hello"},
        ])
        result = convert_messages_to_alpaca_simple(sample)
        assert result is None

    def test_returns_none_without_assistant(self):
        sample = make_sample([
            {"role": "user", "content": "Hello"},
        ])
        result = convert_messages_to_alpaca_simple(sample)
        assert result is None

    def test_empty_messages_returns_none(self):
        sample = make_sample([])
        result = convert_messages_to_alpaca_simple(sample)
        assert result is None


class TestExportDataset:
    def create_input_file(self, directory, samples):
        path = os.path.join(directory, "input.jsonl")
        with open(path, "w") as f:
            for s in samples:
                f.write(json.dumps(s) + "\n")
        return path

    def test_export_passthrough_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            samples = [
                make_sample([{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]),
                make_sample([{"role": "user", "content": "Bye"}, {"role": "assistant", "content": "Goodbye"}]),
            ]
            input_path = self.create_input_file(tmpdir, samples)
            output_path = os.path.join(tmpdir, "output.jsonl")

            export_dataset(input_path, output_path, format="llamafactory_messages")

            exported = []
            with open(output_path, "r") as f:
                for line in f:
                    exported.append(json.loads(line))
            assert len(exported) == 2
            assert exported[0] == samples[0]

    def test_export_sharegpt_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            samples = [
                make_sample([{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]),
            ]
            input_path = self.create_input_file(tmpdir, samples)
            output_path = os.path.join(tmpdir, "output.jsonl")

            export_dataset(input_path, output_path, format="sharegpt")

            exported = []
            with open(output_path, "r") as f:
                for line in f:
                    exported.append(json.loads(line))
            assert len(exported) == 1
            assert "conversations" in exported[0]

    def test_export_alpaca_skips_tool_samples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            samples = [
                make_sample([{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]),
                make_sample([
                    {"role": "user", "content": "Weather?"},
                    {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}]},
                ]),
            ]
            input_path = self.create_input_file(tmpdir, samples)
            output_path = os.path.join(tmpdir, "output.jsonl")

            export_dataset(input_path, output_path, format="alpaca_simple")

            exported = []
            with open(output_path, "r") as f:
                for line in f:
                    exported.append(json.loads(line))
            assert len(exported) == 1
            assert exported[0]["instruction"] == "Hi"

    def test_export_unknown_format_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = self.create_input_file(tmpdir, [make_sample([])])
            output_path = os.path.join(tmpdir, "output.jsonl")
            with pytest.raises(KeyError):
                export_dataset(input_path, output_path, format="unknown_format")

    def test_export_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            export_dataset("/nonexistent/input.jsonl", "/tmp/output.jsonl")

    def test_export_skips_malformed_json_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.jsonl")
            with open(input_path, "w") as f:
                f.write('{"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]}\n')
                f.write("not_valid_json\n")
                f.write('{"messages": [{"role": "user", "content": "Bye"}, {"role": "assistant", "content": "Goodbye"}]}\n')

            output_path = os.path.join(tmpdir, "output.jsonl")
            export_dataset(input_path, output_path, format="llamafactory_messages")

            exported = []
            with open(output_path, "r") as f:
                for line in f:
                    exported.append(json.loads(line))
            assert len(exported) == 2

    def test_export_empty_lines_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.jsonl")
            with open(input_path, "w") as f:
                f.write('{"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]}\n')
                f.write("\n")
                f.write('{"messages": [{"role": "user", "content": "Bye"}, {"role": "assistant", "content": "Goodbye"}]}\n')

            output_path = os.path.join(tmpdir, "output.jsonl")
            export_dataset(input_path, output_path, format="llamafactory_messages")

            exported = []
            with open(output_path, "r") as f:
                for line in f:
                    exported.append(json.loads(line))
            assert len(exported) == 2
