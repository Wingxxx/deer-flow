"use client";

import {
  Download,
  FileJson,
  FileText,
  MoreHorizontal,
  Check,
  Copy,
  Pencil,
  Pin,
  Share2,
  TriangleAlert,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { resetThreadChatAfterDelete } from "@/components/workspace/chats/use-thread-chat";
import { getAPIClient } from "@/core/api";
import { writeTextToClipboard } from "@/core/clipboard";
import { useI18n } from "@/core/i18n/hooks";
import {
  exportThreadAsJSON,
  exportThreadAsMarkdown,
} from "@/core/threads/export";
import {
  useDeleteThread,
  useInfiniteThreads,
  useRenameThread,
} from "@/core/threads/hooks";
import type { AgentThread, AgentThreadState } from "@/core/threads/types";
import {
  channelSourceOfThread,
  pathOfThread,
  titleOfThread,
} from "@/core/threads/utils";
import { env } from "@/env";
import { isIMEComposing } from "@/lib/ime";

import { ThreadChannelIcon } from "./thread-channel-source";
import { usePinnedThreads } from "@/core/threads/use-pinned-threads";
import { cn } from "@/lib/utils";

export function RecentChatList() {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const { thread_id: threadIdFromPath, agent_name: agentNameFromPath } =
    useParams<{
      thread_id: string;
      agent_name?: string;
    }>();
  const {
    data: infiniteThreads,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteThreads();
  const threads = useMemo(
    () => infiniteThreads?.pages.flat() ?? [],
    [infiniteThreads],
  );

  const { isPinned, togglePin, pinOrder } = usePinnedThreads();

  const [pinnedThreads, unpinnedThreads] = useMemo(() => {
    const pinned: typeof threads = [];
    const unpinned: typeof threads = [];
    const sorted = [...threads].sort((a, b) => {
      const aPinned = pinOrder.get(a.thread_id);
      const bPinned = pinOrder.get(b.thread_id);
      if (aPinned !== undefined && bPinned !== undefined)
        return aPinned - bPinned;
      if (aPinned !== undefined) return -1;
      if (bPinned !== undefined) return 1;
      return 0;
    });
    for (const t of sorted) {
      if (pinOrder.has(t.thread_id)) {
        pinned.push(t);
      } else {
        unpinned.push(t);
      }
    }
    return [pinned, unpinned];
  }, [threads, pinOrder]);

  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const element = sentinelRef.current;
    if (!element || !hasNextPage) {
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      { rootMargin: "120px 0px 120px 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  const { mutate: deleteThread } = useDeleteThread();
  const { mutate: renameThread } = useRenameThread();

  // Rename dialog state
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameThreadId, setRenameThreadId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [shareThreadUrl, setShareThreadUrl] = useState("");
  const [shareCopied, setShareCopied] = useState(false);

  const handleDelete = useCallback(
    (thread: AgentThread) => {
      const currentPathname =
        typeof window === "undefined" ? pathname : window.location.pathname;
      const threadPath = pathOfThread(thread);
      const nextThreadPath = pathOfThread("new", {
        agent_name: agentNameFromPath,
      });
      const isNewThreadPath = currentPathname === nextThreadPath;
      const isCurrentThread =
        thread.thread_id === threadIdFromPath ||
        threadPath === currentPathname ||
        (isNewThreadPath && threads[0]?.thread_id === thread.thread_id);

      deleteThread({
        threadId: thread.thread_id,
        onRemoteDeleted: isCurrentThread
          ? () => {
              resetThreadChatAfterDelete({
                deletedThreadId: thread.thread_id,
                nextPath: nextThreadPath,
                force: true,
              });
              void router.replace(nextThreadPath);
            }
          : undefined,
      });
    },
    [
      agentNameFromPath,
      deleteThread,
      pathname,
      router,
      threadIdFromPath,
      threads,
    ],
  );

  const handleRenameClick = useCallback(
    (threadId: string, currentTitle: string) => {
      setRenameThreadId(threadId);
      setRenameValue(currentTitle);
      setRenameDialogOpen(true);
    },
    [],
  );

  const handleRenameSubmit = useCallback(() => {
    if (renameThreadId && renameValue.trim()) {
      renameThread({ threadId: renameThreadId, title: renameValue.trim() });
      setRenameDialogOpen(false);
      setRenameThreadId(null);
      setRenameValue("");
    }
  }, [renameThread, renameThreadId, renameValue]);

  const handleShare = useCallback(
    (thread: AgentThread) => {
      // Always use Vercel URL for sharing so others can access
      const VERCEL_URL = "https://deer-flow-v2.vercel.app";
      const isLocalhost =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1";
      // On localhost: use Vercel URL; On production: use current origin
      const baseUrl = isLocalhost ? VERCEL_URL : window.location.origin;
      const shareUrl = `${baseUrl}${pathOfThread(thread)}`;
      setShareThreadUrl(shareUrl);
      setShareCopied(false);
      setShareDialogOpen(true);
    },
    [],
  );

  const handleExport = useCallback(
    async (thread: AgentThread, format: "markdown" | "json") => {
      try {
        const apiClient = getAPIClient();
        const state = await apiClient.threads.getState<AgentThreadState>(
          thread.thread_id,
        );
        const messages = state.values?.messages ?? [];
        if (messages.length === 0) {
          toast.error(t.conversation.noMessages);
          return;
        }
        if (format === "markdown") {
          exportThreadAsMarkdown(thread, messages);
        } else {
          exportThreadAsJSON(thread, messages);
        }
        toast.success(t.common.exportSuccess);
      } catch {
        toast.error("Failed to export conversation");
      }
    },
    [t],
  );

  if (threads.length === 0) {
    return null;
  }
  return (
    <>
      <style>{`
        .recent-chat-item [data-slot="sidebar-menu-button"]:hover {
          background-color: #e4edfd !important;
          color: #000000 !important;
        }
        .recent-chat-item [data-sidebar="menu-action"] {
          background-color: rgba(255, 255, 255, 0.06) !important;
          border-radius: 6px !important;
          color: rgba(255, 255, 255, 0.6) !important;
        }
        .recent-chat-item:hover [data-sidebar="menu-action"] {
          background-color: rgba(0, 0, 0, 0.1) !important;
          color: #1A3454 !important;
          opacity: 1 !important;
        }
        .recent-chat-item [data-sidebar="menu-action"]:hover {
          background-color: rgba(0, 0, 0, 0.15) !important;
          color: #1A3454 !important;
        }
        .recent-chat-item [data-slot="sidebar-menu-button"][data-active="true"] [data-sidebar="menu-action"] {
          background-color: rgba(0, 0, 0, 0.08) !important;
          color: #1A3454 !important;
          opacity: 1 !important;
        }
        .recent-chat-item [data-slot="sidebar-menu-button"][data-active="true"] [data-sidebar="menu-action"]:hover {
          background-color: rgba(0, 0, 0, 0.15) !important;
          color: #1A3454 !important;
        }
        .recent-chat-item:hover [data-slot="sidebar-menu-button"][data-active="true"] [data-sidebar="menu-action"] {
          background-color: rgba(0, 0, 0, 0.12) !important;
        }
        .recent-chat-item:hover [data-slot="sidebar-menu-button"][data-active="true"] [data-sidebar="menu-action"]:hover {
          background-color: rgba(0, 0, 0, 0.2) !important;
        }
      `}</style>
      {pinnedThreads.length > 0 && (
        <SidebarGroup>
          <SidebarGroupLabel>{t.sidebar.pinned}</SidebarGroupLabel>
          <SidebarGroupContent className="group-data-[collapsible=icon]:pointer-events-none group-data-[collapsible=icon]:-mt-8 group-data-[collapsible=icon]:opacity-0">
            <SidebarMenu>
              <div className="flex w-full flex-col gap-1">
                {pinnedThreads.map((thread) => {
                  const isActive = pathOfThread(thread) === pathname;
                  const channelSource = channelSourceOfThread(thread);
                  return (
                    <SidebarMenuItem
                      key={thread.thread_id}
                      className="group/side-menu-item recent-chat-item"
                    >
                      <SidebarMenuButton isActive={isActive} asChild>
                        <div
                          onClick={() => router.push(pathOfThread(thread))}
                          className="relative cursor-pointer"
                        >
                          <div className="flex min-w-0 items-center gap-1.5 whitespace-nowrap group-hover/side-menu-item:overflow-hidden hover:text-[#000000]">
                            <ThreadChannelIcon source={channelSource} />
                            <span className="min-w-0 truncate">
                              {titleOfThread(thread)}
                            </span>
                            {channelSource && (
                              <span
                                className="bg-muted text-muted-foreground ml-auto inline-flex h-5 max-w-14 shrink-0 items-center rounded-md px-1.5 text-[10px] font-medium"
                                title={`${channelSource.label} channel`}
                              >
                                <span className="truncate">{channelSource.label}</span>
                              </span>
                            )}
                          </div>
                          {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" && (
                            <PinButton
                              isPinned={isPinned(thread.thread_id)}
                              onToggle={() => togglePin(thread.thread_id)}
                            />
                          )}
                          {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" && (
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <SidebarMenuAction
                                  showOnHover
                                  onClick={(e: React.MouseEvent) => e.stopPropagation()}
                                >
                                  <MoreHorizontal />
                                  <span className="sr-only">{t.common.more}</span>
                                </SidebarMenuAction>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent className="w-48 rounded-lg" side={"right"} align={"start"}>
                                <DropdownMenuItem onSelect={() => togglePin(thread.thread_id)} className="cursor-pointer">
                                  <Pin
                                    className={cn(
                                      "size-4",
                                      isPinned(thread.thread_id)
                                        ? "fill-current text-foreground"
                                        : "text-muted-foreground",
                                    )}
                                  />
                                  <span>{isPinned(thread.thread_id) ? t.common.unpin : t.common.pin}</span>
                                </DropdownMenuItem>
                                <DropdownMenuItem onSelect={() => handleRenameClick(thread.thread_id, titleOfThread(thread))} className="cursor-pointer">
                                  <Pencil className="text-muted-foreground" />
                                  <span>{t.common.rename}</span>
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onSelect={() => handleShare(thread)} className="cursor-pointer">
                                  <Share2 className="text-muted-foreground" />
                                  <span>{t.common.share}</span>
                                </DropdownMenuItem>
                                <DropdownMenuSub>
                                  <DropdownMenuSubTrigger>
                                    <Download className="text-muted-foreground" />
                                    <span>{t.common.export}</span>
                                  </DropdownMenuSubTrigger>
                                  <DropdownMenuSubContent>
                                    <DropdownMenuItem onSelect={() => handleExport(thread, "markdown")} className="cursor-pointer">
                                      <FileText className="text-muted-foreground" />
                                      <span>{t.common.exportAsMarkdown}</span>
                                    </DropdownMenuItem>
                                    <DropdownMenuItem onSelect={() => handleExport(thread, "json")} className="cursor-pointer">
                                      <FileJson className="text-muted-foreground" />
                                      <span>{t.common.exportAsJSON}</span>
                                    </DropdownMenuItem>
                                  </DropdownMenuSubContent>
                                </DropdownMenuSub>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onSelect={() => handleDelete(thread)} className="text-red-500 hover:text-red-500 focus:text-red-500 hover:bg-red-50 focus:bg-red-50 cursor-pointer">
                                  <Trash2 className="text-[#ec1313]" />
                                  <span>{t.common.delete}</span>
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          )}
                        </div>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </div>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      )}

      <SidebarGroup>
        <SidebarGroupLabel>
          {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true"
            ? t.sidebar.recentChats
            : t.sidebar.demoChats}
        </SidebarGroupLabel>
        <SidebarGroupContent className="group-data-[collapsible=icon]:pointer-events-none group-data-[collapsible=icon]:-mt-8 group-data-[collapsible=icon]:opacity-0">
          <SidebarMenu>
            <div className="flex w-full flex-col gap-1">
              {unpinnedThreads.map((thread) => {
                const isActive = pathOfThread(thread) === pathname;
                const channelSource = channelSourceOfThread(thread);
                return (
                  <SidebarMenuItem
                    key={thread.thread_id}
                    className="group/side-menu-item recent-chat-item"
                  >
                    <SidebarMenuButton isActive={isActive} asChild>
                      <div
                        onClick={() => router.push(pathOfThread(thread))}
                        className="relative cursor-pointer"
                      >
                        <div className="flex min-w-0 items-center gap-1.5 whitespace-nowrap group-hover/side-menu-item:overflow-hidden hover:text-[#000000]">
                          <ThreadChannelIcon source={channelSource} />
                          <span className="min-w-0 truncate">
                            {titleOfThread(thread)}
                          </span>
                          {channelSource && (
                            <span
                              className="bg-muted text-muted-foreground ml-auto inline-flex h-5 max-w-14 shrink-0 items-center rounded-md px-1.5 text-[10px] font-medium"
                              title={`${channelSource.label} channel`}
                            >
                              <span className="truncate">{channelSource.label}</span>
                            </span>
                          )}
                        </div>
                        {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" && (
                          <PinButton
                            isPinned={isPinned(thread.thread_id)}
                            onToggle={() => togglePin(thread.thread_id)}
                          />
                        )}
                        {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <SidebarMenuAction
                                showOnHover
                                onClick={(e: React.MouseEvent) => e.stopPropagation()}
                              >
                                <MoreHorizontal />
                                <span className="sr-only">{t.common.more}</span>
                              </SidebarMenuAction>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent className="w-48 rounded-lg" side={"right"} align={"start"}>
                              <DropdownMenuItem onSelect={() => togglePin(thread.thread_id)} className="cursor-pointer">
                                <Pin
                                  className={cn(
                                    "size-4",
                                    isPinned(thread.thread_id)
                                      ? "fill-current text-foreground"
                                      : "text-muted-foreground",
                                  )}
                                />
                                <span>{isPinned(thread.thread_id) ? t.common.unpin : t.common.pin}</span>
                              </DropdownMenuItem>
                              <DropdownMenuItem onSelect={() => handleRenameClick(thread.thread_id, titleOfThread(thread))} className="cursor-pointer">
                                <Pencil className="text-muted-foreground" />
                                <span>{t.common.rename}</span>
                              </DropdownMenuItem>
                              <DropdownMenuItem onSelect={() => handleShare(thread)} className="cursor-pointer">
                                <Share2 className="text-muted-foreground" />
                                <span>{t.common.share}</span>
                              </DropdownMenuItem>
                              <DropdownMenuSub>
                                <DropdownMenuSubTrigger>
                                  <Download className="text-muted-foreground" />
                                  <span>{t.common.export}</span>
                                </DropdownMenuSubTrigger>
                                <DropdownMenuSubContent>
                                  <DropdownMenuItem onSelect={() => handleExport(thread, "markdown")} className="cursor-pointer">
                                    <FileText className="text-muted-foreground" />
                                    <span>{t.common.exportAsMarkdown}</span>
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onSelect={() => handleExport(thread, "json")} className="cursor-pointer">
                                    <FileJson className="text-muted-foreground" />
                                    <span>{t.common.exportAsJSON}</span>
                                  </DropdownMenuItem>
                                </DropdownMenuSubContent>
                              </DropdownMenuSub>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onSelect={() => handleDelete(thread)} className="text-red-500 hover:text-red-500 focus:text-red-500 hover:bg-red-50 focus:bg-red-50 cursor-pointer">
                                <Trash2 className="text-[#ec1313]" />
                                <span>{t.common.delete}</span>
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </div>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
              {hasNextPage && (
                <>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mx-2 my-1 w-[calc(100%-1rem)] justify-center text-xs"
                    onClick={() => void fetchNextPage()}
                    disabled={isFetchingNextPage}
                    data-testid="recent-chat-list-load-more"
                  >
                    {isFetchingNextPage
                      ? t.chats.loadingMore
                      : t.chats.loadOlderChats}
                  </Button>
                  <div
                    ref={sentinelRef}
                    aria-hidden="true"
                    className="h-px w-full"
                    data-testid="recent-chat-list-sentinel"
                  />
                </>
              )}
            </div>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      {/* Rename Dialog */}
      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>{t.common.rename}</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Input
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder={t.common.rename}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isIMEComposing(e)) {
                  e.preventDefault();
                  handleRenameSubmit();
                }
              }}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRenameDialogOpen(false)}
            >
              {t.common.cancel}
            </Button>
            <Button onClick={handleRenameSubmit}>{t.common.save}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* Share Dialog */}
      <Dialog open={shareDialogOpen} onOpenChange={setShareDialogOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>{t.common.share}</DialogTitle>
          </DialogHeader>
          <div className="space-y-6 py-2">
            {/* Share Link */}
            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={shareThreadUrl}
                className="flex-1 h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
              <Button
                variant="outline"
                size="icon"
                className="size-9 shrink-0"
                onClick={async () => {
                  const didCopy = await writeTextToClipboard(shareThreadUrl);
                  if (didCopy) {
                    setShareCopied(true);
                    toast.success(t.clipboard.linkCopied);
                    setTimeout(() => setShareCopied(false), 2000);
                  } else {
                    toast.error(t.clipboard.failedToCopyToClipboard);
                  }
                }}
              >
                {shareCopied ? <Check className="size-4 text-green-500" /> : <Copy className="size-4" />}
              </Button>
            </div>

            {/* Share Warning */}
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <TriangleAlert className="size-4 mt-0.5 shrink-0 text-amber-600" />
              <p className="text-xs text-amber-700 leading-relaxed">
                任何获得链接的人都可以查看你的分享内容，请检查是否包含敏感或隐私内容。
              </p>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

type PinButtonProps = {
  isPinned: boolean;
  onToggle: () => void;
};

function PinButton({ isPinned, onToggle }: PinButtonProps) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      className={cn(
        "absolute right-8 top-1/2 -translate-y-1/2 flex items-center justify-center rounded-md p-1 transition-all opacity-0 group-hover/side-menu-item:opacity-100 hover:bg-accent cursor-pointer",
      )}
      title={isPinned ? t.common.unpin : t.common.pin}
    >
      <Pin
        className={cn(
          "size-3.5 transition-colors",
          isPinned
            ? "fill-current text-foreground"
            : "text-muted-foreground",
        )}
      />
    </button>
  );
}
