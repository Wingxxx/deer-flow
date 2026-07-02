"""Entry point for the human_intervention extension."""

import logging
import os

_logger = logging.getLogger("HumanIntervention")
_installed = False


def install_human_intervention():
    """Install the human_intervention extension. Idempotent."""
    global _installed
    if _installed:
        _logger.debug("Already installed, skipping")
        return

    # Kill switch check — reuse boot.py resolver
    try:
        from deerflow_extensions.boot import _resolve_project_root
        root = _resolve_project_root()
        if root:
            marker = os.path.join(root, ".deer-flow", "extensions", "human_intervention.disabled")
            if os.path.exists(marker):
                _logger.info("[HumanIntervention] Kill switch active, skipping install")
                return
    except Exception:
        _logger.warning("[HumanIntervention] Kill switch check failed, continuing (Fail-Open)")
    from deerflow_extensions.human_intervention.patch import (
        _inject_human_intervention_middleware,
        _inject_clarification_into_system_prompt,
        _inject_clarification_into_skills_section,
    )
    _inject_clarification_into_system_prompt()
    _inject_clarification_into_skills_section()
    _inject_human_intervention_middleware()
    _installed = True
    _logger.info("[HumanIntervention] Extension installed")
