"use client";

import { Mic, MicOff, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { PromptInputButton } from "../../src/components/ai-elements/prompt-input";
import { useI18n } from "../../src/core/i18n/hooks";
import { cn } from "../../src/lib/utils";

import { Tooltip } from "../../src/components/workspace/tooltip";
import {
  useVoice,
  type UseVoiceReturn,
  type VoiceError,
} from "./use-voice";

// ── Props ──────────────────────────────────────────────────────────────────

export interface VoiceButtonProps {
  disabled?: boolean;
  lang?: string;
  maxDuration?: number;
  onTranscriptionComplete?: (text: string) => void;
  onError?: (error: VoiceError) => void;
}

// ── Aria label map ─────────────────────────────────────────────────────────

const ariaLabelKeys: Record<string, string> = {
  IDLE: "voice.startRecording",
  LISTENING: "voice.stopRecording",
  RECORDING: "voice.stopRecording",
  TRANSCRIBING: "voice.transcribing",
  ERROR: "voice.retry",
};

// ── Component ──────────────────────────────────────────────────────────────

export function VoiceButton({
  disabled = false,
  lang,
  maxDuration = 30,
  onTranscriptionComplete,
  onError,
}: VoiceButtonProps) {
  const { t } = useI18n();

  // i18n fallback (voice namespace may not exist yet)
  const vt = useCallback(
    (key: string, fallback: string): string => {
      try {
        return (t as unknown as Record<string, unknown>)[key] as string || fallback;
      } catch {
        return fallback;
      }
    },
    [t],
  );

  const [toastId, setToastId] = useState<string | number | null>(null);

  const handleComplete = useCallback(
    (text: string) => {
      if (!text) {
        toast.info(vt("voice.noSpeech", "未检测到语音内容"));
        return;
      }
      onTranscriptionComplete?.(text);
    },
    [onTranscriptionComplete, vt],
  );

  const handleError = useCallback(
    (error: VoiceError) => {
      onError?.(error);

      // Dismiss previous toast
      if (toastId) toast.dismiss(toastId);

      const id = toast.error(error.message, {
        duration: error.recoverable ? 3000 : 5000,
      });
      setToastId(id);
    },
    [onError, toastId, vt],
  );

  const voice = useVoice({
    lang,
    maxDuration,
    onTranscriptionComplete: handleComplete,
    onError: handleError,
  });

  const {
    phase,
    error,
    isSupported,
    duration,
    start,
    stop,
    cancel,
  } = voice;

  // Dismiss toast on phase change
  useEffect(() => {
    if (phase !== "ERROR" && toastId) {
      toast.dismiss(toastId);
      setToastId(null);
    }
  }, [phase, toastId]);

  // ── Countdown announcement (screen reader) ─────────────────────────────

  const countdownInt = Math.ceil(maxDuration - duration);
  const announceCountdown =
    phase === "RECORDING" && (countdownInt === 10 || countdownInt === 5);

  // ── Click handler ──────────────────────────────────────────────────────

  const handleClick = useCallback(() => {
    if (disabled) return;

    switch (phase) {
      case "IDLE":
        start();
        break;
      case "LISTENING":
      case "RECORDING":
        stop();
        break;
      case "TRANSCRIBING":
        // Ignore — prevent race condition
        break;
      case "ERROR":
        // Retry
        start();
        break;
    }
  }, [disabled, phase, start, stop]);

  // ── Don't render if unsupported (SSR: render nothing but keep in bundle) ──

  if (!isSupported && typeof window === "undefined") return <template />;
  if (!isSupported) return null;

  // ── Computed values ─────────────────────────────────────────────────────

  const isActive = phase === "LISTENING" || phase === "RECORDING";
  const isTranscribing = phase === "TRANSCRIBING";
  const isError = phase === "ERROR";
  const isButtonDisabled = disabled || isTranscribing;

  const ariaLabel = error
    ? error.message
    : vt(ariaLabelKeys[phase] || "voice.startRecording", "语音输入");

  const tooltipContent = (() => {
    if (error) return error.message;
    switch (phase) {
      case "IDLE":
        return vt("voice.startRecording", "语音输入");
      case "LISTENING":
      case "RECORDING":
        return vt("voice.stopRecording", "停止录音");
      case "TRANSCRIBING":
        return vt("voice.transcribing", "转录中...");
      default:
        return vt("voice.startRecording", "语音输入");
    }
  })();

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <>
      {/* Screen reader countdown announcements */}
      {announceCountdown && (
        <div role="status" aria-live="polite" className="sr-only">
          剩余 {countdownInt} 秒
        </div>
      )}

      <Tooltip content={tooltipContent}>
        <PromptInputButton
          className={cn(
            "px-2!",
            isActive && "text-red-500 motion-safe:animate-pulse",
          )}
          onClick={handleClick}
          disabled={isButtonDisabled}
          aria-label={ariaLabel}
          aria-disabled={isTranscribing || undefined}
        >
          {isTranscribing ? (
            <Loader2 className="size-3 animate-spin" />
          ) : isActive ? (
            <MicOff className="size-3" />
          ) : (
            <Mic className="size-3" />
          )}

          {/* Recording countdown */}
          {phase === "RECORDING" && (
            <span className="ml-1 text-[10px] tabular-nums text-muted-foreground">
              {countdownInt}s
            </span>
          )}
        </PromptInputButton>
      </Tooltip>
    </>
  );
}

export { useVoice };
