"""Core training data collector for DeerFlow.

Design principles:
  - Thread-based non-blocking: all writes are buffered and flushed in background thread
  - Zero exception propagation: failures are logged and silently degraded
  - Process-level singleton: single collector instance shared across the process
"""

import json
import os
import time
import logging
import threading
from datetime import datetime, timezone
from collections import deque
from typing import Any

from deerflow_extensions.data_collection.config import load_config

logger = logging.getLogger(__name__)


class TrainingDataCollector:
    """Training data collector with async buffered writes.

    Usage:
        collector = TrainingDataCollector()
        collector.record_agent_input(session_id="...", ...)
        await collector.shutdown()
    """

    def __init__(self, config: dict | None = None):
        cfg = config if config is not None else load_config()
        self.output_dir = cfg.get("output_dir", "/data/deerflow/training_logs")
        self.buffer_size = cfg.get("buffer_size", 500)
        self.flush_interval_sec = cfg.get("flush_interval_sec", 5.0)
        self.max_file_size_mb = cfg.get("max_file_size_mb", 100)

        self.collect_flags: dict[str, bool] = {
            "agent_input": cfg.get("collect_agent_input", True),
            "model_output": cfg.get("collect_model_output", True),
            "tool_call_request": cfg.get("collect_tool_calls", True),
            "tool_call_result": cfg.get("collect_tool_calls", True),
            "agent_intermediate_state": cfg.get("collect_intermediate_state", False),
            "final_response": cfg.get("collect_final_response", True),
        }

        self._buffer: deque[dict] = deque()
        self._buffer_lock = threading.Lock()
        self._flush_thread: threading.Thread | None = None
        self._shutdown_flag = False
        self._current_daily_file: str | None = None
        self._current_daily_size: int = 0

        self._ensure_directories()
        self._start_periodic_flush()

    def _ensure_directories(self) -> None:
        """Create raw/daily/archive subdirectories under output_dir."""
        try:
            for subdir in ("raw", "daily", "archive"):
                os.makedirs(os.path.join(self.output_dir, subdir), exist_ok=True)
        except Exception as e:
            logger.warning("[DataCollection] Failed to create directories: %s", e)

    def _get_daily_file(self) -> str:
        """Get the daily JSONL file path for the current UTC date."""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_path = os.path.join(self.output_dir, "daily", f"train_data_{today}.jsonl")

        if file_path != self._current_daily_file:
            self._current_daily_file = file_path
            self._current_daily_size = 0
            if os.path.exists(file_path):
                try:
                    self._current_daily_size = os.path.getsize(file_path)
                except OSError:
                    self._current_daily_size = 0

        return file_path

    def _should_collect(self, sample_type: str) -> bool:
        """Check whether the given sample type collection is enabled."""
        return self.collect_flags.get(sample_type, True)

    def record(self, sample_type: str, data: dict) -> None:
        """General-purpose record method.

        All semantic record methods delegate to this. The record is
        timestamped, buffered, and flushed asynchronously.

        Args:
            sample_type: One of agent_input, model_output, tool_call_request,
                tool_call_result, agent_intermediate_state, final_response.
            data: The data payload to record.
        """
        if not self._should_collect(sample_type):
            return

        record = {
            "sample_type": sample_type,
            "create_time": datetime.now().astimezone().isoformat(),
            **data,
        }

        try:
            with self._buffer_lock:
                self._buffer.append(record)
                if len(self._buffer) >= self.buffer_size:
                    t = threading.Thread(target=self._flush_sync)
                    t.start()
        except Exception as e:
            logger.warning("[DataCollection] Buffer append failed: %s", e)

    # ------------------------------------------------------------------
    # Semantic collection methods
    # ------------------------------------------------------------------

    def record_agent_input(
        self,
        session_id: str,
        user_query: str,
        system_prompt: str,
        history_context: list,
        rag_context: str = "",
        agent_config: dict | None = None,
    ) -> None:
        """Collection point P1: Agent input."""
        self.record("agent_input", {
            "session_id": session_id,
            "user_query": user_query,
            "system_prompt": system_prompt,
            "history_context": history_context,
            "rag_context": rag_context,
            "agent_config": agent_config or {},
        })

    def record_model_output(
        self,
        session_id: str,
        step_number: int,
        raw_response: str,
        response_type: str,
        finish_reason: str | None,
        tool_calls: list,
        token_usage: dict | None,
        thinking_content: str | None,
        latency_ms: float,
    ) -> None:
        """Collection point P2: Model output."""
        self.record("model_output", {
            "session_id": session_id,
            "step_number": step_number,
            "raw_response": raw_response,
            "response_type": response_type,
            "finish_reason": finish_reason,
            "tool_calls": tool_calls,
            "token_usage": token_usage or {},
            "thinking_content": thinking_content or "",
            "latency_ms": round(latency_ms, 1),
        })

    def record_tool_call(
        self,
        session_id: str,
        step_number: int,
        tool_name: str,
        tool_params: dict,
        call_id: str,
        tool_result: Any = None,
        error: str | None = None,
        duration_ms: float = 0.0,
        phase: str = "request",
    ) -> None:
        """Collection points P3+P4: Tool call request and result.

        Args:
            phase: "request" for P3 (tool invocation), "result" for P4 (tool result).
        """
        sample_type = "tool_call_request" if phase == "request" else "tool_call_result"
        data: dict[str, Any] = {
            "session_id": session_id,
            "step_number": step_number,
            "tool_name": tool_name,
            "tool_params": tool_params,
            "call_id": call_id,
            "duration_ms": round(duration_ms, 1),
        }
        if phase == "result":
            data["result"] = tool_result
            data["error"] = error
        self.record(sample_type, data)

    def record_intermediate_state(
        self,
        session_id: str,
        step_number: int,
        total_steps: int,
        message_count: int,
        accumulated_tokens: dict,
        tools_called: list,
        loop_detected: bool = False,
    ) -> None:
        """Collection point P5: Agent intermediate state."""
        self.record("agent_intermediate_state", {
            "session_id": session_id,
            "step_number": step_number,
            "total_steps": total_steps,
            "message_count": message_count,
            "accumulated_tokens": accumulated_tokens,
            "tools_called": tools_called,
            "loop_detected": loop_detected,
        })

    def record_final_response(
        self,
        session_id: str,
        final_response: str,
        total_duration_ms: float,
        total_llm_calls: int,
        total_tool_calls: int,
        total_tokens: int,
        resolution_status: str,
    ) -> None:
        """Collection point P6: Final response."""
        self.record("final_response", {
            "session_id": session_id,
            "final_response": final_response,
            "total_duration_ms": round(total_duration_ms, 1),
            "total_llm_calls": total_llm_calls,
            "total_tool_calls": total_tool_calls,
            "total_tokens": total_tokens,
            "resolution_status": resolution_status,
        })

    # ------------------------------------------------------------------
    # Flush & lifecycle management
    # ------------------------------------------------------------------

    def _flush_sync(self) -> None:
        """Synchronous flush - can be called from any thread."""
        with self._buffer_lock:
            if not self._buffer:
                return

            to_write = list(self._buffer)
            self._buffer.clear()

        if not to_write:
            return

        file_path = self._get_daily_file()
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                for record in to_write:
                    line = json.dumps(record, ensure_ascii=False) + "\n"
                    f.write(line)
                    self._current_daily_size += len(line.encode("utf-8"))

            logger.debug("[DataCollection] Flushed %d records to %s", len(to_write), file_path)

            max_bytes = self.max_file_size_mb * 1024 * 1024
            if self._current_daily_size > max_bytes:
                self._rotate_daily_file(file_path)
        except Exception as e:
            logger.error("[DataCollection] Flush failed: %s", e)
            with self._buffer_lock:
                self._buffer.extendleft(reversed(to_write))

    async def _flush(self) -> None:
        """Flush buffered records to the daily JSONL file.

        On write failure, records are prepended back to the buffer head
        to prevent data loss and preserve ordering.
        """
        self._flush_sync()

    def _rotate_daily_file(self, source_path: str) -> None:
        """Rotate the daily file to archive when it exceeds max_file_size_mb."""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            dest = os.path.join(
                self.output_dir, "archive",
                f"train_data_{timestamp}.jsonl"
            )
            os.rename(source_path, dest)
            self._current_daily_file = None
            self._current_daily_size = 0
            logger.info("[DataCollection] Rotated %s -> %s", source_path, dest)
        except Exception as e:
            logger.warning("[DataCollection] Rotation failed: %s", e)

    def _start_periodic_flush(self) -> None:
        """Start the background periodic flush task using a thread."""
        def _periodic_sync() -> None:
            while not self._shutdown_flag:
                time.sleep(self.flush_interval_sec)
                self._flush_sync()

        self._flush_thread = threading.Thread(target=_periodic_sync, daemon=True)
        self._flush_thread.start()
        logger.debug("[DataCollection] Periodic flush thread started")

    async def shutdown(self) -> None:
        """Safely shut down the collector.

        Signals the periodic flush task to stop and performs a final flush.
        """
        self._shutdown_flag = True
        if hasattr(self, '_flush_thread') and self._flush_thread:
            self._flush_thread.join(timeout=5)
        self._flush_sync()
        logger.info("[DataCollection] Collector shutdown complete")


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_collector_instance: TrainingDataCollector | None = None


def get_collector() -> TrainingDataCollector:
    """Get the global collector singleton.

    Creates a new instance with default config if none exists.
    """
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = TrainingDataCollector()
    return _collector_instance


def set_collector(collector: TrainingDataCollector) -> None:
    """Set the global collector instance (for testing / mock injection).

    Args:
        collector: The collector instance to use as the global singleton.
    """
    global _collector_instance
    _collector_instance = collector
