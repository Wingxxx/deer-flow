"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  CopyIcon,
  Loader2Icon,
  RefreshCwIcon,
  ScanQrCodeIcon,
  UsersIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { listChannelConnections } from "@/core/channels/api";
import {
  startConnectionPoll,
  type ConnectPollHandle,
} from "@/core/channels/connect-poll";

import { generateQrDataUrl } from "./adapters/channel-adapter";
import {
  channelConnectionsQueryKey,
  channelProviderQueryKey,
  useGenerateInvite,
} from "./hooks";

// ── Types ────────────────────────────────────────────────────────────────────

type InviteState = "idle" | "active" | "expired";

interface InviteSectionProps {
  provider: string;
  hasCredentials: boolean;
  authMode: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

// ── Component ────────────────────────────────────────────────────────────────

export function InviteSection({
  provider,
  hasCredentials,
  authMode,
}: InviteSectionProps) {
  // ---- UI state ----
  const [inviteState, setInviteState] = useState<InviteState>("idle");
  const [code, setCode] = useState("");
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [copied, setCopied] = useState(false);

  // ---- Performance refs (race-condition guard, leak prevention) ----
  const pollRef = useRef<ConnectPollHandle | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const deadlineRef = useRef<number>(0);
  const mountedRef = useRef(true);
  const generationIdRef = useRef(0);
  const qrCacheRef = useRef<Map<string, string>>(new Map());
  /** Snapshot of existing connection IDs before polling starts — excludes
   * pre-existing connections so only genuinely new bindings reset the UI. */
  const initialConnectionIdsRef = useRef<Set<string>>(new Set());

  const generateMutation = useGenerateInvite();
  const queryClient = useQueryClient();

  // ---- Reset helper ----
  const resetToIdle = useCallback(() => {
    setInviteState("idle");
    setCode("");
    setQrDataUrl(null);
    setRemainingSeconds(0);
    pollRef.current?.cancel();
    pollRef.current = null;
  }, []);

  // ---- Lifecycle: cleanup on unmount ----
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      pollRef.current?.cancel();
      pollRef.current = null;
      if (countdownRef.current !== null) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    };
  }, []);

  // ---- Generate invite code (with race-condition guard) ----
  const handleGenerate = useCallback(async () => {
    const genId = ++generationIdRef.current;
    try {
      const result = await generateMutation.mutateAsync(provider);
      if (genId !== generationIdRef.current || !mountedRef.current) return;

      setCode(result.code);
      deadlineRef.current = Date.now() + result.expiresIn * 1000;
      setRemainingSeconds(result.expiresIn);

      // QR code with cache
      let qr: string;
      const cached = qrCacheRef.current.get(result.code);
      if (cached) {
        qr = cached;
      } else {
        qr = await generateQrDataUrl(result.code);
        qrCacheRef.current.set(result.code, qr);
      }
      if (genId !== generationIdRef.current || !mountedRef.current) return;
      setQrDataUrl(qr);

      // Snapshot existing connections so the poll only reacts to NEW bindings.
      // Without this, an admin's own pre-existing connection would immediately
      // trigger onConnected and reset the invite UI (bug: invite code vanishes
      // when user tries to copy/drag it).
      const before = await listChannelConnections();
      initialConnectionIdsRef.current = new Set(
        before
          .filter((c) => c.provider === provider && c.status === "connected")
          .map((c) => c.id),
      );

      // Start polling for NEW connections only
      pollRef.current?.cancel();
      pollRef.current = startConnectionPoll({
        provider,
        expiresInSeconds: result.expiresIn,
        fetchConnections: () => listChannelConnections(),
        initialConnectionIds: initialConnectionIdsRef.current,
        onConnected: () => {
          if (!mountedRef.current) return;
          pollRef.current?.cancel();
          pollRef.current = null;
          void queryClient.invalidateQueries({ queryKey: channelProviderQueryKey });
          void queryClient.invalidateQueries({ queryKey: channelConnectionsQueryKey });
          resetToIdle();
        },
      });

      setInviteState("active");
    } catch (err) {
      if (genId !== generationIdRef.current || !mountedRef.current) return;
      toast.error(err instanceof Error ? err.message : "生成邀请码失败，请重试");
    }
  }, [provider, queryClient, resetToIdle]);

  // ---- Regenerate ----
  const handleRegenerate = useCallback(() => {
    pollRef.current?.cancel();
    pollRef.current = null;
    if (countdownRef.current !== null) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
    void handleGenerate();
  }, [handleGenerate]);

  // ---- Countdown effect (uses absolute deadline ref, avoids stale closure) ----
  useEffect(() => {
    if (inviteState !== "active") return;

    const tick = () => {
      const remaining = Math.max(
        0,
        Math.ceil((deadlineRef.current - Date.now()) / 1000),
      );
      if (!mountedRef.current) return;
      setRemainingSeconds(remaining);
      if (remaining <= 0) {
        if (countdownRef.current !== null) {
          clearInterval(countdownRef.current);
          countdownRef.current = null;
        }
        pollRef.current?.cancel();
        pollRef.current = null;
        setInviteState("expired");
      }
    };

    tick(); // immediate first tick
    countdownRef.current = setInterval(tick, 1000);

    return () => {
      if (countdownRef.current !== null) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    };
  }, [inviteState]);

  // ---- Copy handler ----
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(`/connect ${code}`).catch(() => {
      /* clipboard API may reject in non-HTTPS context — silently ignore */
    });
    setCopied(true);
    setTimeout(() => {
      if (mountedRef.current) setCopied(false);
    }, 2000);
  }, [code]);

  // ---- Gate: only render for binding_code channels with credentials ----
  if (!hasCredentials || authMode !== "binding_code") return null;

  // ═══════════════════════════════════════════════════════════════════════════
  //  Render
  // ═══════════════════════════════════════════════════════════════════════════

  return (
    <div className="rounded-lg border p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <UsersIcon className="size-4 text-muted-foreground" />
        <span className="text-sm font-medium">邀请成员</span>
      </div>
      <p className="text-xs text-muted-foreground">
        生成邀请码，分享给团队成员完成身份绑定
      </p>

      {/* ── IDLE ── */}
      {inviteState === "idle" && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">暂无邀请码</p>
          <Button
            onClick={() => void handleGenerate()}
            disabled={generateMutation.isPending}
          >
            {generateMutation.isPending ? (
              <Loader2Icon className="mr-1 size-4 animate-spin" />
            ) : (
              <ScanQrCodeIcon className="mr-1 size-4" />
            )}
            生成邀请码
          </Button>
        </div>
      )}

      {/* ── ACTIVE ── */}
      {inviteState === "active" && (
        <div className="rounded-md border border-blue-200 bg-blue-50 p-4 space-y-3 dark:border-blue-800 dark:bg-blue-950/30">
          <p className="text-sm font-medium text-blue-700 dark:text-blue-400 flex items-center gap-1.5">
            <ScanQrCodeIcon className="size-4" />
            请在 IM 中完成绑定
          </p>

          <div className="flex items-start gap-4">
            <div className="flex-1 min-w-0 space-y-2">
              <code className="block bg-background rounded px-3 py-2 text-sm font-mono select-all break-all">
                /connect {code}
              </code>
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={handleCopy}
              >
                <CopyIcon className="size-3.5 mr-1" />
                {copied ? "已复制" : "复制绑定码"}
              </Button>
            </div>

            {qrDataUrl && (
              <div className="shrink-0">
                <img
                  src={qrDataUrl}
                  alt="绑定码二维码"
                  className="size-24 rounded border bg-white dark:bg-white"
                />
                <p className="text-[10px] text-center text-blue-500 mt-0.5">
                  扫码复制绑定码
                </p>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-blue-600 dark:text-blue-400">
              绑定码有效期 {formatTime(remainingSeconds)}
            </span>
            <Button variant="ghost" size="sm" onClick={handleRegenerate}>
              <RefreshCwIcon className="size-3.5 mr-1" />
              重新生成
            </Button>
          </div>
        </div>
      )}

      {/* ── EXPIRED ── */}
      {inviteState === "expired" && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">邀请码已过期</p>
          <Button
            variant="outline"
            onClick={handleRegenerate}
          >
            <RefreshCwIcon className="mr-1 size-4" />
            重新生成
          </Button>
        </div>
      )}
    </div>
  );
}
