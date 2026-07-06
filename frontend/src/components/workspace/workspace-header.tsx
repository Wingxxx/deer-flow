"use client";

import { Search, MessageSquarePlus } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import { useInfiniteThreads } from "@/core/threads/hooks";
import { pathOfThread, titleOfThread } from "@/core/threads/utils";
import { env } from "@/env";
import { cn } from "@/lib/utils";
import { useBranding } from "../../../extensions/branding/context";

export function WorkspaceHeader({ className }: { className?: string }) {
  const { appName = "开天智能客服", appAbbreviation = "开天智能客服" } = useBranding();
  const { t } = useI18n();
  const { state } = useSidebar();
  const pathname = usePathname();
  const router = useRouter();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchListRef = useRef<HTMLDivElement>(null);

  const { data: infiniteThreads } = useInfiniteThreads();
  const threads = useMemo(
    () => infiniteThreads?.pages.flat() ?? [],
    [infiniteThreads],
  );

  const filteredThreads = useMemo(() => {
    if (!searchQuery.trim()) return threads;
    const q = searchQuery.toLowerCase();
    return threads.filter((thread) => {
      const title = titleOfThread(thread).toLowerCase();
      return title.includes(q);
    });
  }, [threads, searchQuery]);

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(-1);
  }, [filteredThreads]);

  // Scroll selected item into view
  const scrollToSelected = useCallback(() => {
    if (selectedIndex < 0 || !searchListRef.current) return;
    const items = searchListRef.current.querySelectorAll<HTMLButtonElement>(
      "[data-search-item]",
    );
    items[selectedIndex]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedIndex]);

  useEffect(() => {
    scrollToSelected();
  }, [selectedIndex, scrollToSelected]);

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
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                onClick={() => {
                  setSearchOpen(true);
                  setTimeout(() => searchInputRef.current?.focus(), 100);
                }}
                className="inline-flex items-center justify-center rounded-md text-sm font-medium outline-none transition-all hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50 size-7 opacity-50 hover:opacity-100"
                aria-label="Search conversations"
              >
                <Search className="size-4" />
              </button>
              <SidebarTrigger />
            </div>
          </div>
        )}
      </div>
      <style>{`
        .workspace-header-newchat {
          transition: all 0.25s ease !important;
          will-change: transform, box-shadow;
        }
        .workspace-header-newchat:hover {
          transform: translateY(-1px) !important;
          border-color: rgba(74, 108, 247, .35) !important;
          box-shadow:
            0 1px 0 rgba(255,255,255,.5) inset,
            0 -1px 0 rgba(0,0,0,.08) inset,
            0 4px 12px rgba(74, 108, 247, .15),
            0 16px 32px rgba(0,0,0,.3),
            0 8px 16px rgba(0,0,0,.18) !important;
        }
      `}</style>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            isActive={pathname === "/workspace/chats/new"}
            asChild
          >
            <Link
              className="flex h-10 w-full shrink-0 items-center px-4 text-sm font-medium select-none workspace-header-newchat"
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
              }}
              href="/workspace/chats/new"
            >
              <MessageSquarePlus size={16} />
              <span>{t.sidebar.newChat}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>

      {/* Search Dialog */}
      {searchOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 pt-[15vh]"
            onClick={() => setSearchOpen(false)}
          >
            <div
              className="bg-popover text-popover-foreground mx-4 w-full max-w-lg rounded-lg border shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-2 border-b px-4">
                <Search className="text-muted-foreground size-4 shrink-0" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="搜索最近对话"
                  className="flex h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      setSearchOpen(false);
                    } else if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setSelectedIndex((prev) =>
                        prev < filteredThreads.length - 1 ? prev + 1 : 0,
                      );
                    } else if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setSelectedIndex((prev) =>
                        prev > 0 ? prev - 1 : filteredThreads.length - 1,
                      );
                    } else if (e.key === "Enter") {
                      e.preventDefault();
                      if (selectedIndex >= 0 && selectedIndex < filteredThreads.length) {
                        const thread = filteredThreads[selectedIndex];
                        setSearchOpen(false);
                        setSearchQuery("");
                        router.push(pathOfThread(thread));
                        setTimeout(() => {
                          const activeItem = document.querySelector(
                            '[data-slot="sidebar-menu-button"][data-active="true"]',
                          );
                          activeItem?.scrollIntoView({
                            block: "nearest",
                            behavior: "smooth",
                          });
                        }, 200);
                      }
                    }
                  }}
                />
              </div>
              <div className="max-h-[50vh] overflow-y-auto p-2">
                {filteredThreads.length === 0 ? (
                  <div className="text-muted-foreground py-8 text-center text-sm">
                    {searchQuery.trim()
                      ? "No conversations found"
                      : "No conversations yet"}
                  </div>
                ) : (
                  <div ref={searchListRef} className="flex flex-col gap-0.5">
                    {filteredThreads.map((thread, index) => (
                      <button
                        key={thread.thread_id}
                        data-search-item
                        type="button"
                        onClick={() => {
                          setSearchOpen(false);
                          setSearchQuery("");
                          router.push(pathOfThread(thread));
                          setTimeout(() => {
                            const activeItem = document.querySelector(
                              '[data-slot="sidebar-menu-button"][data-active="true"]',
                            );
                            activeItem?.scrollIntoView({
                              block: "nearest",
                              behavior: "smooth",
                            });
                          }, 200);
                        }}
                        className={cn(
                          "flex items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm transition-colors",
                          index === selectedIndex ? "bg-accent" : "hover:bg-accent",
                        )}
                      >
                        <div className="flex min-w-0 flex-1 flex-col">
                          <span className="truncate font-medium">
                            {titleOfThread(thread)}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
