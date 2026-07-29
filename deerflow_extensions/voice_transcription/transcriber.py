"""
transcriber.py — faster-whisper 模型懒加载单例 + 并发控制 + 转录调度。

WhisperModel (CTranslate2) 非线程安全，所有转录请求通过 asyncio.Queue 串行化。
模型加载防重入，compute_type 自适应探测，支持 HF_ENDPOINT 镜像 + 离线部署。
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

# ── 延迟导入 faster-whisper（ImportError 时不阻塞 Gateway 启动）───────────────
try:
    from faster_whisper import WhisperModel  # noqa: F401

    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False

# ── 线程安全单例 ────────────────────────────────────────────────────────────

_model_lock = threading.Lock()
_model: "WhisperModel | None" = None
_model_ready = threading.Event()
_model_error: str | None = None
_model_compute_type: str = "unknown"

# 熔断冷却期
_cooldown_until: float = 0.0
_cooldown_lock = threading.Lock()

# 转录请求串行化
_transcribe_lock = asyncio.Lock()
_dedicated_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper-")


def _detect_compute_type() -> str:
    """探测 CPU 支持的最优 compute_type。降级链: int8→int8_float16→float32→auto。"""
    try:
        from ctranslate2 import get_supported_compute_types

        supported = get_supported_compute_types("cpu")
        for candidate in ("int8", "int8_float16", "float32", "auto"):
            if candidate in supported:
                logger.info(
                    "[VoiceTranscription] CPU supports compute_type=%s (all: %s)",
                    candidate,
                    supported,
                )
                return candidate
    except ImportError:
        pass
    logger.warning("[VoiceTranscription] Cannot detect compute_type, using auto")
    return "auto"


def _get_model_path_and_mode():
    """模型路径多级优先级，兼容开发 + frozen 生产模式。

    优先级:
    1. WHISPER_MODEL_PATH 环境变量（最高）
    2. 开发模式：从 __file__ 上两级到项目根 + models/whisper/tiny/
    3. 生产 frozen 模式：从 sys.executable 推算 release 根目录
    4. HuggingFace 在线下载（兜底）

    使用绝对路径解析，不依赖进程工作目录。
    frozen 模式下 __file__ 指向 _internal/ 内，上两级到 _internal/ 找不对模型，
    需改用 sys.executable 推算 release 根目录。
    """
    model_path = os.environ.get("WHISPER_MODEL_PATH")
    local_only = False

    if model_path:
        local_only = True
        return model_path, local_only

    # ── 优先级 2：开发模式（__file__ 绝对路径） ────────────────
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_this_dir))  # 上两级
    _candidates = [
        os.path.join(_project_root, "models", "whisper", "tiny"),
    ]

    # ── 优先级 3：生产 frozen 模式（sys.executable 推算） ──────
    if getattr(sys, "frozen", False):
        _bin_dir = os.path.dirname(os.path.abspath(sys.executable))
        # 尝试多级相对位置，适应不同的部署结构
        _candidates.extend([
            os.path.join(_bin_dir, "..", "..", "models", "whisper", "tiny"),  # release 根
            os.path.join(_bin_dir, "..", "models", "whisper", "tiny"),         # backend-bin 同级
            os.path.join(_bin_dir, "models", "whisper", "tiny"),               # backend-bin 内
            os.path.join(_project_root, "models", "whisper", "tiny"),          # _internal/ 内（若已--add-data打包）
        ])

    for _candidate in _candidates:
        _resolved = os.path.normpath(_candidate)
        if os.path.isdir(_resolved):
            model_path = _resolved
            local_only = True
            break

    if not model_path:
        model_path = "tiny"  # 兜底：走 HuggingFace 在线下载

    return model_path, local_only


def get_transcriber() -> "tuple[WhisperModel | None, str, str]":
    """获取 WhisperModel 单例。返回 (model|None, compute_type, error_msg)。"""
    global _model, _model_error, _model_compute_type, _cooldown_until

    # 熔断检查
    with _cooldown_lock:
        if _cooldown_until > time.monotonic():
            remaining = int(_cooldown_until - time.monotonic())
            return None, _model_compute_type, f"cooling down ({remaining}s remaining)"

    if _model_ready.is_set():
        return _model, _model_compute_type, ""

    if _model_error:
        return None, _model_compute_type, _model_error

    # 防重入加载
    if not _model_lock.acquire(blocking=False):
        return None, _model_compute_type, "model loading in progress"

    try:
        if _model_ready.is_set():
            return _model, _model_compute_type, ""
        if _model_error:
            return None, _model_compute_type, _model_error

        if not _WHISPER_AVAILABLE:
            _model_error = "faster-whisper not installed"
            return None, _model_compute_type, _model_error

        model_path, local_only = _get_model_path_and_mode()
        compute_type = _detect_compute_type()
        _model_compute_type = compute_type

        # 磁盘空间预检查（HuggingFace 下载模式）
        if not local_only:
            cache_dir = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
            try:
                usage = shutil.disk_usage(cache_dir)
                if usage.free < 200 * 1024 * 1024:  # 200MB
                    _model_error = f"insufficient disk space ({usage.free // 1024 // 1024}MB < 200MB)"
                    return None, _model_compute_type, _model_error
            except OSError:
                pass

        logger.info(
            "[VoiceTranscription] Loading model: path=%s local_only=%s compute_type=%s",
            model_path,
            local_only,
            compute_type,
        )

        _model = WhisperModel(
            model_path,
            device="cpu",
            compute_type=compute_type,
            local_files_only=local_only,
        )

        _model_ready.set()
        logger.info("[VoiceTranscription] Model loaded successfully")
        return _model, _model_compute_type, ""

    except Exception as e:
        _model_error = str(e)
        _model = None
        # 清理残留文件
        if not _get_model_path_and_mode()[1]:
            _cleanup_download_residue()
        # 进入冷却期
        with _cooldown_lock:
            _cooldown_until = time.monotonic() + 60
        logger.error("[VoiceTranscription] Model load failed: %s (cooldown 60s)", e)
        return None, _model_compute_type, _model_error

    finally:
        _model_lock.release()


def _cleanup_download_residue():
    """清理 HuggingFace 下载失败的残留文件。"""
    import glob

    cache_dir = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    pattern = os.path.join(cache_dir, "hub", "models--Systran--faster-whisper-tiny", "blobs", "*")
    for f in glob.glob(pattern):
        try:
            os.unlink(f)
        except OSError:
            pass


def get_model_status() -> dict:
    """返回模型状态，用于 /api/voice/status 健康检查。"""
    model, compute_type, error = get_transcriber()
    return {
        "ready": model is not None,
        "compute_type": compute_type,
        "error": error if not model else None,
    }


async def transcribe(audio_bytes: bytes) -> str:
    """转录音频字节，返回文本。

    使用 asyncio.Lock 串行化所有转录请求（CTranslate2 非线程安全）。
    独立 ThreadPoolExecutor 避免与系统线程池竞争。
    超时根据音频时长动态计算（tiny 模型 CPU: ~0.3-0.6x 实时率，加缓冲）。
    音频时长预检查：超过 60s 直接拒绝。

    Raises:
        ValueError: 0 字节、纯静音音频、或超过 60s
        RuntimeError: 模型未就绪或超时
    """
    if len(audio_bytes) == 0:
        raise ValueError("empty audio")

    # ── 音频时长预检查 ───────────────────────────────────────────────
    duration_sec = _estimate_audio_duration_sec(audio_bytes)
    if duration_sec is not None and duration_sec > 60:
        raise ValueError(f"audio too long ({duration_sec:.0f}s > 60s)")

    model, _, error = get_transcriber()
    if model is None:
        raise RuntimeError(f"transcription unavailable: {error}")

    # ── 动态超时：tiny 模型 CPU 推理 ~0.3-0.6x 实时率，加 20s 基础缓冲 ──
    if duration_sec is not None:
        transcription_timeout = max(30.0, duration_sec * 0.8 + 20.0)
    else:
        # 无法估算时长（<1s 或非 WAV 格式），使用保守默认值
        transcription_timeout = 30.0

    start_time = time.monotonic()

    try:
        async with _transcribe_lock:
            logger.info(
                "[VoiceTranscription] Transcribing %d bytes (timeout=%.0fs)...",
                len(audio_bytes),
                transcription_timeout,
            )
            segments, info = await asyncio.wait_for(
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
                "[VoiceTranscription] Transcription complete: %dms lang=%s",
                elapsed,
                info.language,
            )

            # 拼接所有 segment 文本
            text = " ".join(s.text.strip() for s in segments if s.text.strip())

            # 繁体→简体转换（zhconv 确保输出简体中文）
            try:
                from zhconv import convert
                text = convert(text, "zh-cn")
            except ImportError:
                pass

            if not text:
                # 纯静音检测（兼容不同 faster-whisper 版本，no_speech_prob 可能不存在）
                if getattr(info, "no_speech_prob", 0) > 0.9:
                    raise ValueError("no speech detected")
                return ""

            return text

    except asyncio.TimeoutError:
        elapsed = int((time.monotonic() - start_time) * 1000)
        logger.warning(
            "[VoiceTranscription] Transcription timeout after %dms (zombie thread may continue)",
            elapsed,
        )
        raise RuntimeError("transcription timeout")


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

    # ── 粗略估算（压缩格式） ────────────────────────────────────────
    # 保守假设 128kbps = 16KB/s，实际 WebM/Opus 通常更低
    if len(audio_bytes) < 16000:  # <1s，太短无法估算
        return None
    return len(audio_bytes) / 16000.0


def _do_transcribe(model: "WhisperModel", audio_bytes: bytes):
    """同步转录函数，在独立线程池中运行。"""
    import tempfile

    # 根据 magic bytes 检测音频格式，faster-whisper 靠文件后缀判断编解码器
    # WebM/EBML: 1A 45 DF A3,  WAV/RIFF: 52 49 46 46
    if len(audio_bytes) >= 4 and audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
        suffix = ".webm"
    else:
        suffix = ".wav"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        segments, info = model.transcribe(
            tmp.name,
            temperature=0,
            beam_size=5,
            language="zh",
            initial_prompt="以下是简体中文的转录结果：",
        )
        # 必须消费 segments 生成器——转为 list 确保在 tmp 关闭前完成
        return list(segments), info
