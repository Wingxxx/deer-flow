"""
transcriber.py — Voice transcription core (SenseVoice / faster-whisper).

模型非线程安全：所有转写经 asyncio.Lock 串行化；锁外排队超时 15s 快速失败（503）。
转写超时后 zombie 由 _current_future 追踪：后续请求检测到未完成 future 即快速 503，
zombie 完成后 _current_future.done()→True，服务自愈（pull-based，无需主动恢复）。
"""

import asyncio
import logging
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ── Backend import guards ───────────────────────────────────────────
# 注意：frozen（PyInstaller）环境下被半收集的包在 __init__ 加载时会抛
# FileNotFoundError/OSError（如 funasr 读取 version.txt 数据文件缺失），
# 并非 ImportError。守卫必须一并捕获，否则模块加载直接崩溃。
try:
    from funasr import AutoModel

    _FUNASR_AVAILABLE = True
except (ImportError, FileNotFoundError, OSError):
    _FUNASR_AVAILABLE = False

try:
    from faster_whisper import WhisperModel

    _FASTER_WHISPER_AVAILABLE = True
except (ImportError, FileNotFoundError, OSError):
    _FASTER_WHISPER_AVAILABLE = False

# ── Thread-safe singletons ──────────────────────────────────────────

_model_lock = threading.Lock()
_model: "AutoModel | WhisperModel | None" = None
_model_ready = threading.Event()
_model_error: str | None = None
_model_id: str = ""
_active_backend: str = ""

# Circuit breaker cooldown
_cooldown_until: float = 0.0
_cooldown_lock = threading.Lock()

# Transcription serialization
_transcribe_lock = asyncio.Lock()
_dedicated_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice-")

# Zombie tracking: 记录当前正在 executor 中执行的转写任务。
# 超时后 future.done() 仍为 False（zombie 还在跑），后续请求检查后快速 503。
# 线程安全：_current_future_lock 保护读写（GIL 不保证多字节码原子性）。
_current_future: "concurrent.futures.Future | None" = None
_current_future_lock = threading.Lock()

# ── Runtime-configurable parameters ─────────────────────────────────
_WHISPER_BEAM_SIZE = int(os.environ.get("WHISPER_BEAM_SIZE", "5"))
_WHISPER_CPU_THREADS = int(os.environ.get("WHISPER_CPU_THREADS", "4"))

# ── Transcription limits (seconds) ─────────────────────────────
# 30s 上限 + 2s 容差：客户端提前截断（STOP_EARLY_GRACE_SEC=1s），
# 容差吸收 MediaRecorder 容器误差/后台标签页节流/ffprobe 元数据滞后（实测录制 30.5~31.4s）
_MAX_AUDIO_DURATION_SEC = 30.0
_DURATION_TOLERANCE_SEC = 2.0
# 锁外排队上限：超过即 503 快速失败（AWS Transcribe 429 / Google STT 排队模式）
_QUEUE_WAIT_TIMEOUT_SEC = 15.0
# zombie 观测计数：锁内转写超时后线程仍可能在跑，累计用于日志观测
_zombie_transcribe_count = 0
# zombie 恢复期 Retry-After：faster-whisper 单次转写最长 ~70s（zombie 最长 30s），
# 5s 对 whisper 太短（用户需重试 6 次）；SenseVoice 15s 内基本完成。
_RECOVERING_RETRY_AFTER_SEC: float = 15.0  # 运行时按 _active_backend 动态覆盖


def _resolve_whisper_model_path():
    """Resolve faster-whisper model directory path.

    Priority:
    1. WHISPER_MODEL_PATH environment variable (highest)
    2. frozen mode: traverse up from sys.executable looking for models/whisper/small/
    3. dev mode: derive from __file__ + models/whisper/small/

    Returns:
        str path to model directory, or None if not found.
    """
    # ── Priority 1: environment variable ────────────────────
    model_path = os.environ.get("WHISPER_MODEL_PATH")
    if model_path and os.path.isdir(model_path):
        return model_path

    # ── Priority 2: frozen mode ─────────────────────────────
    if getattr(sys, "frozen", False):
        _bin_dir = os.path.dirname(os.path.abspath(sys.executable))
        _current = _bin_dir
        for _ in range(10):  # traverse up to 10 levels
            _candidate = os.path.join(_current, "models", "whisper", "small")
            if os.path.isdir(_candidate):
                return _candidate
            # config.yaml sentinel marks project root
            if os.path.isfile(os.path.join(_current, "config.yaml")):
                _root_candidate = os.path.join(_current, "models", "whisper", "small")
                if os.path.isdir(_root_candidate):
                    return _root_candidate
            _parent = os.path.dirname(_current)
            if _parent == _current:
                break
            _current = _parent

    # ── Priority 3: dev mode ────────────────────────────────
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_this_dir))  # up two levels
    _candidate = os.path.join(_project_root, "models", "whisper", "small")
    if os.path.isdir(_candidate):
        return _candidate

    return None


def _resolve_sensevoice_model_spec():
    """Resolve SenseVoice model path. Returns (model_dir|None, model_id, local_only).

    Priority:
    1. SENSEVOICE_MODEL_PATH environment variable (highest)
    2. frozen mode: traverse up from sys.executable looking for config.yaml sentinel
    3. dev mode: derive from __file__ + models/sensevoice/
    4. ModelScope online download (fallback)
    """
    _model_id_str = "iic/SenseVoiceSmall"

    # ── Priority 1: environment variable ────────────────────
    model_path = os.environ.get("SENSEVOICE_MODEL_PATH")
    if model_path:
        return model_path, _model_id_str, True

    # ── Priority 2: frozen mode ─────────────────────────────
    if getattr(sys, "frozen", False):
        _bin_dir = os.path.dirname(os.path.abspath(sys.executable))
        _current = _bin_dir
        for _ in range(10):
            _candidate = os.path.join(_current, "models", "sensevoice")
            if os.path.isdir(_candidate):
                return _candidate, _model_id_str, True
            if os.path.isfile(os.path.join(_current, "config.yaml")):
                _root_candidate = os.path.join(_current, "models", "sensevoice")
                if os.path.isdir(_root_candidate):
                    return _root_candidate, _model_id_str, True
            _parent = os.path.dirname(_current)
            if _parent == _current:
                break
            _current = _parent

    # ── Priority 3: dev mode ────────────────────────────────
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_this_dir))
    _candidate = os.path.join(_project_root, "models", "sensevoice")
    if os.path.isdir(_candidate):
        return _candidate, _model_id_str, True

    # ── Fallback: ModelScope online download ─────────────────
    return None, _model_id_str, False


def _try_load_funasr(model_dir, model_id, local_only):
    """Attempt to load funasr/SenseVoice model. Returns True on success."""
    global _model, _model_id, _active_backend, _model_error

    if not _FUNASR_AVAILABLE:
        return False

    # ── Disk space pre-check for ModelScope download ────────
    if not local_only:
        cache_dir = os.environ.get(
            "MODELSCOPE_CACHE",
            os.path.expanduser("~/.cache/modelscope"),
        )
        _check_dir = (
            os.path.join(cache_dir, "models")
            if os.path.isdir(os.path.join(cache_dir, "models"))
            else cache_dir
        )
        try:
            usage = shutil.disk_usage(_check_dir)
            if usage.free < 1024 * 1024 * 1024:  # 1GB
                logger.warning(
                    "[VoiceTranscription] Insufficient disk for ModelScope (%dMB < 1GB)",
                    usage.free // 1024 // 1024,
                )
                return False
        except OSError:
            pass

    logger.info(
        "[VoiceTranscription] Loading funasr: model_dir=%s model_id=%s local_only=%s",
        model_dir,
        model_id,
        local_only,
    )

    kwargs: dict = {"model": model_id, "device": "cpu", "disable_update": True}
    if model_dir:
        kwargs["model_dir"] = model_dir

    _model = AutoModel(**kwargs)
    _model_id = model_id
    _active_backend = "funasr"
    return True


def _try_load_faster_whisper(model_path=None):
    """Attempt to load faster-whisper model. Returns True on success."""
    global _model, _model_id, _active_backend, _model_error

    if not _FASTER_WHISPER_AVAILABLE:
        return False

    if model_path is None:
        model_path = _resolve_whisper_model_path()

    if not model_path:
        logger.warning("[VoiceTranscription] Whisper model not found at expected paths")
        return False

    logger.info(
        "[VoiceTranscription] Loading faster-whisper: path=%s compute_type=int8 beam_size=%d",
        model_path,
        _WHISPER_BEAM_SIZE,
    )

    _model = WhisperModel(
        model_path,
        device="cpu",
        compute_type="int8",
        num_workers=1,
        cpu_threads=_WHISPER_CPU_THREADS,
    )
    _model_id = "Systran/faster-whisper-small"
    _active_backend = "faster-whisper"
    return True


def get_transcriber():
    """Get the transcription model singleton. Returns (model|None, model_id, error_msg)."""
    global _model, _model_error, _cooldown_until

    # ── Circuit breaker check ────────────────────────────────
    with _cooldown_lock:
        if _cooldown_until > time.monotonic():
            remaining = int(_cooldown_until - time.monotonic())
            return None, _model_id, f"cooling down ({remaining}s remaining)"

    if _model_ready.is_set():
        return _model, _model_id, ""

    # Clear stale error after cooldown expires
    if _model_error:
        with _cooldown_lock:
            if _cooldown_until <= time.monotonic():
                _model_error = None  # clear stale error, allow retry
            else:
                return None, _model_id, _model_error

    # Prevent re-entrant loading
    if not _model_lock.acquire(blocking=False):
        return None, _model_id, "model loading in progress"

    try:
        if _model_ready.is_set():
            return _model, _model_id, ""
        if _model_error:
            return None, _model_id, _model_error

        # ═════════════════════════════════════════════════════════
        # Priority 1: funasr/SenseVoice (AVX-capable CPU)
        # ═════════════════════════════════════════════════════════
        if _FUNASR_AVAILABLE:
            model_dir, model_id, local_only = _resolve_sensevoice_model_spec()
            # Only try funasr if model exists locally or download is possible
            if model_dir or not local_only:
                if _try_load_funasr(model_dir, model_id, local_only):
                    _model_ready.set()
                    logger.info("[VoiceTranscription] Model loaded (funasr)")
                    return _model, _model_id, ""

        # ═════════════════════════════════════════════════════════
        # Priority 2: faster-whisper (SSE2-only CPU)
        # ═════════════════════════════════════════════════════════
        if _FASTER_WHISPER_AVAILABLE:
            whisper_path = _resolve_whisper_model_path()
            if whisper_path:
                if _try_load_faster_whisper(whisper_path):
                    _model_ready.set()
                    logger.info("[VoiceTranscription] Model loaded (faster-whisper)")
                    return _model, _model_id, ""

        # ═════════════════════════════════════════════════════════
        # Nothing available
        # ═════════════════════════════════════════════════════════
        _model_error = (
            "no transcription backend available "
            "(funasr not installed/found, whisper model not found at expected paths)"
        )
        return None, "", _model_error

    except Exception as e:
        _model_error = str(e)
        _model = None
        # Enter cooldown
        with _cooldown_lock:
            _cooldown_until = time.monotonic() + 60
        logger.error("[VoiceTranscription] Model load failed: %s (cooldown 60s)", e)
        return None, _model_id, _model_error

    finally:
        _model_lock.release()


def get_model_status() -> dict:
    """Return model status for /api/voice/status health check."""
    model, model_id, error = get_transcriber()
    return {
        "ready": model is not None,
        "backend": _active_backend if model else "",
        "model_id": model_id,
        "error": error if not model else None,
    }


# ── Async transcription ──────────────────────────────────────────────


async def transcribe(audio_bytes: bytes) -> str:
    """Transcribe audio bytes, returns text.

    Uses asyncio.Lock for serialization (models are non-thread-safe).
    Dedicated ThreadPoolExecutor avoids contention with system pool.
    Timeout is dynamic based on backend and audio duration.

    Raises:
        ValueError: empty audio, silent audio, or >32s (30s cap + 2s tolerance)
        RuntimeError: model not ready or timeout
    """
    global _current_future
    if len(audio_bytes) == 0:
        raise ValueError("empty audio")

    # ── Audio duration pre-check (30s cap + 2s tolerance) ─
    duration_sec = _estimate_audio_duration_sec(audio_bytes)
    if duration_sec is not None and duration_sec > _MAX_AUDIO_DURATION_SEC + _DURATION_TOLERANCE_SEC:
        raise ValueError(f"audio too long ({duration_sec:.0f}s > {_MAX_AUDIO_DURATION_SEC:.0f}s)")

    # ── Silence pre-check ────────────────────────────────────
    if _is_silent_audio(audio_bytes):
        raise ValueError("no speech detected")

    model, _, error = get_transcriber()
    if model is None:
        raise RuntimeError(f"transcription unavailable: {error}")

    # ── Dynamic timeout per backend ──────────────────────────
    if duration_sec is not None:
        if _active_backend == "faster-whisper":
            # faster-whisper small RTF ~0.93x on SSE2 CPU (int8)
            transcription_timeout = max(30.0, duration_sec * 2.0 + 10.0)
        else:
            # SenseVoice RTF ~17.2x
            transcription_timeout = max(15.0, duration_sec * 0.15 + 10.0)
    else:
        transcription_timeout = 15.0 if _active_backend != "faster-whisper" else 30.0

    start_time = time.monotonic()

    # ── 动态 zombie 恢复期 Retry-After ─────────────────────
    # SenseVoice zombie 剩余 ≤5s，faster-whisper zombie 最长 ~30s
    global _RECOVERING_RETRY_AFTER_SEC
    _RECOVERING_RETRY_AFTER_SEC = 15.0 if _active_backend == "faster-whisper" else 5.0

    # 锁外排队超时：模型非线程安全，串行化由 _transcribe_lock 保证。
    # 排队超过 _QUEUE_WAIT_TIMEOUT_SEC 快速失败（503），避免无限排队后被代理层 504。
    # acquired 标志为防御式：杜绝极端竞态下锁泄漏（超时取消不改变锁状态）。
    acquired = False
    try:
        await asyncio.wait_for(_transcribe_lock.acquire(), timeout=_QUEUE_WAIT_TIMEOUT_SEC)
        acquired = True
    except asyncio.TimeoutError:
        raise RuntimeError("transcription queue busy")

    try:
        # ── Zombie 快速失败检查 ──────────────────────────────
        # 上一请求超时后 zombie 线程仍在 executor 中运行 _do_transcribe，
        # 此时 _current_future.done() 为 False。后续请求在此快速 503，
        # 避免排队等 zombie 再超时（连锁 504）。zombie 完成后自愈。
        with _current_future_lock:
            if _current_future is not None and not _current_future.done():
                raise RuntimeError("transcription recovering")

        logger.info(
            "[VoiceTranscription] Transcribing %d bytes backend=%s (timeout=%.0fs)...",
            len(audio_bytes),
            _active_backend,
            transcription_timeout,
        )
        future = asyncio.get_event_loop().run_in_executor(
            _dedicated_executor,
            _do_transcribe,
            model,
            audio_bytes,
        )
        # 记录当前 future：供后续请求的 zombie 检查使用
        with _current_future_lock:
            _current_future = future
        text = await asyncio.wait_for(future, timeout=transcription_timeout)

        elapsed = int((time.monotonic() - start_time) * 1000)
        logger.info("[VoiceTranscription] Transcription complete: %dms", elapsed)

        # Post-transcription silence check
        if not text or not text.strip():
            raise ValueError("no speech detected")

        return text

    except asyncio.TimeoutError:
        elapsed = int((time.monotonic() - start_time) * 1000)
        global _zombie_transcribe_count
        _zombie_transcribe_count += 1
        logger.warning(
            "[VoiceTranscription] Transcription timeout after %dms "
            "(zombie thread may continue, cumulative=%d)",
            elapsed,
            _zombie_transcribe_count,
        )
        raise RuntimeError("transcription timeout")
    finally:
        if acquired:
            _transcribe_lock.release()


# ── Audio utilities (backend-agnostic) ───────────────────────────────


def _is_silent_audio(audio_bytes: bytes, threshold: int = 200) -> bool:
    """Check if 16-bit WAV audio is pure silence (very low amplitude). Non-WAV returns False."""
    import struct

    if len(audio_bytes) < 44 or audio_bytes[:4] != b"RIFF":
        return False
    try:
        channels = struct.unpack_from("<H", audio_bytes, 22)[0]
        bits_per_sample = struct.unpack_from("<H", audio_bytes, 34)[0]
        data_size = struct.unpack_from("<I", audio_bytes, 40)[0]
        data_start = min(44, len(audio_bytes))
        data = audio_bytes[data_start : data_start + data_size]
        if not data:
            return True
        if bits_per_sample == 16:
            import array

            samples = array.array("h")
            samples.frombytes(data[: min(len(data), 48000 * channels * 2)])
            if not samples:
                return True
            max_ampl = max(abs(s) for s in samples)
            return max_ampl < threshold
        elif bits_per_sample == 8:
            max_ampl = max(abs(s - 128) for s in data[: len(data)])
            return max_ampl < (threshold // 256)
    except (struct.error, IndexError, ZeroDivisionError, ValueError):
        pass
    return False


def _estimate_audio_duration_sec(audio_bytes: bytes) -> float | None:
    """Estimate audio duration in seconds.

    Prefers WAV RIFF header parsing for accuracy, otherwise uses ffprobe
    to read precise container metadata (WebM/MP3/OGG). Returns None when
    duration cannot be determined precisely (no bitrate guessing —
    deployment machine codecs/bitrates are unknown; oversized inputs are
    already capped at 10MB by the router and the transcription timeout
    guards the rest).
    """
    import struct

    # ── WAV header parsing ───────────────────────────────────
    if len(audio_bytes) >= 44 and audio_bytes[:4] == b"RIFF":
        try:
            channels = struct.unpack_from("<H", audio_bytes, 22)[0]
            sample_rate = struct.unpack_from("<I", audio_bytes, 24)[0]
            bits_per_sample = struct.unpack_from("<H", audio_bytes, 34)[0]
            data_size = struct.unpack_from("<I", audio_bytes, 40)[0]
            if sample_rate > 0 and bits_per_sample > 0 and channels > 0:
                bytes_per_sec = sample_rate * channels * (bits_per_sample // 8)
                if bytes_per_sec > 0:
                    return data_size / bytes_per_sec
        except (struct.error, IndexError, ZeroDivisionError):
            pass

    # ── Compressed format (WebM/MP3/OGG): ffprobe precise parse ──
    # MediaRecorder 实际码率（opus 128kbps+）远高于旧 32kbps 假设，按字节数
    # 估算会把短录音误判超长（11s 录音被估 88s → 400）。用 ffprobe 读容器
    # 元数据拿真实时长；无法解析时返回 None（不做码率估算），由后端转写
    # 超时与 10MB 上限兜底。
    import os
    import subprocess
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    tmp_path,
                ],
                capture_output=True,
                timeout=10,
                check=True,
            )
            duration = float(result.stdout.decode().strip())
            if duration > 0:
                return duration
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except (OSError, subprocess.SubprocessError, ValueError):
        pass

    # 无法精确解析（ffprobe 缺失/非媒体内容）→ 不做时长预检
    return None


# ── Synchronous transcription dispatch ───────────────────────────────


def _do_transcribe(model, audio_bytes: bytes) -> str:
    """Synchronous transcription, dispatched by _active_backend.

    - funasr: model.generate() + rich_transcription_postprocess
    - faster-whisper: model.transcribe() with language="zh", beam_size, VAD,
      WebM ffmpeg transcode fallback
    """
    import subprocess
    import tempfile

    if _active_backend == "faster-whisper":
        # ═══════════════════════════════════════════════════════
        # faster-whisper path
        # ═══════════════════════════════════════════════════════
        # WebM needs ffmpeg transcode (soundfile doesn't support WebM)
        if len(audio_bytes) >= 4 and audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as webm_tmp:
                webm_tmp.write(audio_bytes)
                webm_path = webm_tmp.name
            wav_path = webm_path + ".wav"
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        webm_path,
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        wav_path,
                    ],
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                segments, _info = model.transcribe(
                    wav_path,
                    language="zh",
                    beam_size=_WHISPER_BEAM_SIZE,
                    vad_filter=True,
                )
            finally:
                for p in (webm_path, wav_path):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
        else:
            suffix = ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
                segments, _info = model.transcribe(
                    tmp.name,
                    language="zh",
                    beam_size=_WHISPER_BEAM_SIZE,
                    vad_filter=True,
                )

        text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
        return text

    else:
        # ═══════════════════════════════════════════════════════
        # funasr path
        # ═══════════════════════════════════════════════════════
        from funasr.utils.postprocess_utils import rich_transcription_postprocess

        # Detect audio format by magic bytes
        if len(audio_bytes) >= 4 and audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
            suffix = ".webm"
        else:
            suffix = ".wav"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            result = model.generate(
                input=tmp.name,
                language="zh",
                use_itn=True,
                ban_emo_unk=True,
            )
            # Empty list guard: very short or silent audio may return []
            if not result:
                return ""
            raw_text = (
                result[0].get("text", "") if isinstance(result[0], dict) else str(result[0])
            )
            if not raw_text:
                return ""
            # Strip SenseVoice rich-text tags (e.g. <|startoftrans|><|zh|><|NEUTRAL|>...)
            return rich_transcription_postprocess(raw_text)
