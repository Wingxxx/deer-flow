import {
  MonitorIcon,
  BugIcon,
  GitMergeIcon,
  FileTextIcon,
  FileCodeIcon,
  SearchIcon,
  BarChart3Icon,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { InputSuggestionConfig } from "./types";

// ─── 静态 iconMap ──────────────────────────────────────────

const iconMap: Record<string, LucideIcon> = {
  Monitor: MonitorIcon,
  Bug: BugIcon,
  GitMerge: GitMergeIcon,
  FileText: FileTextIcon,
  FileCode: FileCodeIcon,
  Search: SearchIcon,
  BarChart3: BarChart3Icon,
};

// ─── 原型链污染防护 ────────────────────────────────────────

const BLOCKED_ICON_NAMES = new Set([
  "constructor",
  "__proto__",
  "prototype",
  "toString",
  "valueOf",
  "hasOwnProperty",
  "isPrototypeOf",
  "propertyIsEnumerable",
]);

// ─── icon 解析 ──────────────────────────────────────────────

export function resolveIcon(
  iconName: string,
): LucideIcon | undefined {
  const normalized = iconName.replace(/Icon$/i, "");
  if (BLOCKED_ICON_NAMES.has(normalized)) {
    console.warn(`[input-suggestions] Blocked icon name: "${iconName}"`);
    return undefined;
  }
  return iconMap[normalized];
}

// ─── 分组配置提取 ──────────────────────────────────────────

export interface SuggestionGroupConfig {
  label?: string;    // undefined → 消费端回退 i18n
  visible: boolean;
}

export interface SuggestionGroups {
  create: SuggestionGroupConfig;
}

/**
 * 从 site.config.json 原始对象提取 suggestionGroups。
 * 缺失/类型错误 → { create: { label: undefined, visible: true } }
 */
export function extractSuggestionGroups(json: Record<string, unknown>): SuggestionGroups {
  const raw = json["suggestionGroups"];
  const defaults: SuggestionGroups = { create: { label: undefined, visible: true } };
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return defaults;
  const obj = raw as Record<string, unknown>;
  const create = obj.create;
  if (!create || typeof create !== "object" || Array.isArray(create)) return defaults;
  const c = create as Record<string, unknown>;
  return {
    create: {
      label: typeof c.label === "string" && c.label.trim() ? c.label.trim() : undefined,
      visible: typeof c.visible === "boolean" ? c.visible : true,
    },
  };
}

// ─── 运行时校验 ──────────────────────────────────────────────

const VALID_GROUPS = new Set(["main", "create"]);


function isValidConfig(item: unknown): item is InputSuggestionConfig {
  if (!item || typeof item !== "object") return false;
  const obj = item as Record<string, unknown>;
  if (!obj.id || typeof obj.id !== "string") {
    console.warn(`[input-suggestions] Skipping item: missing or invalid "id"`);
    return false;
  }
  if (!obj.label || typeof obj.label !== "string") {
    console.warn(`[input-suggestions] Skipping item "${obj.id}": missing or invalid "label"`);
    return false;
  }
  if (!obj.prompt || typeof obj.prompt !== "string" || obj.prompt.trim() === "") {
    console.warn(`[input-suggestions] Skipping item "${obj.id}": missing, invalid or empty "prompt"`);
    return false;
  }
  if (!obj.icon || typeof obj.icon !== "string") {
    console.warn(`[input-suggestions] Skipping item "${obj.id}": missing or invalid "icon"`);
    return false;
  }
  if (!obj.group || typeof obj.group !== "string" || !VALID_GROUPS.has(obj.group)) {
    console.warn(`[input-suggestions] Skipping item "${obj.id}": invalid "group" "${String(obj.group)}"`);
    return false;
  }
  return true;
}

// ─── fetch 加载 ────────────────────────────────────────────

let _cached: { configs: InputSuggestionConfig[]; raw: Record<string, unknown> } | null = null;
let _pending: Promise<{ configs: InputSuggestionConfig[]; raw: Record<string, unknown> }> | null = null;

export function clearInputSuggestionsCache(): void {
  _cached = null;
  _pending = null;
}

export async function loadInputSuggestionsConfig(): Promise<{
  configs: InputSuggestionConfig[];
  raw: Record<string, unknown>;
}> {
  if (_cached !== null) return _cached;
  if (_pending !== null) return _pending;  // StrictMode 去重

  _pending = (async () => {
    try {
      const res = await fetch("/site.config.json", { cache: "no-store" });
      if (!res.ok) {
        console.warn(`[input-suggestions] Failed to fetch config: HTTP ${res.status}`);
        return { configs: [], raw: {} };
      }
      const json: unknown = await res.json();
      if (!json || typeof json !== "object" || Array.isArray(json)) {
        console.warn(`[input-suggestions] site.config.json is not a plain object`);
        return { configs: [], raw: {} };
      }
      const raw = json as Record<string, unknown>;
      const inputArr = raw["inputSuggestions"];
      const configs: InputSuggestionConfig[] = Array.isArray(inputArr)
        ? inputArr.filter(isValidConfig)
        : [];
      if (!Array.isArray(inputArr)) {
        console.warn(`[input-suggestions] "inputSuggestions" is not an array, got: ${typeof inputArr}`);
      }
      _cached = { configs, raw };
      return _cached;
    } catch (err) {
      console.warn("[input-suggestions] Failed to load config:", err);
      return { configs: [], raw: {} };
    } finally {
      _pending = null;
    }
  })();
  return _pending;
}



