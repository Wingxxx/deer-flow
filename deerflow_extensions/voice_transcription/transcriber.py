"""
transcriber.py — SenseVoice-Small (funasr) 模型懒加载单例 + 并发控制 + 转录调度。

AutoModel (funasr) 非线程安全，所有转录请求通过 asyncio.Lock 串行化。
模型加载防重入，支持 ModelScope 在线下载 + 离线部署 + frozen 路径探测。
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

# ── 延迟导入 funasr（ImportError 时不阻塞 Gateway 启动）───────────────
try:
    from funasr import AutoModel

    _SENSEVOICE_AVAILABLE = True
except ImportError:
    _SENSEVOICE_AVAILABLE = False

# ── 线程安全单例 ────────────────────────────────────────────────────────────

_model_lock = threading.Lock()
_model: "AutoModel | None" = None
_model_ready = threading.Event()
_model_error: str | None = None
_model_id: str = "iic/SenseVoiceSmall"

# 熔断冷却期
_cooldown_until: float = 0.0
_cooldown_lock = threading.Lock()

# 转录请求串行化
_transcribe_lock = asyncio.Lock()
_dedicated_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sensevoice-")


def _resolve_sensevoice_model_spec():
    """解析 SenseVoice 模型路径，返回 (model_dir|None, model_id, local_only)。

    优先级:
    1. SENSEVOICE_MODEL_PATH 环境变量（最高）
    2. frozen 模式：从 sys.executable 向上遍历找 config.yaml 作为哨兵
    3. 开发模式：从 __file__ 推算项目根 + models/sensevoice/
    4. ModelScope 在线下载 model='iic/SenseVoiceSmall'（兜底）
    """
    # ── 优先级 1：环境变量 ────────────────────────────────────
    model_path = os.environ.get("SENSEVOICE_MODEL_PATH")
    if model_path:
        return model_path, _model_id, True

    # ── 优先级 2：frozen 模式（sys.executable 向上遍历） ────────
    if getattr(sys, "frozen", False):
        _bin_dir = os.path.dirname(os.path.abspath(sys.executable))
        _current = _bin_dir
        for _ in range(10):  # 最多上溯 10 级
            # 直接检查 models/sensevoice/
            _candidate = os.path.join(_current, "models", "sensevoice")
            if os.path.isdir(_candidate):
                return _candidate, _model_id, True
            # 检查 config.yaml 哨兵文件确认项目根
            if os.path.isfile(os.path.join(_current, "config.yaml")):
                _root_candidate = os.path.join(_current, "models", "sensevoice")
                if os.path.isdir(_root_candidate):
                    return _root_candidate, _model_id, True
            _parent = os.path.dirname(_current)
            if _parent == _current:
                break
            _current = _parent

    # ── 优先级 3：开发模式（__file__ 上两级找项目根） ──────────
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_this_dir))  # 上两级
    _candidate = os.path.join(_project_root, "models", "sensevoice")
    if os.path.isdir(_candidate):
        return _candidate, _model_id, True

    # ── 兜底：ModelScope 在线下载 ──────────────────────────────
    return None, _model_id, False


def get_transcriber() -> "tuple[AutoModel | None, str, str]":
    """获取 AutoModel 单例。返回 (model|None, model_id, error_msg)。"""
    global _model, _model_error, _cooldown_until

    # ── 熔断检查 ──────────────────────────────────────────────
    with _cooldown_lock:
        if _cooldown_until > time.monotonic():
            remaining = int(_cooldown_until - time.monotonic())
            return None, _model_id, f"cooling down ({remaining}s remaining)"

    if _model_ready.is_set():
        return _model, _model_id, ""

    # ═══════════════════════════════════════════════════════════
    # 熔断修复：冷却期过后清除 _model_error，允许自动重试
    # 原 bug：line 128-129 在冷却期过后仍返回旧 error
    # ═══════════════════════════════════════════════════════════
    if _model_error:
        with _cooldown_lock:
            if _cooldown_until <= time.monotonic():
                _model_error = None  # 清除旧 error，允许重试
            else:
                return None, _model_id, _model_error

    # 防重入加载
    if not _model_lock.acquire(blocking=False):
        return None, _model_id, "model loading in progress"

    try:
        if _model_ready.is_set():
            return _model, _model_id, ""
        if _model_error:
            return None, _model_id, _model_error

        if not _SENSEVOICE_AVAILABLE:
            _model_error = "funasr not installed"
            return None, _model_id, _model_error

        model_dir, model_id, local_only = _resolve_sensevoice_model_spec()

        # 磁盘空间预检查（ModelScope 下载需要 ≥1GB）
        if not local_only:
            cache_dir = os.environ.get(
                "MODELSCOPE_CACHE",
                os.path.expanduser("~/.cache/modelscope"),
            )
            # 磁盘空间检查：检查父目录或实际hub目录
            _check_dir = os.path.join(cache_dir, "models") if os.path.isdir(os.path.join(cache_dir, "models")) else cache_dir
            try:
                usage = shutil.disk_usage(_check_dir)
                if usage.free < 1024 * 1024 * 1024:  # 1GB
                    _model_error = (
                        f"insufficient disk space "
                        f"({usage.free // 1024 // 1024}MB < 1GB)"
                    )
                    return None, _model_id, _model_error
            except OSError:
                pass

        logger.info(
            "[VoiceTranscription] Loading model: model_dir=%s model_id=%s local_only=%s",
            model_dir,
            model_id,
            local_only,
        )

        kwargs: dict = {
            "model": model_id,
            "device": "cpu",
            "disable_update": True,
        }
        if model_dir:
            kwargs["model_dir"] = model_dir

        _model = AutoModel(**kwargs)

        _model_ready.set()
        logger.info("[VoiceTranscription] Model loaded successfully")
        return _model, _model_id, ""

    except Exception as e:
        _model_error = str(e)
        _model = None
        _cleanup_modelscope_residue()
        # 进入冷却期 60s
        with _cooldown_lock:
            _cooldown_until = time.monotonic() + 60
        logger.error("[VoiceTranscription] Model load failed: %s (cooldown 60s)", e)
        return None, _model_id, _model_error

    finally:
        _model_lock.release()


def _cleanup_modelscope_residue():
    """清理 ModelScope 下载失败的残留文件。"""
    import glob

    cache_dir = os.environ.get(
        "MODELSCOPE_CACHE",
        os.path.expanduser("~/.cache/modelscope"),
    )
    # 兼容新旧 ModelScope 缓存路径
    patterns = [
        os.path.join(cache_dir, "models", "iic--SenseVoiceSmall", "*", "*"),
        os.path.join(cache_dir, "models", "iic--SenseVoiceSmall", "snapshots", "*", "*"),
        os.path.join(cache_dir, "hub", "iic", "SenseVoiceSmall", "*"),
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.unlink(f)
            except OSError:
                pass


def get_model_status() -> dict:
    """返回模型状态，用于 /api/voice/status 健康检查。"""
    model, model_id, error = get_transcriber()
    return {
        "ready": model is not None,
        "backend": "funasr",
        "model_id": model_id,
        "error": error if not model else None,
    }


async def transcribe(audio_bytes: bytes) -> str:
    """转录音频字节，返回文本。

    使用 asyncio.Lock 串行化所有转录请求（AutoModel 非线程安全）。
    独立 ThreadPoolExecutor 避免与系统线程池竞争。
    超时根据音频时长动态计算（SenseVoice CPU: ~17.2x 实时率，加 10s 缓冲）。
    音频时长预检查：超过 30s 直接拒绝。

    Raises:
        ValueError: 0 字节、纯静音音频、或超过 30s
        RuntimeError: 模型未就绪或超时
    """
    if len(audio_bytes) == 0:
        raise ValueError("empty audio")

    # ── 音频时长预检查（30s 上限） ────────────────────────────────
    duration_sec = _estimate_audio_duration_sec(audio_bytes)
    if duration_sec is not None and duration_sec > 30:
        raise ValueError(f"audio too long ({duration_sec:.0f}s > 30s)")

    # ── 静音预检（16-bit WAV 振幅检测） ────────────────────────────
    if _is_silent_audio(audio_bytes):
        raise ValueError("no speech detected")

    model, _, error = get_transcriber()
    if model is None:
        raise RuntimeError(f"transcription unavailable: {error}")

    # ── 动态超时：SenseVoice CPU RTF ~17.2x，公式 max(15, 0.15*d+10) ──
    if duration_sec is not None:
        transcription_timeout = max(15.0, duration_sec * 0.15 + 10.0)
    else:
        # 无法估算时长（<1s 或非 WAV 格式），使用保守默认值
        transcription_timeout = 15.0

    start_time = time.monotonic()

    try:
        async with _transcribe_lock:
            logger.info(
                "[VoiceTranscription] Transcribing %d bytes (timeout=%.0fs)...",
                len(audio_bytes),
                transcription_timeout,
            )
            text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    _dedicated_executor,
                    _do_transcribe,
                    model,
                    audio_bytes,
                ),
                timeout=transcription_timeout,
            )

            elapsed = int((time.monotonic() - start_time) * 1000)
            logger.info(
                "[VoiceTranscription] Transcription complete: %dms",
                elapsed,
            )

            # 静音检测：SenseVoice 对纯静音可能返回空字符串
            if not text or not text.strip():
                raise ValueError("no speech detected")

            return text

    except asyncio.TimeoutError:
        elapsed = int((time.monotonic() - start_time) * 1000)
        logger.warning(
            "[VoiceTranscription] Transcription timeout after %dms (zombie thread may continue)",
            elapsed,
        )
        raise RuntimeError("transcription timeout")


def _is_silent_audio(audio_bytes: bytes, threshold: int = 200) -> bool:
    """检查 16-bit WAV 音频是否为纯静音（振幅极低）。非 WAV 格式返回 False。"""
    import struct

    if len(audio_bytes) < 44 or audio_bytes[:4] != b"RIFF":
        return False
    try:
        channels = struct.unpack_from("<H", audio_bytes, 22)[0]
        bits_per_sample = struct.unpack_from("<H", audio_bytes, 34)[0]
        data_size = struct.unpack_from("<I", audio_bytes, 40)[0]
        data_start = min(44, len(audio_bytes))
        data = audio_bytes[data_start:data_start + data_size]
        if not data:
            return True
        if bits_per_sample == 16:
            import array
            samples = array.array("h")
            samples.frombytes(data[:min(len(data), 48000 * channels * 2)])
            if not samples:
                return True
            max_ampl = max(abs(s) for s in samples)
            return max_ampl < threshold
        elif bits_per_sample == 8:
            max_ampl = max(abs(s - 128) for s in data[:len(data)])
            return max_ampl < (threshold // 256)
    except (struct.error, IndexError, ZeroDivisionError, ValueError):
        pass
    return False


# ── 同步转录函数 ────────────────────────────────────────────────────────────


def _estimate_audio_duration_sec(audio_bytes: bytes) -> float | None:
    """估算音频时长（秒）。

    优先解析 WAV RIFF header 精确计算，
    否则按 128kbps 压缩音频估算（保守偏低，避免漏过超长音频）。
    返回 None 表示无法估算（音频过短）。
    """
    import struct

    # ── WAV header 解析 ──────────────────────────────────────────────
    if len(audio_bytes) >= 44 and audio_bytes[:4] == b"RIFF":
        try:
            # 字段偏移: channels=22, sample_rate=24, bits_per_sample=34, data_size=40
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

    # ── 粗略估算（压缩格式 WebM/MP3/OGG 等） ──────────────────────
    # 压缩格式保守假设 32kbps = 4KB/s（WebM Opus 典型 16-32kbps），
    # 宁可高估不要低估，确保 30s 上限不会被绕过。
    # 旧值 128kbps=16KB/s 导致 WebM 时长被低估 4-8 倍，
    # 61s WebM(32kbps=244KB) 被估为 15.6s 漏过检查。
    if len(audio_bytes) < 4000:  # <1s，太短无法估算
        return None
    return len(audio_bytes) / 4000.0


def _do_transcribe(model: "AutoModel", audio_bytes: bytes) -> str:
    """同步转录函数，在独立线程池中运行。

    使用 model.generate() + rich_transcription_postprocess 剥离富文本标签。

    Returns:
        纯文本（已剥离富文本标签），纯静音返回空字符串。

    Note:
        SenseVoice generate() 极短音频或纯静音可能返回 []，
        此时返回空字符串由上层 transcribe() 做静音检测。
    """
    import tempfile

    from funasr.utils.postprocess_utils import rich_transcription_postprocess

    # 根据 magic bytes 检测音频格式，支持 WAV 和 WebM
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
        # 空列表防御：极短音频或纯静音可能返回 []
        if not result:
            return ""
        raw_text = result[0].get("text", "") if isinstance(result[0], dict) else str(result[0])
        if not raw_text:
            return ""
        # 剥离 SenseVoice 富文本标签（如 <|startoftrans|><|zh|><|NEUTRAL|>...）
        return rich_transcription_postprocess(raw_text)
