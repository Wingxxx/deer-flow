"use client";

import {
  SidebarGroup,
  SidebarMenu,
} from "@/components/ui/sidebar";

/**
 * 🚫 导航项已隐藏——原因：
 * 🚫 根据需求，左侧隐藏「对话」和「智能体」导航链接。
 * 🚫 如需恢复，取消下方注释即可。
 */

export function WorkspaceNavChatList() {
  return (
    <SidebarGroup className="pt-1">
      <SidebarMenu>
        {/*
        <SidebarMenuItem>
          <SidebarMenuButton isActive={pathname === "/workspace/chats"} asChild>
            <Link className="text-muted-foreground" href="/workspace/chats">
              <MessagesSquare />
              <span>{t.sidebar.chats}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton
            isActive={pathname.startsWith("/workspace/agents")}
            asChild
          >
            <Link className="text-muted-foreground" href="/workspace/agents">
              <BotIcon />
              <span>{t.sidebar.agents}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
        */}
      </SidebarMenu>
    </SidebarGroup>
  );
}
