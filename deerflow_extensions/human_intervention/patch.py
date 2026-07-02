"""Patch to inject HumanInterventionClarificationMiddleware into the agent chain."""

import logging
from functools import wraps

_logger = logging.getLogger("HumanIntervention.patch")


def _inject_human_intervention_middleware():
    """Replace ClarificationMiddleware instances with HumanInterventionClarificationMiddleware.

    Follows the same monkey-patching pattern as _patch_sensitive_word()
    in patch_manager.py.
    """
    # Lazy imports to respect extension loading order
    from deerflow_extensions.human_intervention.clarification_middleware_ext import (
        HumanInterventionClarificationMiddleware,
    )
    import deerflow.agents.lead_agent.agent as _agent_mw
    
    _orig = _agent_mw.build_middlewares
    
    @wraps(_orig)
    def _patched_build(config, *args, **kwargs):
        middlewares = _orig(config, *args, **kwargs)
    
        # Guard: skip if our subclass is already present (defense-in-depth)
        already_present = any(
            isinstance(m, HumanInterventionClarificationMiddleware) for m in middlewares
        )
        if already_present:
            _logger.debug(
                "[HumanIntervention] Middleware already present, skipping"
            )
            return middlewares
    
        # Find and replace any ClarificationMiddleware instances
        from deerflow.agents.middlewares.clarification_middleware import (
            ClarificationMiddleware,
        )
    
        replaced = False
        for i, mw in enumerate(middlewares):
            if isinstance(mw, ClarificationMiddleware) and not isinstance(
                mw, HumanInterventionClarificationMiddleware
            ):
                middlewares[i] = HumanInterventionClarificationMiddleware()
                _logger.info(
                    "[HumanIntervention] Replaced ClarificationMiddleware at index %d",
                    i,
                )
                replaced = True
    
        if not replaced:
            _logger.debug(
                "[HumanIntervention] No ClarificationMiddleware found to replace"
            )
    
        return middlewares
    
    _agent_mw.build_middlewares = _patched_build
    
    # Also patch deerflow.client which imports build_middlewares as a local
    # reference at module load time (line 36: from deerflow.agents.lead_agent.agent import build_middlewares).
    # Without this, client.py uses the original function even though agent.py's
    # module attribute has been patched.
    try:
        import deerflow.client as _client_mod
        _client_mod.build_middlewares = _patched_build
        _logger.debug("[HumanIntervention] Also patched deerflow.client.build_middlewares")
    except ImportError:
        _logger.debug("[HumanIntervention] deerflow.client not yet imported, skipping")
    
    _logger.info("[HumanIntervention] Patch installed")
