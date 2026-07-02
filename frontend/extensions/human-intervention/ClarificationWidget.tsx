"use client";
import { useMemo } from "react";
import type { Message } from "@langchain/langgraph-sdk";
import { parseClarificationStructured } from "./schema";
import { useClarification } from "./ClarificationProvider";
import { ChoiceButtonsWidget } from "./widgets/ChoiceButtonsWidget";
import { TextInputWidget } from "./widgets/TextInputWidget";
import { ConfirmWidget } from "./widgets/ConfirmWidget";

interface Props {
  message: Message;
  threadMessages: Message[];
  threadIsLoading: boolean;
}

/**
 * Detects the LATEST unreplied ask_clarification tool message across the
 * entire thread. If the given `message` matches, the interactive widget
 * renders; otherwise a collapsed read-only summary is shown.
 */
function findLatestUnrepliedClarification(
  threadMessages: Message[],
  messageId: string | undefined,
  threadIsLoading: boolean,
): boolean {
  if (threadIsLoading) return false;

  // Collect all ask_clarification tool messages
  const clarificationMessages = threadMessages.filter(
    (m) => m.type === "tool" && (m as Record<string, unknown>).name === "ask_clarification",
    // isClarificationToolMessage would be ideal but we keep deps minimal
  );

  if (clarificationMessages.length === 0) return false;

  const latest = clarificationMessages[clarificationMessages.length - 1];
  if (!latest?.id) return false;

  // Only the latest clarification can be active
  if (latest.id !== messageId) return false;

  // Check whether someone already replied
  const thisIndex = threadMessages.lastIndexOf(latest);
  if (thisIndex === -1) return false;
  const laterMessages = threadMessages.slice(thisIndex + 1);
  const hasHumanReply = laterMessages.some((m) => m.type === "human");

  return !hasHumanReply;
}

export function ClarificationWidget({
  message,
  threadMessages,
  threadIsLoading,
}: Props) {
  const clarificationData = useMemo(
    () => parseClarificationStructured(message),
    [message],
  );
  const { submitClarification } = useClarification();

  const isLatestUnreplied = useMemo(
    () =>
      findLatestUnrepliedClarification(
        threadMessages,
        message.id,
        threadIsLoading,
      ),
    [threadMessages, message.id, threadIsLoading],
  );

  // No structured data → let caller fall through to MarkdownContent
  if (!clarificationData) return null;

  // Not the latest unreplied → collapsed read-only summary
  if (!isLatestUnreplied) {
    const optionSummary =
      clarificationData.options.length > 0
        ? `（${clarificationData.options.length} 个选项）`
        : "";
    return (
      <div className="text-sm text-muted-foreground border-l-2 border-muted pl-3 py-1 opacity-60">
        <span className="mr-1" role="img" aria-label="clarification">
          📋
        </span>
        {clarificationData.question}
        {optionSummary}
      </div>
    );
  }

  // Render the appropriate interactive widget
  const widgetType = clarificationData.widget_hints?.input_type || "text";

  switch (widgetType) {
    case "single_choice":
    case "multi_choice":
      return <ChoiceButtonsWidget data={clarificationData} />;
    case "confirmation":
      return <ConfirmWidget data={clarificationData} />;
    case "text":
    default:
      return <TextInputWidget data={clarificationData} />;
  }
}
