"""Tool Output Enrichment extension.

Provides ``enrich_result`` — a drop-in replacement for the core middleware's
``_enrich_result`` function.  The extension is installed via monkey-patch in
``startup.py``, following the zero-intrusion pattern established by
``data_collection`` and ``topic_guardrail``.

Public API:
    enrich_result(result, config) → ToolMessage | Command
"""

from __future__ import annotations

import logging
from typing import Any

from deerflow_extensions.tool_output_enrichment.enrichment_pipeline import enrich
from langchain_core.messages import ToolMessage

from deerflow.config.tool_output_config import ToolOutputConfig

logger = logging.getLogger(__name__)


def _message_text(content: Any) -> str | None:
    """Extract a plain-text representation from a ToolMessage content field.

    Returns ``None`` for non-string / multimodal content so the caller
    can skip enrichment (images, structured blocks, etc.).
    """
    if isinstance(content, str):
        return content
    if content is None:
        return None
    if isinstance(content, list):
        pieces: list[str] = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                pieces.append(part["text"])
            else:
                return None
        return "\n".join(pieces) if pieces else None
    return None


def _enrich_tool_message(msg: ToolMessage, config: ToolOutputConfig) -> ToolMessage:
    """Pre-process tool message content to add JSON array summary metadata."""
    if not config.preprocess_json:
        return msg
    tool_name = msg.name or "unknown"
    if tool_name in config.exempt_tools:
        return msg
    text = _message_text(msg.content)
    if text is None:
        return msg
    enriched_text = enrich(text)
    if enriched_text == text:
        return msg
    logger.info(
        "Enriched %s output with JSON array summary (%d chars + %d original chars)",
        tool_name,
        len(enriched_text) - len(text),
        len(text),
    )
    update: dict[str, Any] = {"content": enriched_text}
    if getattr(msg, "response_metadata", None):
        update["response_metadata"] = dict(msg.response_metadata)
    if getattr(msg, "additional_kwargs", None):
        update["additional_kwargs"] = dict(msg.additional_kwargs)
    return msg.model_copy(update=update)


def enrich_result(
    result: ToolMessage | Any,
    config: ToolOutputConfig,
) -> ToolMessage | Any:
    """Enrich tool results with JSON array summaries, independent of budget.

    Runs before the budget gate so enrichment applies even to outputs that
    are under the externalize/fallback thresholds.
    Returns the original *result* unchanged if enrichment is disabled,
    the tool is exempt, or no JSON array content is found.
    """
    from dataclasses import replace as dc_replace

    if not config.preprocess_json:
        return result
    if isinstance(result, ToolMessage):
        return _enrich_tool_message(result, config)
    update = getattr(result, "update", None)
    if not isinstance(update, dict):
        return result
    messages = update.get("messages")
    if not isinstance(messages, list):
        return result
    new_messages: list[Any] = []
    changed = False
    for msg in messages:
        if isinstance(msg, ToolMessage):
            enriched = _enrich_tool_message(msg, config)
            if enriched is not msg:
                changed = True
            new_messages.append(enriched)
        else:
            new_messages.append(msg)
    if not changed:
        return result
    return dc_replace(result, update={**update, "messages": new_messages})
