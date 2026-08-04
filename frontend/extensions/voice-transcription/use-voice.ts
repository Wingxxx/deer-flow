/**
 * use-voice.ts — Voice recognition hook with SpeechRecognition → MediaRecorder
 * fallback chain.
 *
 * State machine:
 *   IDLE → LISTENING (SpeechRecognition)
 *   IDLE → RECORDING (MediaRecorder)
 *   LISTENING → IDLE (stop / auto-end / error)
 *   RECORDING → TRANSCRIBING (stop → POST backend)
 *   RECORDING → IDLE (cancel)
 *   TRANSCRIBING → IDLE (result / timeout / abort)
 *   ANY → ERROR (permission denied, no device, etc.)
 *   ERROR → IDLE (retry click / auto-3s / dismiss)
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { fetch } from "../../src/core/api/fetcher";
import { getBackendBaseURL } from "../../src/core/config";

// ── Browser SpeechRecognition type declarations ────────────────────────────
// Named BrowserSpeechRecognition to avoid collision with lib.dom.d.ts.

interface BrowserSpeechRecognition extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onstart: (() => void) | null;
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
  onerror: ((event: BrowserSpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

interface BrowserSpeechRecognitionConstructor {
  new (): BrowserSpeechRecognition;
}

interface BrowserSpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface BrowserSpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

// Extend Window with vendor-prefixed constructor
interface Window {
  SpeechRecognition?: BrowserSpeechRecognitionConstructor;
  webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
}

// ── Types ──────────────────────────────────────────────────────────────────

export type VoicePhase =
  | "IDLE"
  | "LISTENING"
  | "RECORDING"
  | "TRANSCRIBING"
  | "ERROR";

export interface VoiceError {
  code:
    | "NOT_ALLOWED"
    | "NO_MICROPHONE"
    | "UNSUPPORTED_BROWSER"
    | "RECORDER_ERROR"
    | "TRANSCRIPTION_TIMEOUT"
    | "TRANSCRIPTION_FAILED";
  message: string;
  recoverable: boolean;
}

export interface UseVoiceOptions {
  lang?: string;
  maxDuration?: number;
  onTranscriptionComplete?: (text: string) => void;
  onError?: (error: VoiceError) => void;
}

export interface UseVoiceReturn {
  phase: VoicePhase;
  error: VoiceError | null;
  isSupported: boolean;
  duration: number;
  start: () => void;
  stop: () => void;
  cancel: () => void;
}

// ── Browser capability detection ──────────────────────────────────────────

function detectBrowserSupport(): {
  speechRecognition: boolean;
  mediaRecorder: boolean;
} {
  // SSR: assume supported so Turbopack includes this chunk
  if (typeof window === "undefined") {
    return { speechRecognition: true, mediaRecorder: true };
  }

  const speechRecognition =
    "SpeechRecognition" in window || "webkitSpeechRecognition" in window;

  const mediaRecorder = "MediaRecorder" in window;

  return { speechRecognition, mediaRecorder };
}

function getSpeechRecognitionClass(): BrowserSpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  // TypeScript's lib.dom.d.ts types window.SpeechRecognition differently;
  // cast through unknown to use our BrowserSpeechRecognitionConstructor.
  const w = window as unknown as Record<string, BrowserSpeechRecognitionConstructor | undefined>;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

function detectMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/wav",
  ];
  for (const mime of candidates) {
    if (MediaRecorder.isTypeSupported(mime)) {
      return mime;
    }
  }
  return "";
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useVoice(options: UseVoiceOptions = {}): UseVoiceReturn {
  const {
    lang: langProp,
    maxDuration = 30,
    onTranscriptionComplete,
    onError,
  } = options;

  // 提前硬截断宽限（秒）：比例封顶——maxDuration=30 时为 1s（录制 ~29.2s，
  // 永不触达后端 30s 上限，与后端 2s 容差双保险）；短录音场景等比缩小。
  // 倒计时显示（VoiceButton 基于 maxDuration 计算）自动满足"数到 1 时停"。
  const stopEarlyGraceSec = Math.min(1, Math.max(0.3, maxDuration * 0.1));

  const [phase, setPhase] = useState<VoicePhase>("IDLE");
  const [error, setError] = useState<VoiceError | null>(null);
  const [duration, setDuration] = useState(0);

  // Refs
  const phaseRef = useRef<VoicePhase>("IDLE");
  const errorRef = useRef<VoiceError | null>(null);
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef<number>(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cooldownRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoRecoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const onCompleteRef = useRef(onTranscriptionComplete);
  const onErrorRef = useRef(onError);

  // Keep callbacks fresh
  onCompleteRef.current = onTranscriptionComplete;
  onErrorRef.current = onError;

  // Browser support
  const supportRef = useRef(detectBrowserSupport());
  const isSupported = supportRef.current.mediaRecorder;

  // ── Error helper ──────────────────────────────────────────────────────

  const setErrorState = useCallback(
    (code: VoiceError["code"], message: string, recoverable: boolean, recoverDelayMs = 3000) => {
      // 清除上一个错误的自动恢复定时器，防止旧 timer 错误清除新 error
      if (autoRecoverTimerRef.current) {
        clearTimeout(autoRecoverTimerRef.current);
        autoRecoverTimerRef.current = null;
      }

      const err: VoiceError = { code, message, recoverable };
      setError(err);
      errorRef.current = err;
      setPhase("ERROR");
      phaseRef.current = "ERROR";
      onErrorRef.current?.(err);

      if (recoverable) {
        // Auto-recover（默认 3s；503 场景由 Retry-After 决定冷却时长）
        autoRecoverTimerRef.current = setTimeout(() => {
          autoRecoverTimerRef.current = null;
          if (errorRef.current?.code === code) {
            setError(null);
            errorRef.current = null;
            setPhase("IDLE");
            phaseRef.current = "IDLE";
          }
        }, recoverDelayMs);
      }
    },
    [],
  );

  // ── Cleanup ───────────────────────────────────────────────────────────

  const cleanup = useCallback(() => {
    // Stop recognition
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* ignore */ }
      recognitionRef.current = null;
    }

    // Stop recorder
    if (mediaRecorderRef.current?.state === "recording") {
      try { mediaRecorderRef.current.stop(); } catch { /* ignore */ }
      mediaRecorderRef.current = null;
    }

    // Stop stream tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    // Clear chunks
    chunksRef.current = [];

    // Clear timer
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }

    // Clear cooldown
    if (cooldownRef.current) {
      clearTimeout(cooldownRef.current);
      cooldownRef.current = null;
    }

    // Clear auto-recover timer（H2 修复：防止旧 timer 泄露清除新 error）
    if (autoRecoverTimerRef.current) {
      clearTimeout(autoRecoverTimerRef.current);
      autoRecoverTimerRef.current = null;
    }

    // Abort fetch
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  // ── Duration timer ────────────────────────────────────────────────────

  const startDurationTimer = useCallback(() => {
    startTimeRef.current = Date.now();
    durationTimerRef.current = setInterval(() => {
      const elapsed = (Date.now() - startTimeRef.current) / 1000;
      setDuration(elapsed);
      if (elapsed >= maxDuration - stopEarlyGraceSec) {
        stop();
      }
    }, 250);
  }, [maxDuration, stopEarlyGraceSec]);

  // ── SpeechRecognition path ────────────────────────────────────────────

  const startSpeechRecognition = useCallback(() => {
    const SRClass = getSpeechRecognitionClass();
    if (!SRClass) return false;

    try {
      const recognition = new SRClass();
      recognition.lang = langProp || navigator.language || "zh-CN";
      recognition.interimResults = true;
      recognition.continuous = false;

      recognition.onstart = () => {
        setPhase("LISTENING");
        phaseRef.current = "LISTENING";
      };

      recognition.onresult = (event: BrowserSpeechRecognitionEvent) => {
        let finalTranscript = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          if (result?.[0] && result.isFinal) {
            finalTranscript += result[0].transcript;
          }
        }
        if (finalTranscript) {
          onCompleteRef.current?.(finalTranscript.trim());
          setPhase("IDLE");
          phaseRef.current = "IDLE";
        }
      };

      recognition.onerror = (event: BrowserSpeechRecognitionErrorEvent) => {
        if (event.error === "not-allowed" || event.error === "service-not-allowed" || event.error === "aborted") {
          // Fallback to MediaRecorder (手机浏览器经常报 aborted)
          recognitionRef.current = null;
          startMediaRecorder();
        } else if (event.error === "no-speech") {
          setErrorState("RECORDER_ERROR", "未检测到语音", true);
        } else {
          setErrorState("RECORDER_ERROR", `识别错误: ${event.error}`, true);
        }
      };

      recognition.onend = () => {
        if (phaseRef.current === "LISTENING") {
          setPhase("IDLE");
          phaseRef.current = "IDLE";
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
      return true;
    } catch {
      // If start() throws (e.g., not-allowed), fallback to MediaRecorder
      startMediaRecorder();
      return true;
    }
  }, [langProp, setErrorState]);

  // ── MediaRecorder path ─────────────────────────────────────────────────

  const startMediaRecorder = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = detectMimeType();
      if (!mimeType) {
        setErrorState("UNSUPPORTED_BROWSER", "浏览器不支持录音", false);
        return;
      }

      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstart = () => {
        setPhase("RECORDING");
        phaseRef.current = "RECORDING";
        startDurationTimer();
      };

      recorder.onstop = async () => {
        // Stop duration timer
        if (durationTimerRef.current) {
          clearInterval(durationTimerRef.current);
          durationTimerRef.current = null;
        }

        // Stop stream
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;

        // Build blob
        if (chunksRef.current.length === 0) {
          setPhase("IDLE");
          phaseRef.current = "IDLE";
          return;
        }

        const blob = new Blob(chunksRef.current, { type: mimeType });
        chunksRef.current = [];

        if (blob.size === 0) {
          setPhase("IDLE");
          phaseRef.current = "IDLE";
          return;
        }

        // Send to backend
        setPhase("TRANSCRIBING");
        phaseRef.current = "TRANSCRIBING";

        const formData = new FormData();
        formData.append("file", blob, "recording.webm");
        formData.append("mime_type", mimeType);

        const controller = new AbortController();
        abortControllerRef.current = controller;

        try {
          // 转录超时判断由后端负责：后端按音频时长动态计算转写超时（最长 70s），
          // 超时返回 504，UI 提示"转录超时，请重试"。前端不依赖任何机器性能估算
          // （部署机器性能未知），仅设置 180s 网络兜底：2× 后端最长超时 + 排队余量，
          // 保证后端能在自身超时内返回的请求前端一定等得到；真正无响应的请求
          // （网络黑洞/代理挂死）3 分钟兜底中断。
          // 排队超时（15s）+ 锁内转写（最长 ~74s @32s 音频）+ ffprobe（10s）= ~99s < 180s ✓
          const timeoutId = setTimeout(() => controller.abort(), 180_000);

          const resp = await fetch(
            `${getBackendBaseURL()}/api/voice/transcribe`,
            {
              method: "POST",
              body: formData,
              signal: controller.signal,
            },
          );

          clearTimeout(timeoutId);

          if (resp.status === 204) {
            onCompleteRef.current?.("");
            setPhase("IDLE");
            phaseRef.current = "IDLE";
            return;
          }

          if (!resp.ok) {
            let detail = "转录失败";
            try {
              const body = await resp.json();
              detail = body.detail || detail;
            } catch { /* non-JSON response */ }

            let errorCode: VoiceError["code"];
            if (resp.status === 504) {
              errorCode = "TRANSCRIPTION_TIMEOUT";
            } else if (resp.status === 503) {
              errorCode = "TRANSCRIPTION_FAILED";
              // 对齐后端 Retry-After：繁忙冷却期内不自动恢复，避免用户重试再吃 503
              const retryAfter = Number(resp.headers.get("retry-after"));
              if (Number.isFinite(retryAfter) && retryAfter > 0) {
                setErrorState(errorCode, detail, true, Math.max(3000, retryAfter * 1000));
                return;
              }
            } else if (resp.status === 413) {
              errorCode = "TRANSCRIPTION_FAILED";
            } else {
              errorCode = "TRANSCRIPTION_FAILED";
            }

            setErrorState(errorCode, detail, true);
            return;
          }

          const data = await resp.json();
          const text = data.text || "";
          onCompleteRef.current?.(text);
          setPhase("IDLE");
          phaseRef.current = "IDLE";
        } catch (err: unknown) {
          if ((err as Error).name === "AbortError") {
            setErrorState("TRANSCRIPTION_TIMEOUT", "转录超时，请重试", true);
          } else {
            setErrorState("TRANSCRIPTION_FAILED", "网络错误，请重试", true);
          }
        } finally {
          abortControllerRef.current = null;
        }
      };

      recorder.onerror = () => {
        setErrorState("RECORDER_ERROR", "录音失败", true);
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
    } catch (err: unknown) {
      const domErr = err as DOMException;
      if (domErr?.name === "NotAllowedError") {
        setErrorState("NOT_ALLOWED", "麦克风权限被拒绝", false);
      } else if (domErr?.name === "NotFoundError") {
        setErrorState("NO_MICROPHONE", "未检测到麦克风设备", false);
      } else {
        setErrorState("RECORDER_ERROR", "录音启动失败", true);
      }
    }
  }, [maxDuration, setErrorState, startDurationTimer]);

  // ── Public API ─────────────────────────────────────────────────────────

  const start = useCallback(() => {
    // Debounce guard (300ms)
    if (cooldownRef.current) return;
    cooldownRef.current = setTimeout(() => {
      cooldownRef.current = null;
    }, 300);

    if (phaseRef.current === "TRANSCRIBING") return; // Ignore during transcribing

    cleanup();

    // 仅使用 MediaRecorder + 后端 SenseVoice 转录，不走浏览器 SpeechRecognition（谷歌云端）
    startMediaRecorder();
  }, [cleanup, startMediaRecorder]);

  const stop = useCallback(() => {
    if (phaseRef.current === "RECORDING" && mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    } else if (phaseRef.current === "LISTENING" && recognitionRef.current) {
      recognitionRef.current.stop();
      setPhase("IDLE");
      phaseRef.current = "IDLE";
    }
  }, []);

  const cancel = useCallback(() => {
    // Abort any ongoing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    cleanup();
    setPhase("IDLE");
    phaseRef.current = "IDLE";
    setError(null);
    errorRef.current = null;
  }, [cleanup]);

  // ── Lifecycle ─────────────────────────────────────────────────────────

  // Cleanup on unmount (SPA route change)
  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  // beforeunload cleanup (tab close)
  useEffect(() => {
    const handleBeforeUnload = () => cleanup();
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [cleanup]);

  return {
    phase,
    error,
    isSupported,
    duration,
    start,
    stop,
    cancel,
  };
}
