_installed = False


def install_env_settings(app=None):
    global _installed
    if _installed:
        return

    try:
        if app is None:
            from app.gateway.app import app as _app

            app = _app

        from deerflow_extensions.env_settings.router import router

        app.include_router(router)

        # 启动时校验 providers.json 与 CONFIG_TEMPLATE 一致性
        from deerflow_extensions.env_settings.router import _validate_provider_templates

        _validate_provider_templates()

        # Register config.yaml auto-sync middleware (zero-invasion)
        from deerflow_extensions.env_settings.config_sync import ChannelConfigSyncMiddleware

        app.add_middleware(ChannelConfigSyncMiddleware)

        _installed = True
    except Exception as _e:
        import logging

        logging.getLogger(__name__).warning("[EnvSettings] install failed: %s", _e)
        raise
