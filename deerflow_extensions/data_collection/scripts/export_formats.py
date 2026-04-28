"""Multi-format export tool for distilled training data.

Converts aggregated training data into various formats supported by
different distillation frameworks. Currently supports:
  - llamafactory_messages (passthrough)
  - sharegpt
  - alpaca_simple

WING
"""

import json
import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

OutputFormat = Literal["llamafactory_messages", "sharegpt", "alpaca_simple"]


def convert_messages_to_sharegpt(sample: dict) -> dict:
    """Convert messages format to ShareGPT conversations format.

    Role mapping:
      user      -> human
      assistant -> gpt
      tool      -> tool
      system    -> human (first message)

    Preserves tool_calls and tool_call_id at the same nesting level.

    Args:
        sample: A dict containing a "messages" key with a list of
            {"role": ..., "content": ..., ...} entries.

    Returns:
        A dict with "conversations" list in ShareGPT format.
    """
    messages = sample.get("messages", [])
    conversations = []

    role_map = {
        "user": "human",
        "assistant": "gpt",
        "tool": "tool",
        "system": "human",
    }

    for msg in messages:
        role = msg.get("role", "")
        mapped_role = role_map.get(role, role)

        conv: dict = {"from": mapped_role, "value": msg.get("content", "")}

        if "tool_calls" in msg:
            conv["tool_calls"] = msg["tool_calls"]

        if role == "tool" and "tool_call_id" in msg:
            conv["tool_call_id"] = msg["tool_call_id"]

        conversations.append(conv)

    result: dict = {"conversations": conversations}
    if "metadata" in sample:
        result["metadata"] = sample["metadata"]

    return result


def convert_messages_to_alpaca_simple(sample: dict) -> dict | None:
    """Convert messages format to Alpaca instruction/input/output format.

    Suitable only for plain text Q&A. Samples containing tool calls
    return None to indicate they should be skipped.

    System message + first user message -> instruction
    First assistant message              -> output
    The "input" field is left empty.

    Args:
        sample: A dict containing a "messages" key.

    Returns:
        A dict with "instruction", "input", "output" keys, or None if
        the sample contains tool calls or lacks required fields.
    """
    messages = sample.get("messages", [])
    system = ""
    user = ""
    assistant = ""

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            system = msg.get("content", "")
        elif role == "user" and not user:
            user = msg.get("content", "")
        elif role == "assistant" and not assistant:
            if "tool_calls" in msg:
                return None
            assistant = msg.get("content", "")

    if not user or not assistant:
        return None

    instruction = f"{system}\n{user}" if system else user
    return {"instruction": instruction, "input": "", "output": assistant}


def export_dataset(
    input_path: str,
    output_path: str,
    format: OutputFormat = "llamafactory_messages",
) -> None:
    """Export a training dataset to the specified format.

    Reads a JSONL file of messages-format samples, converts each
    sample according to the chosen format, and writes the results
    to a new JSONL file.

    Args:
        input_path:  Path to the aggregated train_data.jsonl file.
        output_path: Path for the output JSONL file.
        format:      Target export format.

    Raises:
        FileNotFoundError: If input_path does not exist.
        json.JSONDecodeError: If a line in the input is not valid JSON.
        KeyError: If an unknown format is passed.
    """
    converter = {
        "llamafactory_messages": lambda s: s,
        "sharegpt": convert_messages_to_sharegpt,
        "alpaca_simple": convert_messages_to_alpaca_simple,
    }

    if format not in converter:
        raise KeyError(f"Unknown export format: {format}. Supported: {list(converter.keys())}")

    convert_fn = converter[format]

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_samples: list[dict] = []
    skipped = 0

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                sample = json.loads(stripped)
            except json.JSONDecodeError as e:
                logger.warning("Skipping malformed JSON line: %s", e)
                skipped += 1
                continue

            try:
                converted = convert_fn(sample)
            except Exception as e:
                logger.warning("Failed to convert sample: %s", e)
                skipped += 1
                continue

            if converted is not None:
                output_samples.append(converted)
            else:
                skipped += 1

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for sample in output_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    total = len(output_samples) + skipped
    logger.info(
        "Export complete: %d written, %d skipped (total %d) -> %s (format: %s)",
        len(output_samples),
        skipped,
        total,
        output_path,
        format,
    )
    print(
        f"Exported {len(output_samples)} samples to {output_path} "
        f"(format: {format}, skipped: {skipped})"
    )
