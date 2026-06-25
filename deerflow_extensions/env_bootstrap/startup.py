"""env_bootstrap 扩展入口点 — 遵循 deerflow_extensions 标准模式。

install_env_bootstrap() 由 boot.py 的 _boot_one() 调用，
_installed 全局守卫确保多次调用 boot_all_extensions() 安全。
"""

import logging

logger = logging.getLogger(__name__)
_installed = False


def _patch_mcp_cwd() -> None:
    """Monkey-patch build_server_params to forward cwd from config.

    ``deerflow.mcp.client.build_server_params()`` only copies the declared
    Pydantic fields (command / args / env) into the connection dict but
    silently drops any ``model_extra`` keys — including ``cwd``, which is
    stored there because ``McpServerConfig`` uses ``extra="allow"``.

    This patch reads ``cwd`` from ``config.model_extra`` and adds it to the
    returned params dict so that :func:`_make_session_pool_tool` in
    ``deerflow.mcp.tools`` can honour it instead of falling back to the
    sandbox workspace directory.

    Only stdio transports are affected; HTTP/SSE servers have no local cwd.
    The patch is safe to call multiple times (idempotent via @wraps).

    Failures are silently swallowed — if the harness module is not available
    or the function signature changes, DeerFlow continues without the patch.
    """
    try:
        from functools import wraps

        from deerflow.mcp.client import build_server_params as _orig

        @wraps(_orig)
        def _patched(server_name, config):
            params = _orig(server_name, config)
            if params.get("transport") == "stdio":
                extra = getattr(config, "model_extra", None) or {}
                cwd = extra.get("cwd", "")
                if cwd and cwd.strip():
                    params["cwd"] = cwd
                    logger.debug(
                        "[EnvBootstrap] Injected cwd=%s for MCP server '%s'",
                        cwd,
                        server_name,
                    )
            return params

        import deerflow.mcp.client

        deerflow.mcp.client.build_server_params = _patched
        logger.info("[EnvBootstrap] Patched build_server_params to propagate cwd")
    except ImportError:
        logger.debug("[EnvBootstrap] deerflow.mcp.client not available, cwd patch skipped")
    except Exception as _e:
        logger.warning("[EnvBootstrap] cwd patch failed: %s", _e)


def install_env_bootstrap(app=None) -> None:
    """安装 env_bootstrap 扩展，自动探测并注入环境变量。

    幂等: _installed 守卫防止重复安装。
    回滚安全: 所有异常被捕获，不阻塞 DeerFlow 启动。
    """
    global _installed
    if _installed:
        return

    try:
        from deerflow_extensions.env_bootstrap.bootstrap import (
            bootstrap_all,
            _rewrite_extensions_config_ads_paths,
        )

        result = bootstrap_all()
        logger.info(
            "[EnvBootstrap] Installed: DEER_FLOW_PROJECT_ROOT=%s ADS_MCP_CONFIG_PATH=%s",
            result.get("DEER_FLOW_PROJECT_ROOT"),
            result.get("ADS_MCP_CONFIG_PATH"),
        )

        # ── ADS MCP 路径绝对化 ──
        # 将 extensions_config.json 中 ADS MCP 的相对路径改写为绝对路径，
        # 删除不再需要的 cwd 字段。必须在 bootstrap_all() 之后执行，
        # 确保 DEER_FLOW_PROJECT_ROOT 已解析。
        project_root = result.get("DEER_FLOW_PROJECT_ROOT")
        if project_root:
            try:
                _rewrite_extensions_config_ads_paths(project_root)
            except Exception as _e:
                logger.warning(
                    "[EnvBootstrap] Failed to rewrite extensions_config.json: %s",
                    _e,
                )

        # ── MCP cwd forwarding patch ──
        # build_server_params() in deerflow.mcp.client drops the `cwd` field
        # from McpServerConfig.model_extra, causing stdio MCP subprocesses to
        # start in the wrong directory.  Monkey-patching the function here
        # ensures cwd is forwarded before any MCP tool is loaded.
        _patch_mcp_cwd()
        _installed = True
    except Exception as _e:
        logger.warning("[EnvBootstrap] install failed: %s", _e)
