"""
router.py — Voice transcription API endpoints.

POST /api/voice/transcribe  — multipart audio upload → text
GET  /api/voice/status      — model health check
"""

import logging
import os
import tempfile

from fastapi import APIRouter, HTTPException, Request, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

# 音频格式白名单
_ALLOWED_MIME_TYPES = frozenset({
    "audio/webm",
    "audio/wav",
    "audio/mpeg",
    "audio/ogg",
    "audio/mp4",
})

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.get("/status")
async def voice_status():
    """返回语音转录服务的就绪状态。需要登录（不在公开路径白名单中）。"""
    from deerflow_extensions.voice_transcription.transcriber import get_model_status

    return get_model_status()


@router.post("/transcribe")
async def voice_transcribe(request: Request, file: UploadFile):
    """接收音频文件，返回转录文本。

    安全约束：
    - MIME 类型白名单校验
    - 文件大小限制 10MB
    - Content-Length 完整性校验
    - 临时文件 try/finally 清理
    """
    from deerflow_extensions.voice_transcription.transcriber import transcribe

    # ── Content-Length 预校验 ───────────────────────────────────────────
    content_length = request.headers.get("content-length")
    expected_bytes: int | None = None
    if content_length:
        try:
            expected_bytes = int(content_length)
            if expected_bytes > _MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件过大，最大允许 {_MAX_FILE_SIZE // 1024 // 1024}MB",
                )
        except (ValueError, TypeError):
            pass

    # ── MIME 类型白名单（去掉 codecs 等参数，只比基础类型） ────────────
    base_mime = (file.content_type or "").split(";")[0].strip()
    if base_mime not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的音频格式: {file.content_type}",
        )

    # ── 读取音频数据 ─────────────────────────────────────────────────────
    # 使用 SpooledTemporaryFile 自动处理内存/磁盘切换
    audio_bytes = None
    tmp_file = None
    try:
        tmp_file = tempfile.SpooledTemporaryFile(max_size=_MAX_FILE_SIZE)
        total = 0
        while chunk := await file.read(8192):  # UPLOAD_CHUNK_SIZE
            total += len(chunk)
            if total > _MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件过大，最大允许 {_MAX_FILE_SIZE // 1024 // 1024}MB",
                )
            tmp_file.write(chunk)
        tmp_file.seek(0)
        audio_bytes = tmp_file.read()

        # Content-Length 完整性校验：防止截断音频进入推理
        # multipart/form-data 有边界开销（~200-1000 bytes），
        # 使用 16KB 容差防止误判，同时仍能捕获严重截断
        if expected_bytes is not None and abs(total - expected_bytes) > 16384:
            raise HTTPException(status_code=400, detail="请求体不完整，请重试")

    finally:
        await file.close()
        if tmp_file is not None:
            tmp_file.close()
            # 若 SpooledTemporaryFile 写入了磁盘，清理磁盘文件
            # 内存模式 tmp_file.name 为 None，跳过 unlink
            if tmp_file.name is not None:
                try:
                    os.unlink(tmp_file.name)
                except OSError:
                    pass

    # ── 边界检查 ─────────────────────────────────────────────────────────
    if not audio_bytes or len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="音频文件为空")

    # ── 转录 ────────────────────────────────────────────────────────────
    try:
        text = await transcribe(audio_bytes)
    except ValueError as e:
        msg = str(e)
        if "no speech" in msg:
            raise HTTPException(status_code=204, detail="未检测到语音内容")
        raise HTTPException(status_code=400, detail=msg)
    except RuntimeError as e:
        msg = str(e)
        if "timeout" in msg:
            raise HTTPException(status_code=504, detail="转录超时，请重试")
        if "unavailable" in msg or "not installed" in msg or "cooling" in msg:
            raise HTTPException(
                status_code=503,
                detail=f"语音转录服务暂不可用: {msg}",
            )
        raise HTTPException(status_code=500, detail=f"转录失败: {msg}")

    if not text:
        return {"text": ""}

    return {"text": text}
