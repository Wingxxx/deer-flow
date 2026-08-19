"""Install entry point for mcp_resilience.

Same ``_installed`` guard + env toggle pattern as mcp_instructions/startup.py.
Idempotent; never raises (install failure marks _installed to avoid noise).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)
_installed = False

_ENABLED = os.getenv("MCP_RESILIENCE_ENABLED", "1") != "0"


def install_mcp_resilience():
    """Install per-server MCP isolation. Idempotent; never raises."""
    global _installed
    if _installed:
        return
    if not _ENABLED:
        logger.info("[MCPResilience] disabled by MCP_RESILIENCE_ENABLED=0")
        _installed = True
        return
    try:
        from deerflow_extensions.mcp_resilience.patch_manager import apply_all

        apply_all()
        _installed = True
    except ImportError:
        logger.warning("[MCPResilience] deerflow not found, disabled")
        _installed = True  # 失败也置位，避免多次 boot 重复尝试打噪音
    except Exception:
        logger.exception("[MCPResilience] install failed, disabled")
        _installed = True
