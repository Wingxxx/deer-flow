"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "deerflow-pinned-threads";
const CUSTOM_EVENT = "deerflow-pinned-changed";

function readSnapshot(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((id): id is string => typeof id === "string");
  } catch {
    return [];
  }
}

function notifyPinnedChanged() {
  window.dispatchEvent(new Event(CUSTOM_EVENT));
}

export function usePinnedThreads() {
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => readSnapshot());

  // Sync from other tabs/windows via custom event
  useEffect(() => {
    const handler = () => {
      const ids = readSnapshot();
      setPinnedIds((prev) => {
        if (
          prev.length === ids.length &&
          prev.every((id, i) => id === ids[i])
        ) {
          return prev;
        }
        return ids;
      });
    };
    window.addEventListener(CUSTOM_EVENT, handler);
    return () => window.removeEventListener(CUSTOM_EVENT, handler);
  }, []);

  const isPinned = useCallback(
    (id: string) => pinnedIds.includes(id),
    [pinnedIds],
  );

  const togglePin = useCallback(
    (id: string): { success: boolean } => {
      const current = readSnapshot();
      let newIds: string[];
      if (current.includes(id)) {
        newIds = current.filter((i) => i !== id);
      } else {
        newIds = [id, ...current];
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newIds));
      // Update state synchronously so the calling component re-renders immediately
      setPinnedIds(newIds);
      // Also notify other components (workspace-header) via custom event
      notifyPinnedChanged();
      return { success: true };
    },
    [],
  );

  const pinOrder = useMemo(() => {
    const map = new Map<string, number>();
    pinnedIds.forEach((id, index) => map.set(id, index));
    return map;
  }, [pinnedIds]);

  return { pinnedIds, isPinned, togglePin, pinOrder };
}
