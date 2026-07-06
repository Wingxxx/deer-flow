"use client";

import { MessageSquarePlus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import { env } from "@/env";
import { cn } from "@/lib/utils";
import { useBranding } from "../../../extensions/branding/context";

export function WorkspaceHeader({ className }: { className?: string }) {
  const { appName = "", appAbbreviation = "" } = useBranding();
  const { t } = useI18n();
  const { state } = useSidebar();
  const pathname = usePathname();
  return (
    <>
      <div
        className={cn(
          "group/workspace-header flex h-12 flex-col justify-center",
          className,
        )}
      >
        {state === "collapsed" ? (
          <div className="group-has-data-[collapsible=icon]/sidebar-wrapper:-translate-y flex w-full cursor-pointer items-center justify-center">
            <div className="text-[#fff] block pt-1 font-serif group-hover/workspace-header:hidden">
              {appAbbreviation}
            </div>
            <SidebarTrigger className="hidden pl-2 group-hover/workspace-header:block" />
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" ? (
              <Link href="/" className="text-[#fff] ml-2 font-serif">
                {appName}
              </Link>
            ) : (
              <div className="text-[#fff] ml-2 cursor-default font-serif">
                {appName}
              </div>
            )}
            <SidebarTrigger />
          </div>
        )}
      </div>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            isActive={pathname === "/workspace/chats/new"}
            asChild
          >
            <Link
              className="flex h-10 w-full shrink-0 items-center px-4 text-sm font-medium select-none"
              style={{
                color: "#0f1115",
                background: "#fff",
                border: "1px solid #679efe00",
                borderRadius: 100,
                justifyContent: "center",
                cursor: "pointer",
                outline: "none",
                boxShadow:
                  "0 -2px 2px rgba(72,104,178,.04), 0 2px 2px rgba(106,111,117,.09), 0 1px 2px rgba(72,104,178,.08)",
                transition: "box-shadow .3s",
              }}
              href="/workspace/chats/new"
            >
              <MessageSquarePlus size={16} />
              <span>{t.sidebar.newChat}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}
