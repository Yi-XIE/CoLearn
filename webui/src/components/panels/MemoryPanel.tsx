import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, Save, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  clearMemoryDocument,
  fetchMemorySummary,
  fetchSettings,
  refreshMemoryDocument,
  updateMemoryDocument,
  updateMemorySettings,
} from "@/lib/api";
import type { MemoryDocPayload, MemoryDocumentName, MemorySummaryPayload } from "@/lib/types";
import { cn } from "@/lib/utils";

import { PanelView, type PanelShellProps } from "./PanelView";

type MemoryBusyKey =
  | MemoryDocumentName
  | "refresh"
  | "toggle"
  | `clear-${MemoryDocumentName}`;

const MEMORY_DOCUMENT_COPY: Record<MemoryDocumentName, { placeholder: string }> = {
  summary: {
    placeholder: "记录稳定的学习结论、偏好和上下文。",
  },
  profile: {
    placeholder: "记录已经确认的长期偏好、目标和背景。",
  },
};

function memoryDocumentLabel(file: MemoryDocumentName): string {
  return file === "summary" ? "学习摘要" : "个人画像";
}

function MemorySectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="px-1 font-sans text-[14px] font-semibold tracking-normal text-foreground/92">
      {children}
    </h2>
  );
}

function MemorySectionHint({ children }: { children: ReactNode }) {
  return (
    <p className="px-1 font-sans text-[13px] leading-5 text-muted-foreground">
      {children}
    </p>
  );
}

function MemoryGroup({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-border/60 bg-card/88 font-sans shadow-[0_16px_48px_rgba(15,23,42,0.055)]",
        className,
      )}
    >
      <div className="divide-y divide-border/50">{children}</div>
    </div>
  );
}

function MemoryDocumentEditor({
  file,
  value,
  dirty,
  busy,
  disabled,
  onChange,
  onSave,
}: {
  file: MemoryDocumentName;
  value: string;
  dirty: boolean;
  busy: MemoryBusyKey | null;
  disabled: boolean;
  onChange: (value: string) => void;
  onSave: () => void;
}) {
  const copy = MEMORY_DOCUMENT_COPY[file];
  const saving = busy === file;
  const isBusy = !!busy;
  return (
    <div className="space-y-2">
      <Textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={copy.placeholder}
        disabled={disabled}
        className="min-h-[184px] resize-y rounded-lg border border-border/80 bg-card/90 px-3 py-3 text-[13px] leading-6 shadow-none focus-visible:border-border focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-0"
      />
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={onSave}
          disabled={isBusy || disabled || !dirty}
          className="h-8 rounded-full px-3 text-[12px] font-medium"
        >
          {saving ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
          ) : (
            <Save className="mr-1.5 h-3.5 w-3.5" aria-hidden />
          )}
          保存
        </Button>
      </div>
    </div>
  );
}

function MemorySettingRow({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-[78px] flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="min-w-0 flex-1">
        <div className="text-[14px] font-medium leading-5 text-foreground">{title}</div>
        <div className="mt-1 max-w-[34rem] text-[12px] leading-5 text-muted-foreground">
          {description}
        </div>
      </div>
      <div className="flex shrink-0 items-center self-end sm:ml-6 sm:self-center">{children}</div>
    </div>
  );
}

function MemorySwitch({
  active,
  disabled,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "relative inline-flex h-7 w-12 items-center rounded-full p-1 transition-[background-color,transform,box-shadow] duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:scale-[0.98]",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        active ? "bg-[#4a4a4a]" : "bg-[#7a7a7a]",
      )}
    >
      <span
        className={cn(
          "block h-5 w-5 rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.28)] transition-transform duration-200 ease-out will-change-transform",
          active ? "translate-x-5" : "translate-x-0",
        )}
      />
    </button>
  );
}

interface MemoryPanelProps extends PanelShellProps {
  token: string;
}

export function MemoryPanel({ token, ...panelProps }: MemoryPanelProps) {
  const [payload, setPayload] = useState<MemorySummaryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [drafts, setDrafts] = useState<Record<MemoryDocumentName, string>>({
    summary: "",
    profile: "",
  });
  const [busy, setBusy] = useState<MemoryBusyKey | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [memoryEnabled, setMemoryEnabled] = useState(true);

  const applyMemoryDocuments = useCallback((snapshot: MemoryDocPayload) => {
    setPayload((current) =>
      current
        ? {
            ...current,
            summary: snapshot.summary,
            profile: snapshot.profile,
            summary_updated_at: snapshot.summary_updated_at,
            profile_updated_at: snapshot.profile_updated_at,
          }
        : current,
    );
    setDrafts({
      summary: snapshot.summary,
      profile: snapshot.profile,
    });
  }, []);

  const loadMemory = useCallback(async () => {
    setLoading(true);
    setNotice(null);
    const [memoryResult, settingsResult] = await Promise.allSettled([
      fetchMemorySummary(token),
      fetchSettings(token),
    ]);
    if (memoryResult.status === "fulfilled") {
      setPayload(memoryResult.value);
      setDrafts({
        summary: memoryResult.value.summary,
        profile: memoryResult.value.profile,
      });
    } else {
      console.warn("Failed to load memory summary", memoryResult.reason);
      setNotice("记忆面板加载失败，请稍后重试。");
    }
    if (settingsResult.status === "fulfilled") {
      setMemoryEnabled(settingsResult.value.memory.enabled);
    } else {
      console.warn("Failed to load memory settings", settingsResult.reason);
      setNotice((current) => current ?? "记忆开关状态加载失败，已使用默认值。");
    }
    setLoading(false);
  }, [token]);

  useEffect(() => {
    void loadMemory();
  }, [loadMemory]);

  const saveDocument = async (file: MemoryDocumentName) => {
    if (busy) return;
    setBusy(file);
    setNotice(null);
    try {
      const snapshot = await updateMemoryDocument(token, file, drafts[file]);
      applyMemoryDocuments(snapshot);
      setNotice(`${memoryDocumentLabel(file)}已保存。`);
    } catch (err) {
      console.warn("Failed to save memory document", err);
      setNotice(`${memoryDocumentLabel(file)}保存失败，请稍后重试。`);
    } finally {
      setBusy(null);
    }
  };

  const clearDocument = async (file: MemoryDocumentName) => {
    if (busy) return;
    setBusy(`clear-${file}`);
    setNotice(null);
    try {
      const snapshot = await clearMemoryDocument(token, file);
      applyMemoryDocuments(snapshot);
      setNotice(`${memoryDocumentLabel(file)}已清空。`);
    } catch (err) {
      console.warn("Failed to clear memory document", err);
      setNotice(`${memoryDocumentLabel(file)}清空失败，请稍后重试。`);
    } finally {
      setBusy(null);
    }
  };

  const refreshSummary = async () => {
    if (busy || !memoryEnabled) return;
    setBusy("refresh");
    setNotice(null);
    try {
      const snapshot = await refreshMemoryDocument(token);
      applyMemoryDocuments(snapshot);
      setNotice(snapshot.changed ? "已整理最新学习摘要。" : "没有发现新的学习回顾。");
    } catch (err) {
      console.warn("Failed to refresh memory document", err);
      setNotice("学习摘要整理失败，请稍后重试。");
    } finally {
      setBusy(null);
    }
  };

  const toggleMemoryEnabled = async () => {
    if (busy) return;
    setBusy("toggle");
    setNotice(null);
    try {
      const nextEnabled = !memoryEnabled;
      const settings = await updateMemorySettings(token, { enabled: nextEnabled });
      setMemoryEnabled(settings.memory.enabled);
      setNotice(
        settings.memory.enabled
          ? "自动记忆已启用，后续对话会继续沉淀。"
          : "自动记忆已关闭，当前仅支持手动维护。",
      );
    } catch (err) {
      console.warn("Failed to update memory settings", err);
      setNotice("记忆开关更新失败，请稍后重试。");
    } finally {
      setBusy(null);
    }
  };

  const summaryDirty = payload ? drafts.summary !== payload.summary : false;
  const profileDirty = payload ? drafts.profile !== payload.profile : false;
  const automaticMemoryHint = memoryEnabled
    ? "设置 CoLearn 如何收集、保留和整合记忆。"
    : "自动记忆已关闭，当前仅支持手动维护。";

  return (
    <PanelView
      title="记忆"
      subtitle="设置 CoLearn 如何保留、整理和使用你的学习资料。"
      {...panelProps}
    >
      <div className="mx-auto flex w-full max-w-[720px] flex-col gap-8">
        {notice ? (
          <div
            role="status"
            className="rounded-lg border border-emerald-500/20 bg-emerald-500/8 px-3 py-2.5 text-[13px] text-emerald-700 dark:text-emerald-300"
          >
            {notice}
          </div>
        ) : null}

        <section className="space-y-2">
          <MemorySectionTitle>学习摘要</MemorySectionTitle>
          <MemorySectionHint>
            跨会话保留的稳定学习背景和结论。
          </MemorySectionHint>
          <MemoryDocumentEditor
            file="summary"
            value={drafts.summary}
            dirty={summaryDirty}
            busy={busy}
            disabled={loading && !payload}
            onChange={(value) => setDrafts((current) => ({ ...current, summary: value }))}
            onSave={() => void saveDocument("summary")}
          />
        </section>

        <section className="space-y-2">
          <MemorySectionTitle>个人画像</MemorySectionTitle>
          <MemorySectionHint>
            记录学习目标、偏好和已经确认的协作方式。
          </MemorySectionHint>
          <MemoryDocumentEditor
            file="profile"
            value={drafts.profile}
            dirty={profileDirty}
            busy={busy}
            disabled={loading && !payload}
            onChange={(value) => setDrafts((current) => ({ ...current, profile: value }))}
            onSave={() => void saveDocument("profile")}
          />
        </section>

        <section className="space-y-2">
          <MemorySectionTitle>记忆（实验性）</MemorySectionTitle>
          <MemorySectionHint>{automaticMemoryHint}</MemorySectionHint>
          <MemoryGroup>
            <MemorySettingRow
              title="启用记忆"
              description="从聊天中生成新记录，并将其带入新聊天。"
            >
              <MemorySwitch
                active={memoryEnabled}
                disabled={busy === "toggle"}
                onClick={() => void toggleMemoryEnabled()}
              />
            </MemorySettingRow>
            <MemorySettingRow
              title="整理摘要"
              description="从最近一次学习回顾更新学习摘要。"
            >
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => void refreshSummary()}
                disabled={!!busy || !memoryEnabled}
                className="h-8 rounded-full px-3 text-[12px] font-medium"
              >
                {busy === "refresh" ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                ) : (
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                )}
                整理
              </Button>
            </MemorySettingRow>
            <MemorySettingRow
              title="重置记忆"
              description="删除已保存的学习摘要或个人画像。"
            >
              <div className="flex flex-wrap justify-end gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => void clearDocument("summary")}
                  disabled={!!busy || !drafts.summary}
                  className="h-8 rounded-full px-3 text-[12px] font-medium text-destructive hover:text-destructive"
                >
                  {busy === "clear-summary" ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                  ) : (
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                  )}
                  摘要
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => void clearDocument("profile")}
                  disabled={!!busy || !drafts.profile}
                  className="h-8 rounded-full px-3 text-[12px] font-medium text-destructive hover:text-destructive"
                >
                  {busy === "clear-profile" ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                  ) : (
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                  )}
                  画像
                </Button>
              </div>
            </MemorySettingRow>
          </MemoryGroup>
        </section>
      </div>
    </PanelView>
  );
}
