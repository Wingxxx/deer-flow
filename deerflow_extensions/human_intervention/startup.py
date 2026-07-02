"""Entry point for the human_intervention extension."""

import logging

_logger = logging.getLogger("HumanIntervention")
_installed = False


def install_human_intervention():
    """Install the human_intervention extension. Idempotent."""
    global _installed
    if _installed:
        _logger.debug("Already installed, skipping")
        return
    from deerflow_extensions.human_intervention.patch import (
        _inject_human_intervention_middleware,
    )
    _inject_human_intervention_middleware()
    _installed = True
    _logger.info("[HumanIntervention] Extension installed")
