"use client";
import { useState } from "react";
import type { ClarificationStructured } from "../types";
import { useClarification } from "../ClarificationProvider";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loader2Icon } from "lucide-react";

interface Props {
  data: ClarificationStructured;
}

export function TextInputWidget({ data }: Props) {
  const [value, setValue] = useState("");
  const { isSubmitting, submitClarification, dismissClarification } =
    useClarification();

  const handleSubmit = async () => {
    if (!value.trim() || isSubmitting) return;
    await submitClarification(value.trim());
  };

  const typeLabel =
    data.clarification_type === "missing_info"
      ? "需要补充信息"
      : data.clarification_type === "ambiguous_requirement"
        ? "需求不明确"
        : data.clarification_type === "approach_choice"
          ? "方案选择"
          : data.clarification_type === "risk_confirmation"
            ? "风险确认"
            : "建议";

  return (
    <div className="w-full rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/40 p-4">
      <div className="flex items-start justify-between mb-2">
        <span className="text-sm font-semibold text-blue-700 dark:text-blue-300">
          {typeLabel}
        </span>
      </div>
      <p className="mb-3 text-sm text-foreground">{data.question}</p>
      {data.context && (
        <p className="mb-3 text-xs text-muted-foreground bg-white/50 dark:bg-black/20 rounded p-2 whitespace-pre-wrap">
          {data.context}
        </p>
      )}
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={data.widget_hints?.required ? "请输入（必填）..." : "请输入..."}
        className="mb-2 min-h-[80px] bg-white dark:bg-black/30"
        disabled={isSubmitting}
      />
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={dismissClarification}
          disabled={isSubmitting}
        >
          跳过
        </Button>
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={!value.trim() || isSubmitting}
        >
          {isSubmitting && (
            <Loader2Icon className="mr-1 size-3 animate-spin" />
          )}
          提交
        </Button>
      </div>
    </div>
  );
}
