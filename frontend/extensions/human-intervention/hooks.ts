"use client";
import { useEffect } from "react";
import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";

/**
 * Bridge between ClarificationProvider's CustomEvent and useThreadStream.sendMessage.
 *
 * Usage in any thread page:
 *   useClarificationSubmit(sendMessage, threadId, isLoading);
 *
 * When a ClarificationWidget calls submitClarification(answer):
 *   1. Provider dispatches window "clarification:submit" CustomEvent
 *   2. This hook's listener catches it
 *   3. Calls sendMessage(threadId, { text: answer, files: [] })
 */
export function useClarificationSubmit(
  sendMessage: (
    threadId: string,
    message: PromptInputMessage,
    context?: Record<string, unknown>,
  ) => Promise<unknown>,
  threadId: string | undefined,
  isLoading?: boolean,
) {
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (!detail?.answer) return;

      const { answer } = detail;
      const tid = threadId;
      if (!tid) return;

      // Defer to next microtask to let Provider's state update settle
      queueMicrotask(() => {
        sendMessage(tid, { text: answer, files: [] }).catch((err: unknown) => {
          console.error("[HumanIntervention] sendMessage failed:", err);
        });
      });
    };

    window.addEventListener("clarification:submit", handler);
    return () => window.removeEventListener("clarification:submit", handler);
  }, [sendMessage, threadId, isLoading]);
}
