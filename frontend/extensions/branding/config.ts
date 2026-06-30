import type { BrandingConfig } from "./types";

let _cached: BrandingConfig | null = null;

export async function loadBrandingConfig(): Promise<BrandingConfig> {
  if (_cached) return _cached;
  try {
    const res = await fetch("/site.config.json", { cache: "no-store" });
    if (!res.ok) return {};
    _cached = await res.json();
    return _cached!;
  } catch {
    return {};
  }
}

export function clearBrandingCache(): void {
  _cached = null;
}
