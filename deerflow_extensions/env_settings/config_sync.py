"""FastAPI/Starlette middleware that syncs channel runtime-config changes to config.yaml.

When the upstream POST/DELETE /api/channels/{provider}/runtime-config returns
2xx, this middleware writes channels.<provider>.enabled = true/false into
config.yaml so the channel auto-starts after a server restart.
"""

from __future__ import annotations

import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Matches: /api/channels/{provider}/runtime-config with optional trailing slash
_RUNTIME_CONFIG_PATH_RE = re.compile(r"^/api/channels/([^/]+)/runtime-config/?$")


class ChannelConfigSyncMiddleware(BaseHTTPMiddleware):
    """Write channels.<provider>.enabled to config.yaml on runtime-config save/delete.

    Design:
      - Only fires on 2xx POST (enable) or DELETE (disable) to the runtime-config endpoint.
      - Provider must be in _CHANNEL_META (wecom, feishu, dingtalk, wechat).
      - Failures are logged but never re-raised — the upstream response is always returned.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Gate 1: only act on successful responses
        if response.status_code < 200 or response.status_code >= 300:
            return response

        # Gate 2: only POST (save) and DELETE (clear) are relevant
        method = request.method
        if method not in ("POST", "DELETE"):
            return response

        # Gate 3: match the runtime-config URL pattern
        path = request.url.path
        m = _RUNTIME_CONFIG_PATH_RE.match(path)
        if not m:
            return response

        provider = m.group(1)

        # Gate 4: only managed channels
        try:
            from deerflow_extensions.env_settings.router import _CHANNEL_META
        except ImportError:
            logger.debug("_CHANNEL_META not importable, skipping config sync")
            return response

        if provider not in _CHANNEL_META:
            return response

        enabled = method == "POST"

        try:
            from deerflow_extensions.env_settings.router import _set_channel_enabled_in_config
            _set_channel_enabled_in_config(provider, enabled)
        except Exception:
            logger.warning(
                "ChannelConfigSync: failed to sync config.yaml for provider=%s enabled=%s",
                provider, enabled, exc_info=True,
            )

        return response
