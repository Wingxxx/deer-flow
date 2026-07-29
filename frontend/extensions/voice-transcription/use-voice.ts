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
    (code: VoiceError["code"], message: string, recoverable: boolean) => {
      const err: VoiceError = { code, message, recoverable };
      setError(err);
      errorRef.current = err;
      setPhase("ERROR");
      phaseRef.current = "ERROR";
      onErrorRef.current?.(err);

      if (recoverable) {
        // Auto-recover after 3s
        setTimeout(() => {
          if (errorRef.current?.code === code) {
            setError(null);
            errorRef.current = null;
            setPhase("IDLE");
            phaseRef.current = "IDLE";
          }
        }, 3000);
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
      if (elapsed >= maxDuration) {
        stop();
      }
    }, 250);
  }, [maxDuration]);

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
          const timeoutId = setTimeout(() => controller.abort(), 12000);

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

    // 仅使用 MediaRecorder + 后端 Whisper 转录，不走浏览器 SpeechRecognition（谷歌云端）
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
