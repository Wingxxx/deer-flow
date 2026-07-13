"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  clearInputSuggestions,
  registerInputSuggestion,
  getInputSuggestions,
} from "./registry";
import type { InputSuggestion } from "./registry";
import { loadInputSuggestionsConfig, resolveIcon } from "./config";

// ─── Context ────────────────────────────────────────────────

const InputSuggestionsContext = createContext<InputSuggestion[]>([]);

// ─── Provider ──────────────────────────────────────────────

export function InputSuggestionsProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [suggestions, setSuggestions] = useState<InputSuggestion[]>([]);

  useEffect(() => {
    let cancelled = false;

    loadInputSuggestionsConfig()
      .then((configs) => {
        if (cancelled) return;
        clearInputSuggestions();
        for (const c of configs) {
          const icon = resolveIcon(c.icon);
          if (icon) {
            registerInputSuggestion({ ...c, icon });
          } else {
            console.warn(
              `[input-suggestions] Icon "${c.icon}" not found for suggestion "${c.id}". ` +
                `Add it to iconMap in config.ts or check the icon name.`,
            );
          }
        }
        // 触发 state 更新 → Context 消费者重渲染 → input-box.tsx 读取已填充的 registry
        setSuggestions(getInputSuggestions());
      })
      .catch((err) => {
        console.warn("[input-suggestions] Failed to load config:", err);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <InputSuggestionsContext.Provider value={suggestions}>
      {children}
    </InputSuggestionsContext.Provider>
  );
}

// ─── Hook ──────────────────────────────────────────────────

export function useInputSuggestionsReady(): InputSuggestion[] {
  return useContext(InputSuggestionsContext);
}
