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

let _cached: InputSuggestionConfig[] | null = null;

export function clearInputSuggestionsCache(): void {
  _cached = null;
}

export async function loadInputSuggestionsConfig(): Promise<InputSuggestionConfig[]> {
  if (_cached !== null) return _cached;

  try {
    const res = await fetch("/site.config.json", { cache: "no-store" });
    if (!res.ok) {
      console.warn(`[input-suggestions] Failed to fetch config: HTTP ${res.status}`);
      return [];
    }
    const json: unknown = await res.json();
    const raw = (json as Record<string, unknown>)?.["inputSuggestions"];
    if (!Array.isArray(raw)) {
      console.warn(`[input-suggestions] "inputSuggestions" is not an array, got: ${typeof raw}`);
      return [];
    }
    const valid: InputSuggestionConfig[] = raw.filter(isValidConfig);
    _cached = valid;
    return valid;
  } catch (err) {
    console.warn(`[input-suggestions] Failed to load config:`, err);
    return [];
  }
}


