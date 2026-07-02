"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import type { ClarificationStructured } from "../types";
import { useClarification } from "../ClarificationProvider";
import { Button } from "@/components/ui/button";
import { Loader2Icon } from "lucide-react";

interface Props {
  data: ClarificationStructured;
}

const LEVEL_STYLES: Record<
  string,
  { border: string; bg: string; label: string; icon: string; pulse?: boolean }
> = {
  medium: {
    border: "border-amber-200 dark:border-amber-800",
    bg: "bg-amber-50 dark:bg-amber-950/40",
    label: "text-amber-700 dark:text-amber-300",
    icon: "⚠️",
  },
  high: {
    border: "border-red-300 dark:border-red-800",
    bg: "bg-red-50 dark:bg-red-950/40",
    label: "text-red-700 dark:text-red-300",
    icon: "🚫",
  },
  critical: {
    border: "border-red-400 dark:border-red-700",
    bg: "bg-red-50 dark:bg-red-950/40",
    label: "text-red-700 dark:text-red-300",
    icon: "🔴",
    pulse: true,
  },
};

export function ConfirmWidget({ data }: Props) {
  const { isSubmitting, submitClarification, dismissClarification } =
    useClarification();

  const riskLevel = data.widget_hints?.risk_level || "medium";
  const confirmPhrase = data.widget_hints?.confirm_phrase || "DELETE";
  const style = (LEVEL_STYLES[riskLevel] || LEVEL_STYLES.medium)!;

  // High/critical: confirm phrase input
  const [phraseInput, setPhraseInput] = useState("");
  const phraseMatch = phraseInput === confirmPhrase;

  // Critical only: countdown
  const [countdown, setCountdown] = useState(5);
  const countdownActiveRef = useRef(true);
  const [countdownDone, setCountdownDone] = useState(false);

  // Visibility tracking for countdown pause/resume
  const visibleRef = useRef(true);

  useEffect(() => {
    if (riskLevel !== "critical") return;
    setCountdown(5);
    countdownActiveRef.current = true;
    setCountdownDone(false);

    const handleVisibility = () => {
      visibleRef.current = !document.hidden;
      if (document.hidden) {
        countdownActiveRef.current = false;
      } else {
        countdownActiveRef.current = true;
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    const timer = setInterval(() => {
      if (!countdownActiveRef.current) return;
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          setCountdownDone(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
      countdownActiveRef.current = false;
    };
  }, [riskLevel]);

  const canConfirm = useCallback(() => {
    if (isSubmitting) return false;
    if (riskLevel === "medium") return true;
    if (riskLevel === "high") return phraseMatch;
    if (riskLevel === "critical") return phraseMatch && countdownDone;
    return true;
  }, [riskLevel, phraseMatch, countdownDone, isSubmitting]);

  const handleConfirm = async () => {
    if (!canConfirm() || isSubmitting) return;
    await submitClarification("confirmed");
  };

  const handleReject = async () => {
    if (isSubmitting) return;
    await submitClarification("rejected");
  };

  const options = data.options.length > 0 ? data.options : ["确认", "取消"];

  // Low risk: don't render interactive widget (auto-accept)
  if (riskLevel === "low") return null;

  return (
    <div
      className={`w-full rounded-lg border p-4 ${style.bg} ${style.border} ${
        style.pulse ? "animate-pulse" : ""
      }`}
    >
      <div className="flex items-start justify-between mb-2">
        <span className={`text-sm font-semibold ${style.label}`}>
          {style.icon} 风险确认
          {riskLevel === "high" && " — 高危"}{" "}
          {riskLevel === "critical" && " — 严重"} {riskLevel === "medium" && ""}
        </span>
      </div>
      <p className="mb-3 text-sm text-foreground">{data.question}</p>
      {data.context && (
        <p className="mb-3 text-xs text-muted-foreground bg-white/50 dark:bg-black/20 rounded p-2 whitespace-pre-wrap">
          {data.context}
        </p>
      )}

      {/* High/critical: confirm phrase input */}
      {(riskLevel === "high" || riskLevel === "critical") && (
        <div className="mb-3">
          <p className="text-xs text-muted-foreground mb-1">
            请输入 <strong>{confirmPhrase}</strong> 以确认此操作：
          </p>
          <input
            type="text"
            value={phraseInput}
            onChange={(e) => setPhraseInput(e.target.value)}
            placeholder={`请输入 ${confirmPhrase}`}
            disabled={isSubmitting}
            className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-red-400"
          />
        </div>
      )}

      {/* Critical: countdown display */}
      {riskLevel === "critical" && !countdownDone && (
        <p className="text-xs text-red-600 mb-2">
          操作将在 {countdown}s 后可用
        </p>
      )}

      <div className="flex justify-end gap-2">
        {options.map((option) => {
          const isRejectAction =
            option === "取消" ||
            option.toLowerCase() === "cancel" ||
            option.toLowerCase() === "reject" ||
            option.toLowerCase() === "no";
          return (
            <Button
              key={option}
              variant={isRejectAction ? "outline" : "default"}
              size="sm"
              onClick={isRejectAction ? handleReject : handleConfirm}
              disabled={
                isRejectAction
                  ? isSubmitting
                  : !canConfirm()
              }
            >
              {isSubmitting && !isRejectAction && (
                <Loader2Icon className="mr-1 size-3 animate-spin" />
              )}
              {option}
            </Button>
          );
        })}
        <Button
          variant="ghost"
          size="sm"
          onClick={dismissClarification}
          disabled={isSubmitting}
        >
          跳过
        </Button>
      </div>
    </div>
  );
}
