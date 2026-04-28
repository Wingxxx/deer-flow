import logging
from typing import Any

logger = logging.getLogger(__name__)

_installed = False


def install_data_collection(config_path: str | None = None) -> None:
    global _installed
    if _installed:
        logger.warning("Data collection already installed, skipping")
        return

    try:
        import deerflow.agents.lead_agent.agent as agent_module
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
        _installed = True
        logger.info("[DataCollection] System installed via monkey-patch")

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
