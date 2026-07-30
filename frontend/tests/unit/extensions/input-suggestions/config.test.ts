import { describe, test, expect, beforeEach, afterEach, rs } from "@rstest/core";

import {
  loadInputSuggestionsConfig,
  resolveIcon,
  clearInputSuggestionsCache,
  extractSuggestionGroups,
} from "../../../../extensions/input-suggestions/config";

// ─── 辅助函数 ──────────────────────────────────────────────

function mockFetchOk(data: unknown) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    ({ ok: true, json: async () => data }) as Response;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

function mockFetchNotOk(status: number) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    ({ ok: false, status, json: async () => ({}) }) as Response;
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

function mockFetchJsonError() {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    ({
      ok: true,
      json: async () => {
        throw new SyntaxError("Unexpected token");
      },
    }) as Response;
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
  return {
    id: "test-1",
    label: "Test",
    prompt: "Test [x]",
    icon: "Monitor",
    group: "main",
    ...overrides,
  };
}

const VALID_7 = [
  validSuggestion({ id: "a", label: "产品咨询", prompt: "咨询关于[问题]", icon: "Monitor", group: "main" }),
  validSuggestion({ id: "b", label: "技术支持", prompt: "排查[问题]", icon: "Bug", group: "main" }),
  validSuggestion({ id: "c", label: "关联模板", prompt: "处理[场景]", icon: "GitMerge", group: "main" }),
  validSuggestion({ id: "d", label: "运维报告", prompt: "生成[主题]报告", icon: "FileText", group: "create" }),
  validSuggestion({ id: "e", label: "配置脚本", prompt: "生成[场景]脚本", icon: "FileCode", group: "create" }),
  validSuggestion({ id: "f", label: "知识检索", prompt: "检索[主题]", icon: "Search", group: "create" }),
  validSuggestion({ id: "g", label: "数据分析", prompt: "分析[数据]", icon: "BarChart3", group: "create" }),
];

// ─── 测试套件 ──────────────────────────────────────────────

describe("loadInputSuggestionsConfig", () => {
  let restoreWarn: () => void;

  beforeEach(() => {
    clearInputSuggestionsCache();
    restoreWarn = spyWarn();
  });

  afterEach(() => {
    restoreWarn();
    clearInputSuggestionsCache();
  });

  // CT1: 正常返回 7 条
  test("CT1: should return 7 valid suggestions from JSON", async () => {
    const restore = mockFetchOk({ inputSuggestions: VALID_7 });
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toHaveLength(7);
      expect(result.configs[0]!.id).toBe("a");
      expect(result.configs[6]!.id).toBe("g");
    } finally {
      restore();
    }
  });

  // CT2: 无 inputSuggestions 字段
  test("CT2: should return [] when inputSuggestions field is missing", async () => {
    const restore = mockFetchOk({ appName: "test" });
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toEqual([])
    } finally {
      restore();
    }
  });

  // CT3: inputSuggestions 是字符串
  test("CT3: should return [] when inputSuggestions is a string", async () => {
    const restore = mockFetchOk({ inputSuggestions: "bad" });
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toEqual([])
      expect(warnCalls.length).toBeGreaterThan(0);
    } finally {
      restore();
    }
  });

  // CT4: 空数组
  test("CT4: should return [] when inputSuggestions is empty array", async () => {
    const restore = mockFetchOk({ inputSuggestions: [] });
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toEqual([])
    } finally {
      restore();
    }
  });

  // CT5: fetch 网络错误
  test("CT5: should return [] on network error", async () => {
    const restore = mockFetchError();
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toEqual([])
      expect(warnCalls.length).toBeGreaterThan(0);
    } finally {
      restore();
    }
  });

  // CT6: HTTP 404
  test("CT6: should return [] on HTTP 404", async () => {
    const restore = mockFetchNotOk(404);
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toEqual([])
      expect(warnCalls.length).toBeGreaterThan(0);
    } finally {
      restore();
    }
  });

  // CT7: JSON 语法错误
  test("CT7: should return [] on JSON parse error", async () => {
    const restore = mockFetchJsonError();
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toEqual([])
      expect(warnCalls.length).toBeGreaterThan(0);
    } finally {
      restore();
    }
  });

  // CT8: 缺少 id 字段
  test("CT8: should skip item missing id", async () => {
    const restore = mockFetchOk({
      inputSuggestions: [
        validSuggestion({ id: undefined }),
        validSuggestion({ id: "valid-2" }),
      ],
    });
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toHaveLength(1);
      expect(result.configs[0]!.id).toBe("valid-2");
      expect(warnCalls.length).toBeGreaterThan(0);
    } finally {
      restore();
    }
  });

  // CT9: group 非法值
  test("CT9: should skip item with invalid group", async () => {
    const restore = mockFetchOk({
      inputSuggestions: [
        validSuggestion({ group: "other" }),
        validSuggestion({ id: "valid-2", group: "main" }),
      ],
    });
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toHaveLength(1);
      expect(result.configs[0]!.id).toBe("valid-2");
      expect(warnCalls.length).toBeGreaterThan(0);
    } finally {
      restore();
    }
  });

  // CT10: prompt 为空字符串
  test("CT10: should skip item with empty prompt", async () => {
    const restore = mockFetchOk({
      inputSuggestions: [
        validSuggestion({ prompt: "" }),
        validSuggestion({ id: "valid-2", prompt: "real prompt" }),
      ],
    });
    try {
      const result = await loadInputSuggestionsConfig();
      expect(result.configs).toHaveLength(1);
      expect(result.configs[0]!.id).toBe("valid-2");
      expect(warnCalls.length).toBeGreaterThan(0);
    } finally {
      restore();
    }
  });

  // CT16: 缓存验证 — 第二次不发起 fetch
  test("CT16: should use cache on second call", async () => {
    let callCount = 0;
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => {
      callCount++;
      return { ok: true, json: async () => ({ inputSuggestions: [validSuggestion()] }) } as Response;
    };
    try {
      const first = await loadInputSuggestionsConfig();
      expect(first.configs).toHaveLength(1);
      expect(callCount).toBe(1);

      const second = await loadInputSuggestionsConfig();
      expect(second.configs).toHaveLength(1);
      // 第二次应使用缓存，fetch 不增加调用次数
      expect(callCount).toBe(1);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  // CT17: clearInputSuggestionsCache 后重新 fetch
  test("CT17: should re-fetch after cache clear", async () => {
    let fetchReturn = { id: "first" };
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () =>
      ({ ok: true, json: async () => ({ inputSuggestions: [validSuggestion(fetchReturn)] }) }) as Response;
    try {
      const first = await loadInputSuggestionsConfig();
      expect(first.configs).toHaveLength(1);
      expect(first.configs[0]!.id).toBe("first");

      clearInputSuggestionsCache();
      fetchReturn = { id: "second" };

      const second = await loadInputSuggestionsConfig();
      expect(second.configs).toHaveLength(1);
      expect(second.configs[0]!.id).toBe("second");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("resolveIcon", () => {
  // CT11: 已知图标
  test("CT11: should resolve Monitor icon", () => {
    const icon = resolveIcon("Monitor");
    expect(icon).toBeDefined();
    // lucide-react 图标组件可能是 ForwardRefExoticComponent (object)，而不是普通函数
    expect(typeof icon).toBe("object");
  });

  // CT12: 未知图标
  test("CT12: should return undefined for unknown icon", () => {
    expect(resolveIcon("NonExistentIcon")).toBeUndefined();
  });

  // CT13: 原型链攻击 — constructor
  test("CT13: should block constructor", () => {
    expect(resolveIcon("constructor")).toBeUndefined();
  });

  // CT14: 原型链攻击 — __proto__
  test("CT14: should block __proto__", () => {
    expect(resolveIcon("__proto__")).toBeUndefined();
  });

  // CT15: 兼容 MonitorIcon 后缀
  test("CT15: should resolve MonitorIcon (with Icon suffix)", () => {
    const icon = resolveIcon("MonitorIcon");
    expect(icon).toBeDefined();
    expect(typeof icon).toBe("object");
  });
});

describe("extractSuggestionGroups", () => {
  // GS1: 字段缺失 → 默认 { label: undefined, visible: true }
  test("GS1: returns default when key absent", () => {
    expect(extractSuggestionGroups({})).toEqual({ create: { label: undefined, visible: true } });
  });
  // GS2: null
  test("GS2: returns default when value is null", () => {
    expect(extractSuggestionGroups({ suggestionGroups: null })).toEqual({ create: { label: undefined, visible: true } });
  });
  // GS3: 字符串
  test("GS3: returns default when value is string", () => {
    expect(extractSuggestionGroups({ suggestionGroups: "bad" })).toEqual({ create: { label: undefined, visible: true } });
  });
  // GS4: 数组
  test("GS4: returns default when value is array", () => {
    expect(extractSuggestionGroups({ suggestionGroups: [{ create: {} }] })).toEqual({ create: { label: undefined, visible: true } });
  });
  // GS5: create 为空对象 → 默认
  test("GS5: returns default when create is empty object", () => {
    expect(extractSuggestionGroups({ suggestionGroups: { create: {} } })).toEqual({ create: { label: undefined, visible: true } });
  });
  // GS6: 有效 label + 有效 visible
  test("GS6: returns custom label and visible", () => {
    expect(extractSuggestionGroups({ suggestionGroups: { create: { label: "创建", visible: false } } }))
      .toEqual({ create: { label: "创建", visible: false } });
  });
  // GS7: label 为空字符串 → undefined（i18n 回退）
  test("GS7: returns undefined label when empty string", () => {
    expect(extractSuggestionGroups({ suggestionGroups: { create: { label: "" } } }))
      .toEqual({ create: { label: undefined, visible: true } });
  });
  // GS8: label 为纯空白 → undefined
  test("GS8: returns undefined label when whitespace-only", () => {
    expect(extractSuggestionGroups({ suggestionGroups: { create: { label: "   " } } }))
      .toEqual({ create: { label: undefined, visible: true } });
  });
  // GS9: label 为数字 → undefined
  test("GS9: returns undefined label when label is number", () => {
    expect(extractSuggestionGroups({ suggestionGroups: { create: { label: 123 } } }))
      .toEqual({ create: { label: undefined, visible: true } });
  });
  // GS10: label 为 boolean → undefined
  test("GS10: returns undefined label when label is boolean", () => {
    expect(extractSuggestionGroups({ suggestionGroups: { create: { label: true } } }))
      .toEqual({ create: { label: undefined, visible: true } });
  });
  // GS11: visible 为 0 → true（非 boolean）
  test("GS11: returns default visible when 0", () => {
    expect(extractSuggestionGroups({ suggestionGroups: { create: { visible: 0 } } }))
      .toEqual({ create: { label: undefined, visible: true } });
  });
  // GS12: visible 为 1 → true
  test("GS12: returns default visible when 1", () => {
    expect(extractSuggestionGroups({ suggestionGroups: { create: { visible: 1 } } }))
      .toEqual({ create: { label: undefined, visible: true } });
  });
  // GS13: visible 为 "true" → true（非 boolean）
  test("GS13: returns default visible when string 'true'", () => {
    expect(extractSuggestionGroups({ suggestionGroups: { create: { visible: "true" } } }))
      .toEqual({ create: { label: undefined, visible: true } });
  });
  // GS14: 极长 label 保留
  test("GS14: preserves extremely long label", () => {
    const long = "A".repeat(10_000);
    expect(extractSuggestionGroups({ suggestionGroups: { create: { label: long } } }))
      .toEqual({ create: { label: long, visible: true } });
  });
});

