import type { Message } from "@langchain/langgraph-sdk";
import type { ClarificationStructured } from "./types";

const SUPPORTED_VERSION = 1;

export function parseClarificationStructured(
  message: Message | undefined | null,
): ClarificationStructured | null {
  if (!message?.additional_kwargs) return null;

  const raw = message.additional_kwargs["_clarification"];
  if (!raw || typeof raw !== "object") return null;

  const data = raw as Record<string, unknown>;
  if (typeof data._schema !== "string") return null;

  const versionMatch = data._schema.match(/\/v(\d+)$/);
  if (!versionMatch?.[1]) return null;

  const version = parseInt(versionMatch[1], 10);
  if (version > SUPPORTED_VERSION) return null;

  if (typeof data.question !== "string" || !data.question.trim()) return null;

  return data as unknown as ClarificationStructured;
}
