"""env_bootstrap 扩展入口点 — 遵循 deerflow_extensions 标准模式。

install_env_bootstrap() 由 boot.py 的 _boot_one() 调用，
_installed 全局守卫确保多次调用 boot_all_extensions() 安全。
"""

import logging

logger = logging.getLogger(__name__)
_installed = False


def install_env_bootstrap(app=None) -> None:
    """安装 env_bootstrap 扩展，自动探测并注入环境变量。

    幂等: _installed 守卫防止重复安装。
    回滚安全: 所有异常被捕获，不阻塞 DeerFlow 启动。
    """
    global _installed
    if _installed:
        return

    try:
        from deerflow_extensions.env_bootstrap.bootstrap import bootstrap_all

        result = bootstrap_all()
        logger.info(
            "[EnvBootstrap] Installed: DEER_FLOW_PROJECT_ROOT=%s ADS_MCP_CONFIG_PATH=%s",
            result.get("DEER_FLOW_PROJECT_ROOT"),
            result.get("ADS_MCP_CONFIG_PATH"),
        )
        _installed = True
    except Exception as _e:
        logger.warning("[EnvBootstrap] install failed: %s", _e)
