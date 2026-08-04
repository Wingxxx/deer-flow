"""
startup.py — voice_transcription extension installer.

Idempotent via _installed guard.  Model loading happens lazily on first request
(via transcriber.get_transcriber()), so startup does NOT block Gateway boot.

If WHISPER_DISABLED=1 (legacy) or VOICE_DISABLED=1 is set, the extension
skips router registration entirely — endpoints return 404, not 503.
VOICE_DISABLED takes precedence over WHISPER_DISABLED.
"""

import os

_installed = False


def _trigger_preload():
    """Trigger model preloading in background. Does NOT block Gateway boot.

    If preload fails, the first API request will trigger retry (with cooldown).
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        from deerflow_extensions.voice_transcription.transcriber import get_transcriber

        logger.info("[VoiceTranscription] Preloading model in background...")
        model, model_id, error = get_transcriber()
        if model is not None:
            logger.info("[VoiceTranscription] Model preloaded: %s", model_id)
        else:
            logger.warning("[VoiceTranscription] Model preload skipped: %s", error)
    except Exception as e:
        logger.warning("[VoiceTranscription] Model preload failed: %s", e)


def install_voice_transcription(app=None):
    global _installed
    if _installed:
        return

    # VOICE_DISABLED 优先于 WHISPER_DISABLED（兼容旧配置）
    if os.environ.get("VOICE_DISABLED") or os.environ.get("WHISPER_DISABLED"):
        _installed = True  # 标记为已安装但跳过路由注册
        import logging
        logging.getLogger(__name__).info(
            "[VoiceTranscription] Disabled via %s",
            "VOICE_DISABLED" if os.environ.get("VOICE_DISABLED") else "WHISPER_DISABLED",
        )
        return

    try:
        if app is None:
            from app.gateway.app import app as _app
            app = _app

        from deerflow_extensions.voice_transcription.router import router

        app.include_router(router)
        _installed = True

        import threading

        import logging

        logger = logging.getLogger(__name__)
        logger.info("[VoiceTranscription] Router installed at /api/voice")

        # ── Preload model in background (eliminates 8.6s cold-start latency) ──
        threading.Thread(
            target=lambda: _trigger_preload(),
            name="voice-preload",
            daemon=True,
        ).start()

    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(
            "[VoiceTranscription] install failed: %s", _e
        )
