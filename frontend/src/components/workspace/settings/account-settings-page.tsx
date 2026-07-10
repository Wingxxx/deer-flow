"use client";

import { useMemo } from "react";
import { LogOutIcon, MonitorIcon, UserIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

import { SettingsSection } from "./settings-section";

/** 解析 userAgent 获取操作系统名称 */
function getOS(ua: string): string {
  if (ua.includes("Windows NT")) return "Windows";
  if (ua.includes("Mac OS X")) return "macOS";
  if (ua.includes("Linux")) return "Linux";
  if (ua.includes("Android")) return "Android";
  if (ua.includes("iPhone") || ua.includes("iPad")) return "iOS";
  return "—";
}

export function AccountSettingsPage() {
  const { user, logout } = useAuth();
  const { t } = useI18n();

  const displayName = user?.email ? user.email.replace(/@.*$/, "") : "—";

  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const os = useMemo(() => getOS(ua), [ua]);

  return (
    <div className="flex flex-col space-y-8 w-full">
      <SettingsSection title={t.settings.account.profileTitle} icon={UserIcon}>
        <div className="flex flex-col items-center gap-6 mt-8 mb-6">
          {/* 通用个人信息图标 - 渐变背景 */}
          <div className="flex size-[80px] items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 shadow-sm">
            <UserIcon className="size-10 text-white" />
          </div>

          {/* 名称 */}
          <div className="text-center">
            <div className="text-lg font-semibold">{displayName}</div>
          </div>

          {/* 信息列表 - 精简样式 */}
          <div className="max-w-xs space-y-3">
            {/* 登录账号 */}
            <div className="flex items-center gap-3">
              <div className="flex size-8 items-center justify-center rounded-full bg-muted shrink-0">
                <UserIcon className="size-4 text-muted-foreground" />
              </div>
              <span className="text-sm text-foreground/70">登录账号</span>
              <span className="text-sm font-medium ml-auto">{displayName}</span>
            </div>
            {/* 操作系统 */}
            <div className="flex items-center gap-3">
              <div className="flex size-8 items-center justify-center rounded-full bg-muted shrink-0">
                <MonitorIcon className="size-4 text-muted-foreground" />
              </div>
              <span className="text-sm text-foreground/70">{t.settings.account.os}</span>
              <span className="text-sm font-medium ml-auto">{os}</span>
            </div>
          </div>
        </div>
      </SettingsSection>

      {/* 退出登录 */}
      <SettingsSection title="" description="">
        <div className="flex justify-center">
          <Button
            variant="destructive"
            size="sm"
            onClick={logout}
            className="gap-2 cursor-pointer"
          >
            <LogOutIcon className="size-4" />
            {t.settings.account.signOut}
          </Button>
        </div>
      </SettingsSection>
    </div>
  );
}
