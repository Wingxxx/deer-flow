"use client";

import {
  LogOutIcon,
  Settings2Icon,
  SettingsIcon,
  UserIcon,
} from "lucide-react";
// 🚫 以下导入被注释——原因：对应的菜单项（官方网站、Github、报告问题、联系我们、关于DeerFlow）已被注释隐藏，恢复时取消注释即可。
// import {
//   BugIcon,
//   GlobeIcon,
//   InfoIcon,
//   MailIcon,
// } from "lucide-react";
import { useEffect, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
// 🚫 DropdownMenuSeparator 被注释——原因：对应的菜单分隔线已被注释隐藏，恢复时取消注释即可。
// import { DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";
import { getSettingsExtensions } from "@/core/settings-extensions";

// --- EXTENSION IMPORT: begin ---
import "../../../extensions/env-settings/extension";
// --- EXTENSION IMPORT: end ---

import { SettingsDialog } from "./settings";
// 🚫 GithubIcon 导入被注释——原因：对应的 Github 菜单项已被注释隐藏，恢复时取消注释即可。
// import { GithubIcon } from "./github-icon";

/** 将用户名格式化为 "前2位...后2位" */
function maskDisplayName(name: string): string {
  if (name.length <= 4) return name;
  return name.slice(0, 2) + "..." + name.slice(-2);
}

export function WorkspaceNavMenu() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsDefaultSection, setSettingsDefaultSection] = useState<
    "account" | "appearance" | "memory" | "tools" | "skills" | "notification" | "about"
  >("account");
  const [mounted, setMounted] = useState(false);
  const { open: isSidebarOpen } = useSidebar();
  const { t } = useI18n();
  const { user, logout } = useAuth();

  useEffect(() => {
    setMounted(true);
  }, []);

  const extensions = getSettingsExtensions();

  // 获取用户显示名称（取 email 的 @ 前部分）
  const rawName = user?.email?.split("@")[0] ?? user?.id ?? "User";
  const displayName = maskDisplayName(rawName);

  return (
    <>
      <SettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        defaultSection={settingsDefaultSection}
        additionalSections={extensions}
        hiddenSectionIds={["notification","memory","tools","skills","about"]}
      />
      <style>{`
        .nav-menu-hover {
          --sidebar-accent: transparent !important;
          --sidebar-accent-foreground: inherit !important;
          outline: none;
        }
      `}</style>
      <SidebarMenu className="w-full">
        <SidebarMenuItem className="nav-menu-hover">
          {mounted ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton size="lg" className="focus-visible:!ring-0">
                  <div
                    className="flex h-10 w-full shrink-0 items-center justify-between gap-2 px-4 text-sm font-medium select-none bg-white hover:!bg-[#e5e5e5]"
                    style={{
                      color: "#0f1115",
                      border: "1px solid #679efe00",
                      borderRadius: 100,
                      cursor: "pointer",
                      outline: "none",
                      boxShadow:
                        "0 -2px 2px rgba(72,104,178,.04), 0 2px 2px rgba(106,111,117,.09), 0 1px 2px rgba(72,104,178,.08)",
                      transition: "box-shadow .3s",
                    }}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                    <UserIcon className="size-4 shrink-0" />
                    <span className="truncate">{isSidebarOpen ? displayName : ""}</span>
                    </span>
                    {isSidebarOpen && <span className="text-sm font-bold opacity-55 shrink-0">...</span>}
                  </div>
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
                align="end"
                sideOffset={4}
              >
                <DropdownMenuGroup>
                  <DropdownMenuItem
                    className="cursor-pointer"
                    onClick={() => {
                      setSettingsDefaultSection("account");
                      setSettingsOpen(true);
                    }}
                  >
                    <SettingsIcon className="size-4 shrink-0" />
                    {t.common.settings}
                  </DropdownMenuItem>
                  <DropdownMenuItem className="cursor-pointer" onClick={() => logout()}>
                    <LogOutIcon />
                    {t.workspace.logout}
                  </DropdownMenuItem>
                </DropdownMenuGroup>
                {/*
// 🚫 以下菜单项被隐藏——原因：
// 🚫 根据功能自定义需求，左下角"设置和更多"下拉菜单只保留"设置"按钮。
// 🚫 官方网站、Github、报告问题、联系我们、关于DeerFlow 等按钮均隐藏。
// 🚫 如需恢复，删除该注释块即可。
// ================================================================
                  <DropdownMenuSeparator />
                  <a
                    href="https://deerflow.tech/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <DropdownMenuItem>
                      <GlobeIcon />
                      {t.workspace.officialWebsite}
                    </DropdownMenuItem>
                  </a>
                  <a
                    href="https://github.com/bytedance/deer-flow"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <DropdownMenuItem>
                      <GithubIcon />
                      {t.workspace.visitGithub}
                    </DropdownMenuItem>
                  </a>
                  <DropdownMenuSeparator />
                  <a
                    href="https://github.com/bytedance/deer-flow/issues"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <DropdownMenuItem>
                      <BugIcon />
                      {t.workspace.reportIssue}
                    </DropdownMenuItem>
                  </a>
                  <a href="mailto:support@deerflow.tech">
                    <DropdownMenuItem>
                      <MailIcon />
                      {t.workspace.contactUs}
                    </DropdownMenuItem>
                  </a>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => {
                    setSettingsDefaultSection("about");
                    setSettingsOpen(true);
                  }}
                >
                  <InfoIcon />
                  {t.workspace.about}
                </DropdownMenuItem>
*/}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <SidebarMenuButton size="lg" className="pointer-events-none">
              <div
                className="flex h-10 w-full shrink-0 items-center justify-center px-4 text-sm font-medium select-none"
                style={{
                  color: "#0f1115",
                  background: "#fff",
                  border: "1px solid #679efe00",
                  borderRadius: 100,
                  cursor: "pointer",
                  outline: "none",
                  boxShadow:
                    "0 -2px 2px rgba(72,104,178,.04), 0 2px 2px rgba(106,111,117,.09), 0 1px 2px rgba(72,104,178,.08)",
                  transition: "box-shadow .3s",
                }}
              >
                <span className="truncate">{isSidebarOpen ? displayName : ""}</span>
              </div>
            </SidebarMenuButton>
          )}
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}
