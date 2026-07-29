"""
startup.py — voice_transcription extension installer.

Idempotent via _installed guard.  Model loading happens lazily on first request
(via transcriber.get_transcriber()), so startup does NOT block Gateway boot.

If WHISPER_DISABLED=1 is set, the extension installs the router but the model
will never be loaded — endpoints return 503 until the flag is cleared.
"""

_installed = False


def install_voice_transcription(app=None):
    global _installed
    if _installed:
        return

    try:
        if app is None:
            from app.gateway.app import app as _app
            app = _app

        from deerflow_extensions.voice_transcription.router import router

        app.include_router(router)
        _installed = True

        import logging
        logger = logging.getLogger(__name__)
        logger.info("[VoiceTranscription] Router installed at /api/voice")

    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(
            "[VoiceTranscription] install failed: %s", _e
        )
