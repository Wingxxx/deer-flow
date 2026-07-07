import "@/styles/globals.css";
import "katex/dist/katex.min.css";

import { readFileSync } from "fs";
import { join } from "path";

import type { Metadata } from "next";

import { ThemeProvider } from "@/components/theme-provider";
import { BrandingProvider } from "../../extensions/branding/context";
import { I18nProvider } from "@/core/i18n/context";
import { detectLocaleServer } from "@/core/i18n/server";

function loadSiteConfig(): { appName?: string } {
  try {
    const configPath = join(process.cwd(), "public", "site.config.json");
    const content = readFileSync(configPath, "utf-8");
    return JSON.parse(content);
  } catch {
    return {};
  }
}

export async function generateMetadata(): Promise<Metadata> {
  const config = loadSiteConfig();
  return {
    title: config.appName ?? "开天智能助手",
    description: "A LangChain-based framework for building super agents.",
  };
}

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await detectLocaleServer();
  return (
    <html lang={locale} suppressContentEditableWarning suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" enableSystem disableTransitionOnChange>
          <BrandingProvider>
            <I18nProvider initialLocale={locale}>{children}</I18nProvider>
          </BrandingProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
