"""Monkey-patch installation for tool_output_enrichment.

Replaces ``_enrich_result`` in the core middleware module via LOAD_GLOBAL.
The module-level function reference is resolved at call time in Python, so
replacing it after import is safe.  This is the same Level 3 pattern used
by ``data_collection`` (replacing ``build_middlewares``) and
``topic_guardrail`` (replacing multiple module-level references).

Idempotent: ``_installed`` guard prevents double-installation.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
_installed = False


def install_tool_output_enrichment():
    """Install tool_output_enrichment via monkey-patch into the core middleware.

    Replaces ``deerflow.agents.middlewares.tool_output_budget_middleware._enrich_result``
    with the extension's ``enrich_result``.  The ``_installed`` guard makes
    this call idempotent so boot.py can call it safely multiple times.
    """
    global _installed
    if _installed:
        return
    try:
        from deerflow_extensions.tool_output_enrichment import enrich_result

        import deerflow.agents.middlewares.tool_output_budget_middleware as _mw

        _mw._enrich_result = enrich_result
        _installed = True
        logger.info("[ToolOutputEnrichment] Installed via function replacement")
    except ImportError:
        logger.warning("[ToolOutputEnrichment] deerflow not found, enrichment disabled")
    except Exception:
        logger.exception("[ToolOutputEnrichment] Install failed, enrichment disabled")
