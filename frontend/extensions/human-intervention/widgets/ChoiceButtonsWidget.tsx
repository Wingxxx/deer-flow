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
  const allowCustom = data.widget_hints?.allow_custom === true;
  const [selectedValues, setSelectedValues] = useState<string[]>([]);
  const [showCustom, setShowCustom] = useState(false);
  const [customText, setCustomText] = useState("");
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
    if (isSubmitting) return;
    const answer = showCustom && customText.trim()
      ? customText.trim()
      : isMulti
        ? selectedValues.join("\n")
        : (selectedValues[0] ?? "");
    if (!answer) return;
    await submitClarification(answer);
  };

  const handleCustomSubmit = async () => {
    if (!customText.trim() || isSubmitting) return;
    await submitClarification(customText.trim());
  };

  const hasSelection =
    selectedValues.length > 0 || (showCustom && customText.trim().length > 0);

  const optionsToRender = allowCustom
    ? [...data.options, "其他/自定义…"]
    : data.options;

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
        {optionsToRender.map((option, index) => {
          const isCustomButton = option === "其他/自定义…";
          const isSelected = isCustomButton
            ? showCustom
            : selectedValues.includes(option);
          return (
            <Button
              key={option || `option-${index}`}
              variant={isSelected ? "default" : "outline"}
              size="sm"
              onClick={() => {
                if (isCustomButton) {
                  setShowCustom(!showCustom);
                } else {
                  toggleOption(option);
                }
              }}
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

      {/* Custom input: shown when allow_custom and "其他/自定义…" is clicked */}
      {showCustom && allowCustom && (
        <div className="mb-3">
          <textarea
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            placeholder="请输入您的自定义内容…"
            disabled={isSubmitting}
            rows={3}
            className="w-full rounded border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
            style={{ position: "sticky", bottom: 0 }}
          />
          <div className="flex justify-end mt-2">
            <Button
              size="sm"
              onClick={handleCustomSubmit}
              disabled={!customText.trim() || isSubmitting}
            >
              {isSubmitting && (
                <Loader2Icon className="mr-1 size-3 animate-spin" />
              )}
              提交自定义
            </Button>
          </div>
        </div>
      )}

      {/* Only show standard submit when NOT in custom mode, or for multi_choice */}
      {(!showCustom || isMulti) && (
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
      )}
    </div>
  );
}
