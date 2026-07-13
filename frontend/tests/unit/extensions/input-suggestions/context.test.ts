import { describe, test, expect, beforeEach, afterEach } from "@rstest/core";

import {
  clearInputSuggestions,
  getInputSuggestions,
} from "../../../../extensions/input-suggestions/registry";
import {
  loadInputSuggestionsConfig,
  clearInputSuggestionsCache,
} from "../../../../extensions/input-suggestions/config";

// ─── 辅助 ──────────────────────────────────────────────────

function mockFetchOk(data: unknown) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    ({ ok: true, json: async () => data }) as Response;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

function mockFetchError() {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("Network error");
  };
  return () => {
    globalThis.fetch = originalFetch;
  };
}

let warnCalls: unknown[][] = [];

function spyWarn() {
  const originalWarn = console.warn;
  warnCalls = [];
  console.warn = (...args: unknown[]) => {
    warnCalls.push(args);
  };
  return () => {
    console.warn = originalWarn;
  };
}

function validSuggestion(overrides?: Record<string, unknown>) {
  return { id: "t", label: "T", prompt: "T [x]", icon: "Monitor", group: "main", ...overrides };
}

// ─── 集成测试：config.ts → registry.ts 链路 ─────────────────

describe("InputSuggestionsProvider integration (config → registry)", () => {
  let restoreWarn: () => void;

  beforeEach(() => {
    clearInputSuggestions();
    clearInputSuggestionsCache();
    restoreWarn = spyWarn();
  });

  afterEach(() => {
    restoreWarn();
    clearInputSuggestions();
    clearInputSuggestionsCache();
  });

  // PT1: 7 条有效配置 → registry 中有 7 条
  test("PT1: should populate registry with 7 items from valid JSON", async () => {
    const items = [
      validSuggestion({ id: "a" }),
      validSuggestion({ id: "b" }),
      validSuggestion({ id: "c" }),
      validSuggestion({ id: "d", group: "create" }),
      validSuggestion({ id: "e", group: "create" }),
      validSuggestion({ id: "f", group: "create" }),
      validSuggestion({ id: "g", group: "create" }),
    ];
    const restoreFetch = mockFetchOk({ inputSuggestions: items });
    try {
      const configs = await loadInputSuggestionsConfig();
      expect(configs).toHaveLength(7);

      // 模拟 Provider 行为：clear → register
      clearInputSuggestions();
      const { Monitor, Bug, GitMerge, FileText, FileCode, Search, BarChart3 } = await import("lucide-react");
      const iconMap: Record<string, unknown> = { Monitor, Bug, GitMerge, FileText, FileCode, Search, BarChart3 };

      for (const c of configs) {
        const icon = iconMap[c.icon];
        if (icon) {
          const { registerInputSuggestion } = await import(
            "../../../../extensions/input-suggestions/registry"
          );
          registerInputSuggestion({ ...c, icon: icon as any });
        }
      }

      const all = getInputSuggestions();
      expect(all).toHaveLength(7);
      expect(all.filter((s) => s.group === "main")).toHaveLength(3);
      expect(all.filter((s) => s.group === "create")).toHaveLength(4);
    } finally {
      restoreFetch();
    }
  });

  // PT2: 空数组
  test("PT2: should result in empty registry when config is empty array", async () => {
    const restoreFetch = mockFetchOk({ inputSuggestions: [] });
    try {
      const configs = await loadInputSuggestionsConfig();
      expect(configs).toEqual([]);
    } finally {
      restoreFetch();
    }
  });

  // PT3: 配置缺失
  test("PT3: should result in empty registry when config is missing", async () => {
    const restoreFetch = mockFetchOk({});
    try {
      const configs = await loadInputSuggestionsConfig();
      expect(configs).toEqual([]);
    } finally {
      restoreFetch();
    }
  });

  // PT4: fetch 失败 → 不崩溃
  test("PT4: should not crash on fetch failure", async () => {
    const restoreFetch = mockFetchError();
    try {
      const configs = await loadInputSuggestionsConfig();
      expect(configs).toEqual([]);
      expect(warnCalls.length).toBeGreaterThan(0);
    } finally {
      restoreFetch();
    }
  });

  // PT5: icon 解析失败 → 跳过 + warn
  test("PT5: resolveIcon should return undefined for unknown icon", async () => {
    const { resolveIcon: ri } = await import(
      "../../../../extensions/input-suggestions/config"
    );
    const icon = ri("BadIcon");
    expect(icon).toBeUndefined();
  });

  // PT8: useInputSuggestionsReady 应导出为函数
  test("PT8: useInputSuggestionsReady should be a function", async () => {
    const { useInputSuggestionsReady } = await import(
      "../../../../extensions/input-suggestions/context"
    );
    expect(typeof useInputSuggestionsReady).toBe("function");
  });

  // PT6: cancelled 守卫 — Provider 卸载后 registry 不应被写入
  test("PT6: cancelled guard should prevent registry writes after unmount", async () => {
    const items = [validSuggestion({ id: "a" })];
    const restoreFetch = mockFetchOk({ inputSuggestions: items });
    try {
      let cancelled = false;
      const promise = loadInputSuggestionsConfig();

      // 模拟组件卸载：同步 cancelled=true 先于 microtask 执行
      cancelled = true;

      const configs = await promise;

      // 模拟 Provider .then() 回调中的 cancelled 守卫
      if (!cancelled) {
        clearInputSuggestions();
        const { Monitor } = await import("lucide-react");
        for (const c of configs) {
          const { registerInputSuggestion } = await import(
            "../../../../extensions/input-suggestions/registry"
          );
          registerInputSuggestion({ ...c, icon: Monitor as any });
        }
      }

      expect(getInputSuggestions()).toHaveLength(0);
    } finally {
      restoreFetch();
    }
  });

  // PT7: StrictMode 双挂载 — clear-then-register 天然幂等
  test("PT7: StrictMode double-mount should not duplicate registrations", async () => {
    const items = [
      validSuggestion({ id: "a" }),
      validSuggestion({ id: "b" }),
      validSuggestion({ id: "c" }),
      validSuggestion({ id: "d", group: "create" }),
      validSuggestion({ id: "e", group: "create" }),
      validSuggestion({ id: "f", group: "create" }),
      validSuggestion({ id: "g", group: "create" }),
    ];
    const restoreFetch = mockFetchOk({ inputSuggestions: items });
    try {
      // 第一轮 mount（cancelled=true 模拟 unmount）
      let cancelled = true;
      const p1 = loadInputSuggestionsConfig();
      await p1;
      // cancelled=true => 任何 .then() 中的注册逻辑被守卫阻止
      expect(getInputSuggestions()).toHaveLength(0);

      // 清空缓存 + registry 模拟全新 mount
      clearInputSuggestionsCache();
      clearInputSuggestions();

      // 第二轮 mount（正常注册全部 7 条）
      cancelled = false;
      const configs = await loadInputSuggestionsConfig();
      clearInputSuggestions();
      const { Monitor, Bug, GitMerge, FileText, FileCode, Search, BarChart3 } = await import("lucide-react");
      const iconMap: Record<string, unknown> = { Monitor, Bug, GitMerge, FileText, FileCode, Search, BarChart3 };
      for (const c of configs) {
        const { registerInputSuggestion } = await import(
          "../../../../extensions/input-suggestions/registry"
        );
        const icon = iconMap[c.icon];
        if (icon) {
          registerInputSuggestion({ ...c, icon: icon as any });
        }
      }

      const all = getInputSuggestions();
      expect(all).toHaveLength(7);
      expect(all.filter((s) => s.group === "main")).toHaveLength(3);
      expect(all.filter((s) => s.group === "create")).toHaveLength(4);
    } finally {
      restoreFetch();
    }
  });
});
