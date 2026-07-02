"""In-memory clarification rate limiter.

Process-internal dict + threading.Lock implementation.
No external dependencies (Redis/DB) — state resets on process restart,
which is acceptable for clarification rate limiting.
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)


class ClarificationRateLimiter:
    """Thread-safe in-memory rate limiter for clarification requests.

    Tracks per-thread clarification count with cooldown enforcement.
    Designed for Fail-Open: any internal error returns True (allow).
    """

    def __init__(self, max_per_turn: int = 3, cooldown_seconds: float = 30.0):
        self.max_per_turn = max_per_turn
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        # thread_id -> {"count": int, "last_ts": float}
        self._state: dict[str, dict] = {}

    def allow(self, thread_id: str) -> bool:
        """Check if a new clarification is allowed for this thread.

        Returns True (allow) on any internal error (Fail-Open).
        """
        try:
            with self._lock:
                now = time.time()
                entry = self._state.get(thread_id)
                if entry is None:
                    self._state[thread_id] = {"count": 1, "last_ts": now}
                    return True
                # Cooldown check
                if now - entry["last_ts"] < self.cooldown_seconds:
                    return False
                # Max per turn check
                if entry["count"] >= self.max_per_turn:
                    # Reset if cooldown has passed by a generous margin
                    if now - entry["last_ts"] >= self.cooldown_seconds * 2:
                        entry["count"] = 1
                        entry["last_ts"] = now
                        return True
                    return False
                entry["count"] += 1
                entry["last_ts"] = now
                return True
        except Exception:
            logger.exception("[RateLimiter] allow() error, Fail-Open")
            return True

    def cleanup_thread(self, thread_id: str):
        """Remove state for a completed/archived thread. Best-effort."""
        try:
            with self._lock:
                self._state.pop(thread_id, None)
        except Exception:
            pass
