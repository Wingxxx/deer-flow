import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_installed = False


def _ensure_package_path() -> None:
    """Ensure deerflow_extensions is importable by adding its parent to sys.path."""
    pkg_path = Path(__file__).resolve().parent.parent  # deerflow_extensions/
    pkg_str = str(pkg_path)
    if pkg_str not in sys.path:
        sys.path.insert(0, pkg_str)


def install_data_collection(config_path: str | None = None) -> None:
    global _installed
    if _installed:
        logger.warning("Data collection already installed, skipping")
        return

    _ensure_package_path()

    try:
        import deerflow.agents.lead_agent.agent as agent_module
        import deerflow.client as client_module
        from deerflow_extensions.data_collection.middleware import DataCollectionMiddleware

        original_build = agent_module._build_middlewares

        def patched_build_middlewares(*args: Any, **kwargs: Any) -> list:
            middlewares = original_build(*args, **kwargs)
            if config_path:
                from deerflow_extensions.data_collection.config import load_config
                cfg = load_config(config_path)
                if not cfg.get("enabled", True):
                    return middlewares
            middlewares.append(DataCollectionMiddleware())
            return middlewares

        agent_module._build_middlewares = patched_build_middlewares
        client_module._build_middlewares = patched_build_middlewares
        _installed = True
        logger.info("[DataCollection] System installed via monkey-patch (agent + client)")

    except ImportError:
        logger.warning(
            "[DataCollection] Failed to import deerflow module. "
            "Data collection is disabled."
        )
    except Exception:
        logger.warning(
            "[DataCollection] Failed to install. "
            "Data collection is disabled. DeerFlow continues normally."
        )
