"use client";

import { LogOutIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

import { SettingsSection } from "./settings-section";

export function AccountSettingsPage() {
  const { user, logout } = useAuth();
  const { t } = useI18n();

  const displayName = user?.email ? user.email.replace(/@.*$/, "") : "—";

  return (
    <div className="flex flex-col items-center space-y-8">
      {/* 个人信息 */}
      <SettingsSection title={t.settings.account.profileTitle}>
        <div className="flex flex-col items-center gap-4 mt-18 mb-14">
          {/* 登录账号 */}
          <div className="flex items-center gap-3">
            <span className="text-muted-foreground text-sm">登录账号</span>
            <span className="text-sm font-medium">{displayName}</span>
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
            className="gap-2"
          >
            <LogOutIcon className="size-4" />
            {t.settings.account.signOut}
          </Button>
        </div>
      </SettingsSection>
    </div>
  );
}
