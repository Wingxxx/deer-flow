"use client";
import { useState } from "react";
import type { ClarificationStructured } from "../types";
import { useClarification } from "../ClarificationProvider";
import { Button } from "@/components/ui/button";
import { Loader2Icon } from "lucide-react";

interface Props {
  data: ClarificationStructured;
}

export function ChoiceButtonsWidget({ data }: Props) {
  const isMulti = data.widget_hints?.input_type === "multi_choice";
  const [selectedValues, setSelectedValues] = useState<string[]>([]);
  const { isSubmitting, submitClarification, dismissClarification } =
    useClarification();

  const toggleOption = (option: string) => {
    if (isMulti) {
      setSelectedValues((prev) =>
        prev.includes(option)
          ? prev.filter((v) => v !== option)
          : [...prev, option],
      );
    } else {
      setSelectedValues((prev) =>
        prev.length === 1 && prev[0] === option ? [] : [option],
      );
    }
  };

  const handleSubmit = async () => {
    const answer = isMulti
      ? selectedValues.join("\n")
      : selectedValues[0];
    if (!answer || isSubmitting) return;
    await submitClarification(answer);
  };

  const hasSelection = selectedValues.length > 0;

  return (
    <div className="w-full rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/40 p-4">
      <div className="flex items-start justify-between mb-2">
        <span className="text-sm font-semibold text-blue-700 dark:text-blue-300">
          {isMulti ? "请选择（可多选）" : "请选择"}
        </span>
      </div>
      <p className="mb-3 text-sm text-foreground">{data.question}</p>
      {data.context && (
        <p className="mb-3 text-xs text-muted-foreground bg-white/50 dark:bg-black/20 rounded p-2 whitespace-pre-wrap">
          {data.context}
        </p>
      )}
      <div className="flex flex-wrap gap-2 mb-3">
        {data.options.map((option) => {
          const isSelected = selectedValues.includes(option);
          return (
            <Button
              key={option}
              variant={isSelected ? "default" : "outline"}
              size="sm"
              onClick={() => toggleOption(option)}
              disabled={isSubmitting}
              className={
                isMulti && isSelected ? "ring-2 ring-blue-400" : ""
              }
            >
              {option}
            </Button>
          );
        })}
      </div>
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
          disabled={!hasSelection || isSubmitting}
        >
          {isSubmitting && (
            <Loader2Icon className="mr-1 size-3 animate-spin" />
          )}
          {isMulti ? "确认选择" : "确认"}
        </Button>
      </div>
    </div>
  );
}
