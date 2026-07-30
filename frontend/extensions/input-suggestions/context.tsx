"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  clearInputSuggestions,
  registerInputSuggestion,
} from "./registry";
import type { InputSuggestion } from "./registry";
import { loadInputSuggestionsConfig, resolveIcon, extractSuggestionGroups } from "./config";
import type { SuggestionGroupConfig } from "./config";

// ─── Context ────────────────────────────────────────────────

interface InputSuggestionsContextValue {
  suggestions: InputSuggestion[];
  groupConfig: SuggestionGroupConfig;  // 扁平化：只取 create 组
}

const InputSuggestionsContext = createContext<InputSuggestionsContextValue>({
  suggestions: [],
  groupConfig: { label: undefined, visible: true },
});

// ─── Provider ──────────────────────────────────────────────

export function InputSuggestionsProvider({ children }: { children: ReactNode }) {
  const [value, setValue] = useState<InputSuggestionsContextValue>({
    suggestions: [],
    groupConfig: { label: undefined, visible: true },
  });

  useEffect(() => {
    let cancelled = false;

    loadInputSuggestionsConfig()
      .then(({ configs, raw }) => {
        if (cancelled) return;
        clearInputSuggestions();
        for (const c of configs) {
          const icon = resolveIcon(c.icon);
          if (icon) {
            registerInputSuggestion({ ...c, icon });
          }
        }
        const groups = extractSuggestionGroups(raw);
        setValue({
          suggestions: configs.map((c) => {
            const icon = resolveIcon(c.icon);
            return { ...c, icon: icon! };  // icon 已在上面验证
          }),
          groupConfig: groups.create,
        });
      })
      .catch((err) => {
        console.warn("[input-suggestions] Failed to load config:", err);
      });

    return () => { cancelled = true; };
  }, []);

  return (
    <InputSuggestionsContext.Provider value={value}>
      {children}
    </InputSuggestionsContext.Provider>
  );
}

// ─── Hook ──────────────────────────────────────────────────

export function useInputSuggestionsReady(): InputSuggestionsContextValue {
  return useContext(InputSuggestionsContext);
}
