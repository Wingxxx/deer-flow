"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Loader2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { FlickeringGrid } from "@/components/ui/flickering-grid";
import { Input } from "@/components/ui/input";
import { useBranding } from "../branding/context";

function validateNext(next: string | null): string | null {
  if (!next || !next.startsWith("/")) return null;
  if (next.startsWith("//") || next.startsWith("http://") || next.startsWith("https://")) return null;
  if (next.includes(":") && !next.startsWith("/")) return null;
  return next;
}

export default function ADSLoginPage() {
  const branding = useBranding();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { theme, resolvedTheme } = useTheme();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const nextPath = validateNext(searchParams.get("next")) ?? "/workspace";

  useEffect(() => {
    // When the CSRF handler in fetcher.ts force-redirects here with
    // ?csrf_forced=1, skip the auto-redirect check entirely.  Even if
    // the backend logout's Set-Cookie doesn't survive the proxy
    // rewrite, we MUST NOT bounce the user back to workspace — the
    // whole point is to show the login form.
    if (searchParams.get("csrf_forced") === "1") {
      setIsLoading(false);
      return;
    }

    // ── Safety timeout: never let the loading spinner hang forever ──
    // The fetch below can hang if the gateway is slow / restarting /
    // unreachable.  Without a timeout the user sees a permanent spinner.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    fetch("/api/v1/auth/me", {
      credentials: "include",
      signal: controller.signal,
    })
      .then((r) => {
        clearTimeout(timeout);

        // ── Guard against auth-mechanism mismatch ──
        // The middleware (middleware.ts) checks the `access_token`
        // cookie, but /api/v1/auth/me uses the HttpOnly session
        // cookie.  When the access_token expires before the backend
        // session, the middleware redirects to /login while
        // /api/v1/auth/me still returns 200.  This creates an
        // infinite redirect loop:
        //   login→auth/me(200)→push(workspace)→middleware(no token)→login
        // Check access_token cookie explicitly to break the loop.
        const hasAccessToken =
          typeof document !== "undefined" &&
          document.cookie.includes("access_token=");

        if (r.ok && hasAccessToken) {
          // Both session and access_token are valid — safe to
          // auto-redirect to workspace.
          setIsLoading(false);
          router.push(nextPath);
        } else {
          // Session expired, access_token missing, or CSRF-forced:
          // show the login form so the user can re-authenticate.
          setIsLoading(false);
        }
      })
      .catch(() => {
        clearTimeout(timeout);
        // Fetch failed (timeout, network error, etc.) — always show
        // the login form rather than letting the user stare at a spinner.
        setIsLoading(false);
      });
  }, [router, nextPath, searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/v1/auth/login/ads", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail?.message || data.detail || "登录失败");
        return;
      }
      router.push(nextPath);
    } catch {
      setError("网络错误，请重试");
    } finally {
      setLoading(false);
    }
  };

  const actualTheme = theme === "system" ? resolvedTheme : theme;

  if (isLoading) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center">
        <Loader2Icon className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="bg-background flex min-h-screen items-center justify-center">
      {/* 背景图片 */}
      <div
        className="absolute inset-0 z-0"
        style={{
          backgroundImage: "url('/images/login-background.png')",
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
        }}
      />
      {/* 半透明遮罩 */}
      <div className="absolute inset-0 z-0 bg-black/40" />
      <div className="border-border/20 bg-white/90 w-full max-w-md space-y-6 rounded-3xl border p-8 backdrop-blur-sm">
        <div className="text-center">
          {/* <h1 className="text-foreground font-serif text-3xl">DeerFlow</h1> */}
          <p className="text-black font-medium mt-2 text-2xl">{branding.loginPage?.title ?? "账号登录"}</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-2">
          <div className="flex flex-col space-y-1">
            <label htmlFor="username" className="text-black font-medium">用户名</label>
            <Input
              id="username" className="text-black font-medium border border-solid border-black" type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="输入登录名" required
            />
          </div>
          <div className="flex flex-col space-y-1">
            <label htmlFor="password" className="text-black font-medium">密码</label>
            <Input
              id="password" className="text-black font-medium border border-solid border-black" type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="•••••••" required
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button type="submit" className="w-full mt-4 bg-[#1890ff] hover:bg-[#1580e0] text-white" disabled={loading}>
            {loading ? "登录中..." : "登录"}
          </Button>
        </form>
      </div>
    </div>
  );
}
