"use client";
import { useState } from "react";
import type { ClarificationStructured } from "../types";
import { useClarification } from "../ClarificationProvider";
import { Button } from "@/components/ui/button";
import { Loader2Icon } from "lucide-react";

interface Props {
  data: ClarificationStructured;
}

export function ConfirmWidget({ data }: Props) {
  const { isSubmitting, submitClarification, dismissClarification } =
    useClarification();

  const handleConfirm = async () => {
    if (isSubmitting) return;
    await submitClarification("confirmed");
  };

  const handleReject = async () => {
    if (isSubmitting) return;
    await submitClarification("rejected");
  };

  const options = data.options.length > 0 ? data.options : ["确认", "取消"];

  return (
    <div className="w-full rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40 p-4">
      <div className="flex items-start justify-between mb-2">
        <span className="text-sm font-semibold text-amber-700 dark:text-amber-300">
          风险确认
        </span>
      </div>
      <p className="mb-3 text-sm text-foreground">{data.question}</p>
      {data.context && (
        <p className="mb-3 text-xs text-muted-foreground bg-white/50 dark:bg-black/20 rounded p-2 whitespace-pre-wrap">
          {data.context}
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
              disabled={isSubmitting}
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
