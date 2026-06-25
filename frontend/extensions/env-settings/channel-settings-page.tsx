"use client";

import {
  AlertCircleIcon,
  CheckCircle2Icon,
  CopyIcon,
  EyeIcon,
  EyeOffIcon,
  Loader2Icon,
  MessageSquareIcon,
  ScanQrCodeIcon,
  Trash2Icon,
  XIcon,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SettingsSection } from "@/components/workspace/settings/settings-section";

import { generateQrDataUrl } from "./adapters/channel-adapter";
import {
  useChannelSettings,
  useDeleteChannel,
  useUpdateChannel,
  useVerifyChannel,
} from "./hooks";

export function ChannelSettingsPage() {
  const { settings, isLoading, error } = useChannelSettings();
  const updateMutation = useUpdateChannel();
  const deleteMutation = useDeleteChannel();
  const verifyMutation = useVerifyChannel();

  const [selectedChannelId, setSelectedChannelId] = useState("wecom");
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [showFields, setShowFields] = useState<Record<string, boolean>>({});
  const [statusMessage, setStatusMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [bindingInfo, setBindingInfo] = useState<{
    code: string;
    instruction: string;
    qrDataUrl?: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  const channelInfo = settings?.channels?.[selectedChannelId];
  const selectedCredentialFields = channelInfo?.credentialFields ?? [];
  const channelNames = useMemo(
    () =>
      Object.values(settings?.channels ?? {}).map((c) => ({
        id: c.id,
        name: c.id === "wecom" ? "WeCom(企业微信)" : c.name,
      })),
    [settings],
  );

  const hasAnyValue = useMemo(
    () => Object.values(formValues).some((v) => v.trim()),
    [formValues],
  );
  const hasCredentials = useMemo(
    () =>
      channelInfo &&
      Object.values(channelInfo.credentials).some((v) => v),
    [channelInfo],
  );

  const handleChannelChange = useCallback((id: string) => {
    setSelectedChannelId(id);
    setFormValues({});
    setShowFields({});
    setStatusMessage(null);
    setBindingInfo(null);
    setCopied(false);
  }, []);

  const handleSave = useCallback(async () => {
    if (!hasAnyValue) return;
    setStatusMessage(null);
    setBindingInfo(null);
    try {
      const result = await updateMutation.mutateAsync({
        channel: selectedChannelId,
        credentials: formValues,
      });
      setFormValues({});
      setStatusMessage({
        type: result.success ? "success" : "error",
        text: result.message,
      });
      if (result.connectInfo) {
        let qrDataUrl: string | undefined;
        try {
          qrDataUrl = await generateQrDataUrl(result.connectInfo.code);
        } catch {
          // QR code generation failure should not block the flow.
        }
        setBindingInfo({
          code: result.connectInfo.code,
          instruction: result.connectInfo.instruction,
          qrDataUrl,
        });
      }
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "保存失败",
      });
    }
  }, [formValues, hasAnyValue, selectedChannelId, updateMutation]);

  const handleVerify = useCallback(async () => {
    setStatusMessage(null);
    try {
      const result = await verifyMutation.mutateAsync({
        channel: selectedChannelId,
        credentials:
          hasAnyValue
            ? Object.fromEntries(
                Object.entries(formValues).filter(([, v]) => v.trim()),
              )
            : undefined,
      });
      setStatusMessage({
        type: result.valid ? "success" : "error",
        text: result.message,
      });
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "验证失败",
      });
    }
  }, [formValues, hasAnyValue, selectedChannelId, verifyMutation]);

  const handleDelete = useCallback(async () => {
    setDeleteConfirmOpen(false);
    setStatusMessage(null);
    try {
      const result = await deleteMutation.mutateAsync(selectedChannelId);
      setFormValues({});
      setStatusMessage({ type: "success", text: result.message });
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "清除失败",
      });
    }
  }, [selectedChannelId, deleteMutation]);

  const statusBadge = useMemo(() => {
    if (!channelInfo) return null;

    if (channelInfo.connectionStatus === "connected") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
          <span className="size-1.5 rounded-full bg-green-500" />
          已连接
        </span>
      );
    }

    if (channelInfo.enabled && channelInfo.running) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
          <span className="size-1.5 rounded-full bg-amber-500" />
          已启用·待绑定
        </span>
      );
    }

    if (channelInfo.enabled && !channelInfo.running) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
          <span className="size-1.5 rounded-full bg-amber-500" />
          已配置但未启用
        </span>
      );
    }
    if (Object.values(channelInfo.credentials).some((v) => v)) {
      return (
        <span className="text-muted-foreground inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium">
          已配置
        </span>
      );
    }
    return null;
  }, [channelInfo]);

  return (
    <>
      <SettingsSection
        title={
          <div className="flex items-center gap-2">
            <MessageSquareIcon className="size-5" />
            <span>渠道配置</span>
          </div>
        }
        description="管理 IM 渠道凭据。保存后自动启用渠道并重启。"
      >
        {isLoading ? (
          <div className="text-muted-foreground flex items-center gap-2 py-8 text-sm">
            <Loader2Icon className="size-4 animate-spin" />
            加载中...
          </div>
        ) : error ? (
          <div className="text-destructive py-4 text-sm">
            加载失败: {error.message}
          </div>
        ) : (
          <div className="space-y-5 py-2">
            {/* Channel Selector */}
            <div className="max-w-xs">
              <Select
                value={selectedChannelId}
                onValueChange={handleChannelChange}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择渠道" />
                </SelectTrigger>
                <SelectContent>
                  {channelNames.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Credentials Form Card */}
            <div className="rounded-lg border p-4 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">
                  {channelInfo?.name ?? selectedChannelId}
                </span>
                {statusBadge}
              </div>

              {selectedCredentialFields.map((field) => (
                <div key={field.key} className="space-y-2">
                  <label className="text-sm font-medium">{field.label}</label>
                  {channelInfo?.credentials?.[field.key] && (
                    <div className="text-muted-foreground mb-1 text-xs">
                      当前:{" "}
                      <code className="bg-muted rounded px-1 py-0.5">
                        {channelInfo.credentials[field.key] ?? "****"}
                      </code>
                    </div>
                  )}
                  <div className="relative max-w-md">
                    <Input
                      type={showFields[field.key] ? "text" : "password"}
                      placeholder={`输入${field.label}`}
                      value={formValues[field.key] ?? ""}
                      onChange={(e) =>
                        setFormValues((f) => ({
                          ...f,
                          [field.key]: e.target.value,
                        }))
                      }
                      className="pr-10"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setShowFields((s) => ({
                          ...s,
                          [field.key]: !s[field.key],
                        }))
                      }
                      className="text-muted-foreground hover:text-foreground absolute right-3 top-1/2 -translate-y-1/2"
                      tabIndex={-1}
                    >
                      {showFields[field.key] ? (
                        <EyeOffIcon className="size-4" />
                      ) : (
                        <EyeIcon className="size-4" />
                      )}
                    </button>
                  </div>
                </div>
              ))}

              {/* Action Buttons */}
              <div className="flex items-center gap-2">
                <Button
                  onClick={handleSave}
                  disabled={!hasAnyValue || updateMutation.isPending}
                >
                  {updateMutation.isPending && (
                    <Loader2Icon className="mr-1 size-4 animate-spin" />
                  )}
                  保存
                </Button>
                <Button
                  variant="outline"
                  onClick={handleVerify}
                  disabled={verifyMutation.isPending}
                >
                  {verifyMutation.isPending ? (
                    <Loader2Icon className="size-4 animate-spin" />
                  ) : (
                    "验证连通性"
                  )}
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setDeleteConfirmOpen(true)}
                  disabled={
                    (!hasCredentials && !hasAnyValue) ||
                    deleteMutation.isPending
                  }
                >
                  {deleteMutation.isPending ? (
                    <Loader2Icon className="size-4 animate-spin" />
                  ) : (
                    <Trash2Icon className="mr-1 size-4" />
                  )}
                  清除配置
                </Button>
              </div>

              {/* Status Message */}
              {statusMessage && (
                <div
                  className={`flex items-center gap-1.5 text-sm ${
                    statusMessage.type === "success"
                      ? "text-green-600 dark:text-green-400"
                      : "text-destructive"
                  }`}
                >
                  {statusMessage.type === "success" ? (
                    <CheckCircle2Icon className="size-4" />
                  ) : (
                    <AlertCircleIcon className="size-4" />
                  )}
                  {statusMessage.text}
                </div>
              )}

              {/* Binding Code Guidance */}
              {bindingInfo && (
                <div className="rounded-md border border-blue-200 bg-blue-50 p-4 space-y-3 dark:border-blue-800 dark:bg-blue-950/30">
                  <p className="text-sm font-medium text-blue-700 dark:text-blue-400 flex items-center gap-1.5">
                    <ScanQrCodeIcon className="size-4" />
                    请完成连接码绑定
                  </p>
                  <p className="text-xs text-blue-600 dark:text-blue-400">
                    在企业微信中向 DeerFlow Bot 发送以下指令完成账号绑定：
                  </p>

                  <div className="flex items-start gap-4">
                    <div className="flex-1 min-w-0 space-y-2">
                      <code className="block bg-background rounded px-3 py-2 text-sm font-mono select-all break-all">
                        /connect {bindingInfo.code}
                      </code>
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={() => {
                          void navigator.clipboard.writeText(`/connect ${bindingInfo.code}`);
                          setCopied(true);
                          setTimeout(() => setCopied(false), 2000);
                        }}
                      >
                        <CopyIcon className="size-3.5 mr-1" />
                        {copied ? "已复制" : "复制绑定码"}
                      </Button>
                    </div>

                    {bindingInfo.qrDataUrl && (
                      <div className="shrink-0">
                        <img
                          src={bindingInfo.qrDataUrl}
                          alt="绑定码二维码"
                          className="size-24 rounded border bg-white dark:bg-white"
                        />
                        <p className="text-[10px] text-center text-blue-500 mt-0.5">
                          扫码复制绑定码
                        </p>
                      </div>
                    )}
                  </div>

                  <p className="text-xs text-blue-600 dark:text-blue-400">
                    未绑定前，向 Bot 发送消息会被拦截。绑定码有效期 10 分钟。
                  </p>
                </div>
              )}

              {/* Bottom Tip */}
              <div className="text-muted-foreground border-t pt-3 text-xs">
                配置保存后自动启用渠道。企业微信/飞书/钉钉/微信渠道还需在对应 IM 应用中完成连接码绑定。清除配置后自动禁用。
              </div>
            </div>
          </div>
        )}
      </SettingsSection>

      {/* Delete Confirmation Modal */}
      {deleteConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background rounded-lg border p-6 shadow-lg max-w-sm w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">确认清除</h3>
              <button
                type="button"
                onClick={() => setDeleteConfirmOpen(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <XIcon className="size-4" />
              </button>
            </div>
            <p className="text-muted-foreground text-sm mb-6">
              确定清除 {channelInfo?.name ?? selectedChannelId} 的全部配置？操作不可撤销。
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
                取消
              </Button>
              <Button variant="destructive" onClick={handleDelete}>
                确认清除
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
