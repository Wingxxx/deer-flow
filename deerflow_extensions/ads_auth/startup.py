_installed = False


def install_ads_auth(app=None):
    global _installed
    if _installed:
        return

    try:
        if app is None:
            from app.gateway.app import app as _app

            app = _app

        from deerflow_extensions.ads_auth.router import router as ads_router

        app.include_router(ads_router, prefix="/api/v1/auth")

        from deerflow_extensions.ads_auth.config import get_ads_default_role
        import logging as _log
        _log.getLogger(__name__).info(
            "[ADS] Installed — default_role=%s", get_ads_default_role()
        )

        _installed = True
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("[ADS] install failed: %s", _e)
