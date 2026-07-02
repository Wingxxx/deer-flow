"""Extended clarification middleware that attaches structured _clarification data to ToolMessage.

Subclasses ClarificationMiddleware to inject `_clarification` key into
ToolMessage.additional_kwargs, enabling the frontend to render rich
interactive widgets instead of plain text.
"""

from __future__ import annotations

import json
import logging

from deerflow.agents.middlewares.clarification_middleware import (
    ClarificationMiddleware,
)

logger = logging.getLogger(__name__)


class HumanInterventionClarificationMiddleware(ClarificationMiddleware):
    """Subclasses ClarificationMiddleware to enrich ToolMessage with structured _clarification data.

    Follows the zero-intrusion pattern:
    - Inherits all base behavior via super()
    - Enriches ToolMessage.additional_kwargs with a '_clarification' key
    - Falls back gracefully on any error
    """

    def _build_clarification_structured(self, args: dict) -> dict:
        """Build the v1 structured clarification schema for additional_kwargs.

        Returns a dict matching the deerflow/clarification/v1 contract:
        {
            "_schema": "deerflow/clarification/v1",
            "question": ...,
            "clarification_type": ...,
            "context": ...,
            "options": [...],
            "widget_hints": { "input_type": ..., "required": ... }
        }
        """
        question = args.get("question", "")
        clarification_type = args.get("clarification_type", "missing_info")
        context = args.get("context")
        options = self._normalize_options(args.get("options", []))
        widget_hints = self._infer_widget_hints(clarification_type, options)

        return {
            "_schema": "deerflow/clarification/v1",
            "question": question,
            "clarification_type": clarification_type,
            "context": context,
            "options": options,
            "widget_hints": widget_hints,
        }

    def _normalize_options(self, options):
        """Normalize options, handling Qwen3-Max JSON string serialization."""
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except (json.JSONDecodeError, TypeError):
                options = [options]
        if options is None:
            options = []
        elif not isinstance(options, list):
            options = [options]
        return options

    def _infer_widget_hints(self, clarification_type: str, options: list) -> dict:
        """Map clarification type to a frontend widget hints dict.

        Returns a dict matching the WidgetHints interface from types.ts.
        """
        type_map = {
            "missing_info": {"input_type": "text", "multi_line": False, "required": True},
            "ambiguous_requirement": {"input_type": "text", "multi_line": True, "required": True},
            "approach_choice": {"input_type": "single_choice", "required": True},
            "risk_confirmation": {"input_type": "confirmation", "required": True},
            "suggestion": {"input_type": "single_choice", "required": False},
        }
        hints = type_map.get(clarification_type, {"input_type": "text", "required": True})
        # If options exist and type is text, promote to single_choice
        if options and hints.get("input_type") == "text":
            hints = {**hints, "input_type": "single_choice"}
        # If no options and type is choice-like, fallback to text
        if not options and hints.get("input_type") in ("single_choice", "multi_choice", "confirmation"):
            hints = {**hints, "input_type": "text"}
        return hints

    def _is_duplicate(self, tool_msg) -> bool:
        """Check whether a ToolMessage already carries _clarification data.

        Prevents checkpoint replay from injecting duplicate structured data.
        """
        try:
            return (
                hasattr(tool_msg, "additional_kwargs")
                and tool_msg.additional_kwargs is not None
                and "_clarification" in tool_msg.additional_kwargs
            )
        except Exception:
            return False

    def _handle_clarification(self, request):
        """Handle clarification request, enriching result with structured data.

        Calls super()._handle_clarification() to let the parent build the
        base Command/ToolMessage, then injects the '_clarification' key into
        ToolMessage.additional_kwargs. Falls back to the parent on error.
        """
        try:
            # Let the parent build the Command/ToolMessage
            result = super()._handle_clarification(request)

            args = request.tool_call.get("args", {})
            structured = self._build_clarification_structured(args)

            # Attach structured data to the ToolMessage
            if hasattr(result, "update") and result.update:
                messages = result.update.get("messages", [])
                for msg in messages:
                    if hasattr(msg, "additional_kwargs") and msg.additional_kwargs is not None:
                        if not self._is_duplicate(msg):
                            msg.additional_kwargs["_clarification"] = structured
                            logger.info(
                                "Attached _clarification to ToolMessage (type=%s)",
                                structured.get("clarification_type"),
                            )
            return result

        except Exception:
            logger.exception("[HumanIntervention] Enrichment failed, fallback to plain")
            return super()._handle_clarification(request)
