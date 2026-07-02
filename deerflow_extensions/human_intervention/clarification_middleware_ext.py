"""Extended clarification middleware — Clarification Gate for universal human intervention.

Subclasses ClarificationMiddleware to inject `_clarification` key into
ToolMessage.additional_kwargs, enabling the frontend to render rich
interactive widgets instead of plain text.

Implements the Clarification Gate pattern:
- awrap_model_call intercepts LLM responses to detect inline questions
- When an inline question is detected without an ask_clarification tool call,
  automatically injects the tool call to trigger proper human intervention
- Universal — works for ALL skills and scenarios without customization
"""

from __future__ import annotations

import json
import logging
import re
from hashlib import sha256

from langchain_core.messages import AIMessage

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

    # Clarification keywords for inline question detection
    _INLINE_QUESTION_KEYWORDS = frozenset([
        '请问', '您想', '你要', '要不要', '是否',
        '请选择', '选哪个', '哪个',
        '请提供', '请告诉我', '请给出',
        '您希望', '你希望', '确认', '确定',
    ])
    
    # Max recent question entries per thread for dedup
    THREAD_KEYWORDS_MAX = 5
    
    def __init__(self, *args, **kwargs):
        """Initialize with rate limiter and recent question tracker."""
        super().__init__(*args, **kwargs)
        # Rate limiter — read policy from manifest, Fail-Open on error
        self._limiter = None
        self._recent_questions: dict[str, list[set[str]]] = {}
        try:
            import json
            import os
            manifest_path = os.path.join(
                os.path.dirname(__file__),
                "extension_manifest.json",
            )
            if os.path.exists(manifest_path):
                with open(manifest_path) as f:
                    manifest = json.load(f)
                policy = manifest.get("clarification_policy", {})
                from deerflow_extensions.human_intervention.rate_limiter import (
                    ClarificationRateLimiter,
                )
                self._limiter = ClarificationRateLimiter(
                    max_per_turn=policy.get("max_per_turn", 3),
                    cooldown_seconds=policy.get("cooldown_seconds", 30.0),
                )
                logger.info(
                    "[HumanIntervention] Rate limiter initialized: max=%d, cooldown=%.1fs",
                    self._limiter.max_per_turn,
                    self._limiter.cooldown_seconds,
                )
        except Exception:
            logger.warning(
                "[HumanIntervention] Rate limiter init failed, disabled (Fail-Open)"
            )
    
    def _extract_keywords(self, question: str) -> set[str]:
        """Extract keywords from a question for dedup comparison.
    
        Includes:
        - Chinese phrases (len >= 2 characters)
        - English tokens (len >= 3 characters)
        """
        keywords = set()
        n = len(question)
        # Chinese: extract substrings of 2+ characters
        i = 0
        while i < n - 1:
            ch = question[i]
            if '\u4e00' <= ch <= '\u9fff':
                j = i
                while j < n and '\u4e00' <= question[j] <= '\u9fff':
                    j += 1
                if j - i >= 2:
                    keywords.add(question[i:j])
                i = j
            else:
                i += 1
        # English: split by non-alpha and take tokens of len >= 3
        import re as _re
        for token in _re.findall(r'[a-zA-Z]{3,}', question):
            keywords.add(token.lower())
        return keywords
    
    def _has_recent_similar_question(self, thread_id: str, question: str) -> bool:
        """Check if a similar question was recently asked in this thread.
    
        Uses keyword intersection ratio: >= 70% overlap is considered duplicate.
        Fail-Open: returns False on any error.
        """
        try:
            new_keywords = self._extract_keywords(question)
            if not new_keywords:
                return False
            history = self._recent_questions.get(thread_id, [])
            for old_keywords in history:
                if not new_keywords or not old_keywords:
                    continue
                intersection = new_keywords & old_keywords
                # Union-based ratio: |intersection| / max(|new|, |old|)
                ratio = len(intersection) / max(len(new_keywords), len(old_keywords))
                if ratio >= 0.7:
                    logger.debug(
                        "[Clarification Gate] Similar question skipped (ratio=%.2f): %s",
                        ratio, question[:60],
                    )
                    return True
            return False
        except Exception:
            logger.warning("[Clarification Gate] Dedup check error, Fail-Open")
            return False
    
    def _record_question(self, thread_id: str, question: str):
        """Record a question in the recent history for this thread."""
        if thread_id not in self._recent_questions:
            self._recent_questions[thread_id] = []
        keywords = self._extract_keywords(question)
        if keywords:
            self._recent_questions[thread_id].append(keywords)
            # Trim oldest entries
            if len(self._recent_questions[thread_id]) > self.THREAD_KEYWORDS_MAX:
                self._recent_questions[thread_id].pop(0)

    def _build_clarification_structured(self, args: dict, tool_call_id: str = "") -> dict:
        """Build the v1 structured clarification schema for additional_kwargs.

        Returns a dict matching the deerflow/clarification/v1 contract:
        {
            "_schema": "deerflow/clarification/v1",
            "type": "clarification",
            "id": ...,
            "question": ...,
            "clarification_type": ...,
            "context": ...,
            "options": [...],
            "widget_hints": { "input_type": ..., "required": ... },
            "widget_hint": "...",  # legacy, will be removed in v2
        }
        """
        question = args.get("question", "")
        clarification_type = args.get("clarification_type", "missing_info")
        context = args.get("context")
        options = self._normalize_options(args.get("options", []))
        widget_hints = self._infer_widget_hints(clarification_type, options, args)

        structured = {
            "_schema": "deerflow/clarification/v1",
            "type": "clarification",
            "id": tool_call_id,
            "question": question,
            "clarification_type": clarification_type,
            "context": context,
            "options": options,
            "widget_hints": widget_hints,
            "widget_hint": widget_hints.get("input_type", "text"),  # legacy field (v1→v2 transition)
        }
        return structured

    def _normalize_options(self, options, max_options: int = 50):
        """Normalize options, handling Qwen3-Max JSON string serialization.

        Truncates options exceeding max_options (H1 boundary patch).
        """
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except (json.JSONDecodeError, TypeError):
                options = [options]
        if options is None:
            options = []
        elif not isinstance(options, list):
            options = [options]
        # H1: hard truncation at max_options
        if len(options) > max_options:
            extra = len(options) - max_options
            logger.warning(
                "[HumanIntervention] Options truncated: %d > %d",
                len(options), max_options,
            )
            options = options[:max_options] + [f"…及其他 {extra} 项"]
        return options

    def _infer_widget_hints(self, clarification_type: str, options: list, args: dict | None = None) -> dict:
        """Map clarification type to a frontend widget hints dict.

        Returns a dict matching the WidgetHints interface from types.ts.
        Includes risk_level and allow_custom when present in args.
        """
        type_map = {
            "missing_info": {"input_type": "text", "multi_line": False, "required": True},
            "ambiguous_requirement": {"input_type": "text", "multi_line": True, "required": True},
            "approach_choice": {"input_type": "single_choice", "required": True},
            "risk_confirmation": {"input_type": "confirmation", "required": True},
            "suggestion": {"input_type": "single_choice", "required": False},
        }
        hints = type_map.get(clarification_type, {"input_type": "text", "required": True})
        # If options exist and type is text, promote to single_choice or multi_choice
        if options and hints.get("input_type") == "text":
            multi_select = args.get("multi_select", False) if args else False
            if multi_select and len(options) >= 2:
                hints = {**hints, "input_type": "multi_choice"}
            else:
                hints = {**hints, "input_type": "single_choice"}
        # If no options and type is choice-like, fallback to text
        if not options and hints.get("input_type") in ("single_choice", "multi_choice", "confirmation"):
            hints = {**hints, "input_type": "text"}

        # Inject risk_level from args or infer from type
        if args is not None:
            risk_level = args.get("risk_level")
            if risk_level is not None:
                hints["risk_level"] = risk_level
            elif clarification_type == "risk_confirmation" and "risk_level" not in hints:
                hints["risk_level"] = "medium"
            allow_custom = args.get("allow_custom")
            if allow_custom is not None:
                hints["allow_custom"] = bool(allow_custom)

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

    def _emit_clarification_event(self, structured: dict):
        """Emit clarification event for monitoring/collection. Best-effort.

        Encapsulates the try/except data_collection dependency.
        """
        try:
            from deerflow_extensions.data_collection.collector import get_collector
            collector = get_collector()
            collector.record("clarification_triggered", {
                "clarification_type": structured.get("clarification_type"),
                "question": structured.get("question", ""),
                "options_count": len(structured.get("options", [])),
            })
        except Exception:
            pass  # Silent fallback - data collection is best-effort

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
                            self._emit_clarification_event(structured)
            return result

        except Exception:
            logger.exception("[HumanIntervention] Enrichment failed, fallback to plain")
            return super()._handle_clarification(request)

    # ========== Clarification Gate ==========

    def _detect_inline_clarification(self, text: str) -> tuple | None:
        """Detect if AI text contains an inline question that should be ask_clarification.
    
        Detection rules:
        1. Text must contain a sentence ending with "?" or "?"
        2. Text must contain at least one clarification keyword
        3. Extract the last question sentence and any structured options
    
        Returns:
            (question: str, options: list[str]) tuple, or None if no inline question.
        """
        if not text or not isinstance(text, str):
            return None
    
        text = text.strip()
        if not text:
            return None
    
        # Rule 1: Must contain a question mark at end of a sentence
        has_question = '\uff1f' in text or '?' in text
        if not has_question:
            return None
    
        # Rule 2: Must contain clarification keywords
        has_keyword = any(kw in text for kw in self._INLINE_QUESTION_KEYWORDS)
        if not has_keyword:
            return None
    
        # Rule 3: Extract question from TEXT BEFORE options/bullet list
        # This prevents bullet items (e.g. "2. 启动菜单 → 保持默认还是调整？")
        # from being mistaken as the main question.
        opt_marker = re.search(r'\n\s*(?:\d+[\.\)\u3001]|[-•*])\s*', text)
        if opt_marker:
            question_text = text[:opt_marker.start()]
        else:
            question_text = text
        # Clean markdown bold markers
        question_text = question_text.replace('**', '')
        # Extract meaningful question: find the last ？/？ and take text from
        # the sentence boundary (。！\n) before it to the end of question_text.
        # This preserves trailing context (e.g. "功能扩展？请您选择：" instead of
        # just "功能扩展？") and avoids splitting multi-sentence questions.
        last_q_pos = -1
        for ch in ('\uff1f', '?'):
            pos = question_text.rfind(ch)
            if pos > last_q_pos:
                last_q_pos = pos
        if last_q_pos >= 0:
            # Find sentence boundary before the last question
            sentence_start = last_q_pos
            while sentence_start > 0 \
                    and question_text[sentence_start - 1] not in '\u3002\uff01\n\r！':
                sentence_start -= 1
            question = question_text[sentence_start:].strip()
        else:
            question = question_text.strip()
    
        # Rule 4: Extract options if present (numbered or bullet list)
        options = []
        opt_pattern = re.findall(
            r'(?:^|\n)\s*(?:\d+[\.\)\u3001]|[-•*])\s*(.+)',
            text,
            re.MULTILINE,
        )
        if opt_pattern:
            options = [opt.strip() for opt in opt_pattern if opt.strip()]
            
        # Filter out non-actionable items:
        # 1. Pure dash separators (--, ---)
        # 2. Markdown bold/informational text (containing **)
        # 3. ANY option containing ？/？ is a descriptive prompt, not a choice.
        #    Real choice options are concise (e.g. "终端关联", "部门关联").
        #    If any option contains ？/？, the extraction is unreliable.
        all_parsed = list(options)
        has_q_options = any(
            ('\uff1f' in opt or '?' in opt)
            for opt in all_parsed
        )
        if has_q_options:
            # ？-containing option detected → extraction unreliable
            options = []
        else:
            # Apply remaining filters only when no ？/？ options found
            options = [
                opt for opt in options
                if not re.match(r'^-+$', opt)
                and '**' not in opt
            ]
            
        return question, options

    # ========== Shared Gate Logic ==========

    def _apply_clarification_gate(self, response):
        """Shared gate logic for sync and async paths.

        Detects inline questions in LLM responses and injects
        ask_clarification tool calls. Fail-Closed: any exception
        logs and returns the original response unmodified.
        """
        try:
            if not response or not response.result:
                return response
            ai_msg = response.result[0]
            if not isinstance(ai_msg, AIMessage):
                return response

            existing_tcs = getattr(ai_msg, 'tool_calls', None) or []
            if any(tc.get('name') == 'ask_clarification' for tc in existing_tcs):
                # Still clear content if it contains duplicate question text
                text = getattr(ai_msg, 'content', '') or ''
                if isinstance(text, str) and self._detect_inline_clarification(text):
                    ai_msg.content = ''
                return response

            text = getattr(ai_msg, 'content', '') or ''
            q_result = self._detect_inline_clarification(text)
            if not q_result:
                return response

            question, options = q_result

            # Rate limiter check (Fail-Open: True if limiter is None or error)
            thread_id = ""
            try:
                if hasattr(request, 'config') and request.config:
                    thread_id = request.config.get('configurable', {}).get('thread_id', '')
            except Exception:
                pass

            if self._limiter and not self._limiter.allow(thread_id):
                logger.warning(
                    "[Clarification Gate] Rate limited (thread=%s): %s",
                    thread_id, question[:60],
                )
                return response  # Keep content, skip injection

            if self._has_recent_similar_question(thread_id, question):
                logger.info(
                    "[Clarification Gate] Dedup skipped (thread=%s): %s",
                    thread_id, question[:60],
                )
                return response  # Keep content, skip injection

            self._record_question(thread_id, question)

            new_tc = {
                'name': 'ask_clarification',
                'args': {
                    'question': question,
                    'clarification_type': 'missing_info',
                    'options': options or [],
                },
                'id': f'clarification-gate-{sha256(question.encode()).hexdigest()[:16]}',
                'type': 'tool_call',
            }
            ai_msg.tool_calls = existing_tcs + [new_tc]
            ai_msg.content = ''

            logger.info(
                '[Clarification Gate] Inline question detected - '
                'injected ask_clarification: %s',
                question[:120],
            )

        except Exception:
            logger.exception('[Clarification Gate] Error')
        return response

    def wrap_model_call(self, request, handler):
        """Sync version — mirrors awrap_model_call."""
        response = handler(request)
        return self._apply_clarification_gate(response)

    async def awrap_model_call(self, request, handler):
        """Async version — delegates to shared _apply_clarification_gate."""
        response = await handler(request)
        return self._apply_clarification_gate(response)
