"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { BrandingConfig } from "./types";
import { loadBrandingConfig } from "./config";

const EMPTY_CONFIG: BrandingConfig = {};

const BrandingContext = createContext<BrandingConfig>(EMPTY_CONFIG);

export function BrandingProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [config, setConfig] = useState<BrandingConfig>(EMPTY_CONFIG);

  useEffect(() => {
    loadBrandingConfig().then(setConfig);
  }, []);

  return (
    <BrandingContext.Provider value={config}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding(): BrandingConfig {
  return useContext(BrandingContext);
}
