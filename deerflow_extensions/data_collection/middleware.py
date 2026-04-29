import logging
import time
from typing import Any

from deerflow_extensions.data_collection.collector import get_collector
from deerflow_extensions.data_collection.config import load_config
from deerflow_extensions.data_collection.role_parser import parse_messages
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


def _get_thread_id_from_state_or_runtime(state: dict, runtime: Runtime | None = None) -> str:
    """Extract thread_id from state or runtime context.

    Tries multiple sources to find thread_id:
    1. runtime.context.get("thread_id") if runtime is available
    2. state.get("config", {}).get("configurable", {}).get("thread_id")
    3. get_config().get("configurable", {}).get("thread_id")

    Returns "unknown" if no thread_id is found.
    """
    thread_id = "unknown"

    if runtime is not None and runtime.context:
        thread_id = runtime.context.get("thread_id") or "unknown"
        if thread_id != "unknown":
            return thread_id

    if isinstance(state, dict):
        config = state.get("config")
        if isinstance(config, dict):
            configurable = config.get("configurable")
            if isinstance(configurable, dict):
                thread_id = configurable.get("thread_id") or "unknown"

    return thread_id


class DataCollectionMiddleware(AgentMiddleware):
    def __init__(self):
        super().__init__()
        try:
            self.collector = get_collector()
        except Exception as e:
            logger.debug("[DataCollection] Failed to get collector: %s", e)
            self.collector = None

        try:
            config = load_config()
            self.role_extract_mode = config.get("role_extract_mode", "auto")
        except Exception as e:
            logger.debug("[DataCollection] Failed to load config: %s", e)
            self.role_extract_mode = "auto"

        self._step_counts: dict[str, int] = {}
        self._session_start: dict[str, float] = {}
        self._llm_calls: dict[str, int] = {}
        self._tool_calls: dict[str, int] = {}
        self._accumulated_tokens: dict[str, dict] = {}

    def before_model(self, state: dict, runtime: Runtime | None = None) -> dict:
        if self.collector is None:
            return state

        try:
            session_id = _get_thread_id_from_state_or_runtime(state, runtime)
            messages = state.get("messages", [])

            parsed = parse_messages(messages, mode=self.role_extract_mode)
            user_query = parsed["user_query"]
            system_prompt = parsed["system_prompt"]
            history = parsed["history"]

            self.collector.record_agent_input(
                session_id=session_id,
                user_query=user_query,
                system_prompt=system_prompt,
                history_context=history[-4:],
                rag_context=state.get("rag_context", ""),
            )

            if session_id not in self._step_counts:
                self._step_counts[session_id] = 0
                self._session_start[session_id] = time.monotonic()
                self._llm_calls[session_id] = 0
                self._tool_calls[session_id] = 0
                self._accumulated_tokens[session_id] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }

        except Exception as e:
            logger.debug("[DataCollection] before_model error: %s", e)

        return state

    async def abefore_model(self, state: dict, runtime: Runtime | None = None) -> dict:
        return self.before_model(state, runtime)

    def after_model(self, state: dict, runtime: Runtime | None = None) -> dict:
        if self.collector is None:
            return state

        try:
            session_id = _get_thread_id_from_state_or_runtime(state, runtime)
            messages = state.get("messages", [])
            if not messages:
                return state

            last = messages[-1]
            step_number = self._step_counts.get(session_id, 0)
            self._step_counts[session_id] = step_number + 1
            self._llm_calls[session_id] = self._llm_calls.get(session_id, 0) + 1

            raw_tool_calls = []
            if hasattr(last, "additional_kwargs"):
                raw_tool_calls = last.additional_kwargs.get("tool_calls", [])

            usage = {}
            if hasattr(last, "response_metadata"):
                usage = last.response_metadata.get("token_usage", {})

            self.collector.record_model_output(
                session_id=session_id,
                step_number=step_number,
                raw_response=getattr(last, "content", "") or "",
                response_type="tool_calls" if raw_tool_calls else "text",
                finish_reason=(
                    last.additional_kwargs.get("finish_reason", "")
                    if hasattr(last, "additional_kwargs")
                    else ""
                ),
                tool_calls=[
                    {
                        "tool_name": tc.get("function", {}).get("name", ""),
                        "call_id": tc.get("id", ""),
                        "arguments": tc.get("function", {}).get("arguments", {}),
                    }
                    for tc in raw_tool_calls
                ],
                token_usage=usage,
                thinking_content=getattr(last, "thinking_content", ""),
                latency_ms=0.0,
            )

            tools_called = [
                tc.get("function", {}).get("name", "") for tc in raw_tool_calls
            ]
            self.collector.record_intermediate_state(
                session_id=session_id,
                step_number=step_number,
                total_steps=state.get("max_steps", 25),
                message_count=len(messages),
                accumulated_tokens=self._accumulated_tokens.get(session_id, {}),
                tools_called=tools_called,
            )

        except Exception as e:
            logger.debug("[DataCollection] after_model error: %s", e)

        return state

    async def aafter_model(self, state: dict, runtime: Runtime | None = None) -> dict:
        return self.after_model(state, runtime)

    def wrap_tool_call(self, tool_call: Any, handler: Any) -> Any:
        if self.collector is None:
            return handler(tool_call)

        session_id = "unknown"
        tool_name = ""
        tool_params = {}
        call_id = ""

        try:
            tc = getattr(tool_call, "tool_call", {}) or {}
            metadata = tc.get("metadata", {}) or {}
            session_id = metadata.get("session_id", "unknown")
            tool_name = tc.get("name", "unknown")
            tool_params = tc.get("args", {})
            call_id = tc.get("id", "") or str(id(tool_call))

            self._tool_calls[session_id] = (
                self._tool_calls.get(session_id, 0) + 1
            )

            self.collector.record_tool_call(
                session_id=session_id,
                step_number=self._step_counts.get(session_id, 0),
                tool_name=tool_name,
                tool_params=tool_params,
                call_id=call_id,
                phase="request",
            )
        except Exception as e:
            logger.debug("[DataCollection] wrap_tool_call request error: %s", e)

        start = time.monotonic()
        error = None
        result = None
        try:
            result = handler(tool_call)
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = (time.monotonic() - start) * 1000
            try:
                self.collector.record_tool_call(
                    session_id=session_id,
                    step_number=self._step_counts.get(session_id, 0),
                    tool_name=tool_name,
                    tool_params=tool_params,
                    call_id=call_id,
                    tool_result=(
                        getattr(result, "content", None) if result else None
                    ),
                    error=error,
                    duration_ms=duration,
                    phase="result",
                )
            except Exception as e:
                logger.debug(
                    "[DataCollection] wrap_tool_call result error: %s", e
                )

        return result

    async def awrap_tool_call(self, tool_call: Any, handler: Any) -> Any:
        if self.collector is None:
            return handler(tool_call)

        session_id = "unknown"
        tool_name = ""
        tool_params = {}
        call_id = ""

        try:
            tc = getattr(tool_call, "tool_call", {}) or {}
            metadata = tc.get("metadata", {}) or {}
            session_id = metadata.get("session_id", "unknown")
            tool_name = tc.get("name", "unknown")
            tool_params = tc.get("args", {})
            call_id = tc.get("id", "") or str(id(tool_call))

            self._tool_calls[session_id] = (
                self._tool_calls.get(session_id, 0) + 1
            )

            self.collector.record_tool_call(
                session_id=session_id,
                step_number=self._step_counts.get(session_id, 0),
                tool_name=tool_name,
                tool_params=tool_params,
                call_id=call_id,
                phase="request",
            )
        except Exception as e:
            logger.debug("[DataCollection] awrap_tool_call request error: %s", e)

        start = time.monotonic()
        error = None
        result = None
        try:
            result = await handler(tool_call)
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = (time.monotonic() - start) * 1000
            try:
                self.collector.record_tool_call(
                    session_id=session_id,
                    step_number=self._step_counts.get(session_id, 0),
                    tool_name=tool_name,
                    tool_params=tool_params,
                    call_id=call_id,
                    tool_result=(
                        getattr(result, "content", None) if result else None
                    ),
                    error=error,
                    duration_ms=duration,
                    phase="result",
                )
            except Exception as e:
                logger.debug(
                    "[DataCollection] awrap_tool_call result error: %s", e
                )

        return result

    def after_agent(self, state: dict, runtime: Runtime | None = None) -> dict:
        if self.collector is None:
            return state

        try:
            session_id = _get_thread_id_from_state_or_runtime(state, runtime)
            messages = state.get("messages", [])
            final_msg = messages[-1] if messages else None

            total_duration = (
                time.monotonic()
                - self._session_start.get(session_id, time.monotonic())
            ) * 1000

            self.collector.record_final_response(
                session_id=session_id,
                final_response=(
                    getattr(final_msg, "content", "") if final_msg else ""
                ),
                total_duration_ms=total_duration,
                total_llm_calls=self._llm_calls.get(session_id, 0),
                total_tool_calls=self._tool_calls.get(session_id, 0),
                total_tokens=self._accumulated_tokens.get(session_id, {}).get(
                    "total_tokens", 0
                ),
                resolution_status="completed",
            )

            for d in [
                self._step_counts,
                self._session_start,
                self._llm_calls,
                self._tool_calls,
                self._accumulated_tokens,
            ]:
                d.pop(session_id, None)

        except Exception as e:
            logger.debug("[DataCollection] after_agent error: %s", e)

        return state

    async def aafter_agent(self, state: dict, runtime: Runtime | None = None) -> dict:
        return self.after_agent(state, runtime)
