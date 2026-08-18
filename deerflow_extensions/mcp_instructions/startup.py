"""Monkey-patch installation for mcp_instructions.

Replaces ``get_deferred_tools_prompt_section`` in BOTH the core prompt module
(LOAD_GLOBAL path: lead + embedded client) and tool_search (subagent lazy-
import path), same Level 3 pattern as tool_output_enrichment. Core source
files are NOT modified; this extension only swaps module attributes at
runtime. Idempotent: ``_installed`` guard + per-target wrapper marker prevent
double-installation and wrapper stacking (incl. reload / import-order races).
"""

from __future__ import annotations

import functools
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)
_installed = False

# ---- 配置：env 可覆盖，缺省即启用（不触碰核心 config 体系） ----
_ENABLED = os.getenv("MCP_INSTRUCTIONS_ENABLED", "1") != "0"
_PER_SERVER_LIMIT = int(os.getenv("MCP_INSTRUCTIONS_PER_SERVER_LIMIT", "2000"))
_TOTAL_BUDGET = int(os.getenv("MCP_INSTRUCTIONS_TOTAL_BUDGET", "8000"))
_REFRESH_COOLDOWN = float(os.getenv("MCP_INSTRUCTIONS_REFRESH_COOLDOWN", "300"))

_WRAPPER_MARK = "_mcp_instructions_wrapped"

_registry: dict[str, str] = {}
_registry_mtime: float | None = None
_registry_lock = threading.Lock()
_fetch_in_progress = False
_last_attempt = 0.0


def _config_mtime() -> float | None:
    try:
        from deerflow.config.extensions_config import ExtensionsConfig

        path = ExtensionsConfig.resolve_config_path()
        return os.path.getmtime(path) if path and path.exists() else None
    except Exception:
        return None


def _maybe_spawn_refresh() -> None:
    """Non-blocking: spawn a background fetch when registry is empty or the
    config mtime changed; cooldown + in-flight flags prevent storms. The
    request path NEVER waits on IO."""
    global _fetch_in_progress, _last_attempt
    with _registry_lock:
        now = time.monotonic()
        if _fetch_in_progress or now - _last_attempt < _REFRESH_COOLDOWN:
            return
        empty = not _registry
        mtime_changed = _config_mtime() != _registry_mtime
        if not empty and not mtime_changed:
            return
        _fetch_in_progress = True
        _last_attempt = now  # 失败/超时也推进，避免每 300s 边界同步重试
    threading.Thread(target=_sync_refresh, name="mcp-instructions-refresh", daemon=True).start()


def _sync_refresh() -> None:
    """Run the fetch on this (background) thread; lock held ONLY for state
    swap, never for network IO."""
    global _fetch_in_progress
    try:
        import asyncio

        from deerflow_extensions.mcp_instructions.fetcher import fetch_all_instructions

        data = asyncio.run(fetch_all_instructions())
        with _registry_lock:
            _registry.clear()
            _registry.update(data)
            _registry_mtime = _config_mtime()
            logger.info("[MCPInstructions] fetched %d server(s)", len(data))
    except Exception as e:
        logger.warning("[MCPInstructions] refresh failed: %s", e)
    finally:
        with _registry_lock:
            _fetch_in_progress = False


def get_registry() -> dict[str, str]:
    with _registry_lock:
        return dict(_registry)


def _render_section(instructions: dict[str, str]) -> str:
    """Render per-server instructions, sorted for deterministic prompt
    content (prefix-cache friendly); per-server truncation + total budget
    (header cost included; negative budget guarded)."""
    if not instructions:
        return ""
    parts = []
    budget = _TOTAL_BUDGET
    for name in sorted(instructions):
        header = f"### MCP 服务器指令 - {name}\n"
        text = instructions[name].strip()[:_PER_SERVER_LIMIT]
        if not text:
            continue
        if budget <= 0:
            break
        cost = len(header) + len(text)
        if cost > budget:
            text = text[: max(0, budget - len(header))]
            cost = len(header) + len(text)
            if not text:
                continue
        parts.append(header + text)
        budget -= cost
    if not parts:
        return ""
    return f"<mcp-instructions>\n{chr(10).join(parts)}\n</mcp-instructions>"


def _wrap_deferred_section(original):
    """Wrap the core section builder, appending the MCP instructions block.
    Marker attribute makes install/reload idempotent against wrapper stacking."""

    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        _maybe_spawn_refresh()
        section = original(*args, **kwargs)
        block = _render_section(get_registry())
        if not block:
            return section
        return f"{section}\n\n{block}" if section else block

    setattr(wrapper, _WRAPPER_MARK, True)
    return wrapper


def install_mcp_instructions():
    """Install via module-attribute replacement (core source untouched)."""
    global _installed
    if _installed:
        return
    # 上游 ≥0.3 原生把 instructions 注入工具描述，与本扩展并存会重复
    try:
        from importlib.metadata import version as _pkg_version

        v = tuple(int(x) for x in _pkg_version("langchain-mcp-adapters").split(".")[:2])
        if v >= (0, 3):
            logger.warning(
                "[MCPInstructions] langchain-mcp-adapters>=0.3 natively injects "
                "instructions into tool schemas; extension disabled"
            )
            _installed = True
            return
    except Exception:
        pass  # 版本探测失败不阻断（已装 0.2.2）
    if not _ENABLED:
        logger.info("[MCPInstructions] disabled by MCP_INSTRUCTIONS_ENABLED=0")
        _installed = True
        return
    try:
        from deerflow.agents.lead_agent import prompt as _prompt
        from deerflow.tools.builtins import tool_search as _tool_search

        for _label, _target in (("tool_search", _tool_search), ("prompt", _prompt)):
            _current = getattr(_target, "get_deferred_tools_prompt_section", None)
            if _current is None or getattr(_current, _WRAPPER_MARK, False):
                continue  # 已 wrap（含 prompt 后 import 绑定到 tool_search wrapper 的时序）
            setattr(_target, "get_deferred_tools_prompt_section", _wrap_deferred_section(_current))
            logger.info("[MCPInstructions] patched %s.get_deferred_tools_prompt_section", _label)
        _installed = True
        _maybe_spawn_refresh()
    except ImportError:
        logger.warning("[MCPInstructions] deerflow not found, disabled")
    except Exception:
        logger.exception("[MCPInstructions] Install failed, disabled")
