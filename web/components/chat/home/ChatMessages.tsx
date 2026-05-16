"use client";

import { memo, useMemo, type ReactNode } from "react";
import {
  Brain,
  Copy,
  FileText,
  FolderOpen,
  Loader2,
  RefreshCcw,
  X,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import AssistantResponse from "@/components/common/AssistantResponse";
import type {
  MessageAttachment,
  MessageRequestSnapshot,
} from "@/context/UnifiedChatContext";
import { apiUrl } from "@/lib/api";
import { docIconFor } from "@/lib/doc-attachments";
import type { StreamEvent } from "@/lib/unified-ws";
import { hasVisibleMarkdownContent } from "@/lib/markdown-display";
import { parseModelThinkingSegments } from "@/lib/think-segments";
import type {
  LearningProjectRef,
  MemoryReferenceFile,
} from "@/lib/learning-context";

interface ChatMessageItem {
  role: "user" | "assistant" | "system";
  content: string;
  events?: StreamEvent[];
  attachments?: MessageAttachment[];
  requestSnapshot?: MessageRequestSnapshot;
}

function memoryLabel(
  file: MemoryReferenceFile,
  t: (key: string) => string,
): string {
  if (file === "summary") return t("Summary");
  if (file === "profile") return t("Profile");
  if (file === "mastery") return t("Mastery");
  return t("Event Store");
}

function imageSrcForAttachment(attachment: MessageAttachment): string | null {
  if (attachment.url) {
    if (
      attachment.url.startsWith("http") ||
      attachment.url.startsWith("blob:") ||
      attachment.url.startsWith("data:")
    ) {
      return attachment.url;
    }
    return apiUrl(attachment.url);
  }

  const base64 = attachment.base64?.trim();
  if (!base64) return null;
  if (base64.startsWith("data:")) return base64;
  return `data:${attachment.mime_type || "image/png"};base64,${base64}`;
}

const AssistantMessage = memo(function AssistantMessage({
  msg,
  isStreaming,
}: {
  msg: { content: string; events?: StreamEvent[] };
  isStreaming?: boolean;
}) {
  const hasVisibleContent = useMemo(
    () =>
      parseModelThinkingSegments(msg.content).some((segment) => {
        if (segment.kind === "think") return false;
        return hasVisibleMarkdownContent(segment.content);
      }),
    [msg.content],
  );
  const showStreamingPlaceholder = Boolean(isStreaming) && !hasVisibleContent;
  const { t } = useTranslation();

  return (
    <>
      {showStreamingPlaceholder ? (
        <div className="mb-3 mt-1 flex items-center gap-2 text-[12px] text-[var(--muted-foreground)]">
          <Loader2 size={13} className="animate-spin" />
          <span>{t("Thinking...")}</span>
        </div>
      ) : null}
      <AssistantResponse content={msg.content} />
    </>
  );
});

AssistantMessage.displayName = "AssistantMessage";

function RoughActionButton({
  icon: Icon,
  label,
  onClick,
  disabled,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1 px-0.5 py-0.5 text-[11px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] disabled:cursor-not-allowed disabled:opacity-35"
    >
      <Icon size={11} strokeWidth={1.5} />
      <span>{label}</span>
    </button>
  );
}

function UsageFooter({
  tokens,
}: {
  tokens: number;
}) {
  const { t } = useTranslation();

  const formatTokens = (value: number) => {
    if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
    return String(value);
  };

  return (
    <div className="flex items-center gap-2 text-[10px] text-[var(--muted-foreground)]/40">
      <span>{formatTokens(tokens)}</span>
      <span>{t("tokens")}</span>
    </div>
  );
}

function renderRequestChips(
  snap: MessageRequestSnapshot | undefined,
  t: (key: string) => string,
): ReactNode {
  const hasSources = Boolean(snap?.sourceReferences?.length);
  const hasMemory = Boolean(snap?.memoryReferences?.length);

  if (!hasSources && !hasMemory) return null;

  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {snap?.sourceReferences?.map((ref) => (
        <span
          key={ref.source_id}
          className="inline-flex items-center gap-1.5 rounded-md border border-cyan-200 bg-cyan-50 px-2 py-1 text-[11px] font-medium text-cyan-800 dark:border-cyan-900/60 dark:bg-cyan-950/30 dark:text-cyan-200"
        >
          <FileText size={11} strokeWidth={1.8} />
          {t("Source")}{" "}
          <span className="max-w-[16rem] truncate">
            {ref.title || ref.file_name}
          </span>
        </span>
      ))}
      {snap?.memoryReferences?.map((file) => (
        <span
          key={file}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--background)]/60 px-2 py-1 text-[11px] font-medium text-[var(--muted-foreground)]"
        >
          <Brain size={11} strokeWidth={1.8} />
          {t("Memory")} | {memoryLabel(file, t)}
        </span>
      ))}
    </div>
  );
}

const UserMessage = memo(function UserMessage({
  msg,
  index,
  onPreviewAttachment,
}: {
  msg: ChatMessageItem;
  index: number;
  onPreviewAttachment?: (attachment: MessageAttachment) => void;
}) {
  const { t } = useTranslation();

  return (
    <div key={`${msg.role}-${index}`} className="flex justify-end">
      <div className="max-w-[75%] space-y-1.5">
        {msg.attachments?.some((attachment) => attachment.type === "image") ? (
          <div className="flex flex-wrap justify-end gap-2">
            {msg.attachments
              .filter((attachment) => attachment.type === "image")
              .map((attachment, attachmentIndex) => {
                const src = imageSrcForAttachment(attachment);
                if (!src) return null;
                return (
                  <button
                    key={`img-${attachmentIndex}`}
                    type="button"
                    onClick={() => onPreviewAttachment?.(attachment)}
                    title={attachment.filename || t("image")}
                    className="overflow-hidden rounded-2xl border border-[var(--border)] transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)]/40"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={src}
                      alt={attachment.filename || t("image")}
                      className="max-h-48 max-w-[280px] rounded-2xl object-contain"
                    />
                  </button>
                );
              })}
          </div>
        ) : null}
        {msg.attachments?.some((attachment) => attachment.type !== "image") ? (
          <div className="flex flex-wrap justify-end gap-2">
            {msg.attachments
              .filter((attachment) => attachment.type !== "image")
              .map((attachment, attachmentIndex) => {
                const filename = attachment.filename || t("Attachment");
                const spec = docIconFor(filename);
                const Icon = spec.Icon;

                return (
                  <button
                    key={`doc-${attachmentIndex}`}
                    type="button"
                    onClick={() => onPreviewAttachment?.(attachment)}
                    title={filename}
                    className="flex h-14 w-[220px] items-center gap-2.5 rounded-xl border border-[var(--border)] bg-[var(--card)] px-2.5 text-left shadow-sm transition-colors hover:border-[var(--primary)]/40 hover:bg-[var(--muted)]/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)]/40"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[var(--muted)]/60">
                      <Icon size={20} strokeWidth={1.5} className={spec.tint} />
                    </div>
                    <div className="min-w-0 flex-1 text-left">
                      <div className="truncate text-[12px] font-medium text-[var(--foreground)]">
                        {filename}
                      </div>
                      <div className="truncate text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                        {spec.label}
                      </div>
                    </div>
                  </button>
                );
              })}
          </div>
        ) : null}
        <div className="rounded-2xl bg-[var(--secondary)] px-4 py-2.5 text-[14px] leading-relaxed text-[var(--foreground)] shadow-sm">
          {renderRequestChips(msg.requestSnapshot, t)}
          <div className="whitespace-pre-wrap">{msg.content}</div>
        </div>
      </div>
    </div>
  );
});

UserMessage.displayName = "UserMessage";

export const ProjectContextChips = memo(function ProjectContextChips({
  currentProject,
  memoryFiles,
  onRemoveMemoryFile,
}: {
  currentProject: LearningProjectRef;
  memoryFiles: MemoryReferenceFile[];
  onRemoveMemoryFile: (file: MemoryReferenceFile) => void;
}) {
  const { t } = useTranslation();

  if (memoryFiles.length === 0) return null;

  return (
    <div className="mb-3 flex flex-wrap gap-2">
      <span className="inline-flex max-w-full items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-[12px] text-slate-800 shadow-sm dark:border-slate-900/60 dark:bg-slate-950/30 dark:text-slate-200">
        <FolderOpen size={12} strokeWidth={1.8} className="shrink-0" />
        <span className="shrink-0 font-medium">{t("Project")}</span>
        <span className="truncate text-slate-700/90 dark:text-slate-200/90">
          {currentProject.title}
        </span>
      </span>
      {memoryFiles.map((file) => (
        <span
          key={file}
          className="inline-flex max-w-full items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[12px] text-emerald-800 shadow-sm dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200"
        >
          <Brain size={12} strokeWidth={1.8} className="shrink-0" />
          <span className="shrink-0 font-medium">{t("Memory")}</span>
          <span className="truncate text-emerald-700/90 dark:text-emerald-200/90">
            {memoryLabel(file, t)}
          </span>
          <button
            onClick={() => onRemoveMemoryFile(file)}
            className="shrink-0 opacity-60 transition hover:opacity-100"
          >
            <X size={12} />
          </button>
        </span>
      ))}
    </div>
  );
});

ProjectContextChips.displayName = "ProjectContextChips";

export const ChatMessageList = memo(function ChatMessageList({
  messages,
  isStreaming,
  onCopyAssistantMessage,
  onRegenerateMessage,
  onPreviewAttachment,
}: {
  messages: ChatMessageItem[];
  isStreaming: boolean;
  onCopyAssistantMessage: (content: string) => void | Promise<void>;
  onRegenerateMessage: () => void;
  onPreviewAttachment?: (attachment: MessageAttachment) => void;
}) {
  const { t } = useTranslation();

  const messageRows = useMemo(() => {
    return messages
      .map((msg, index) => ({ msg, originalIndex: index }))
      .filter(({ msg }) => msg.role !== "system")
      .map(({ msg, originalIndex }) => {
        if (msg.role === "user") {
          return {
            msg,
            originalIndex,
            pairedUserMessage: null as ChatMessageItem | null,
          };
        }

        const pairedUserMessage =
          [...messages.slice(0, originalIndex)]
            .reverse()
            .find((previous) => previous.role === "user") ?? null;

        return { msg, originalIndex, pairedUserMessage };
      });
  }, [messages]);

  const lastAssistantIndex = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === "assistant") return index;
    }
    return -1;
  }, [messages]);

  return (
    <>
      {messageRows.map(({ msg, originalIndex, pairedUserMessage }) => {
        if (msg.role === "user") {
          return (
            <UserMessage
              key={`${msg.role}-${originalIndex}`}
              msg={msg}
              index={originalIndex}
              onPreviewAttachment={onPreviewAttachment}
            />
          );
        }

        const isActiveAssistant =
          isStreaming && originalIndex === messages.length - 1;
        const msgDone = !isActiveAssistant;
        const showActions = msgDone && hasVisibleMarkdownContent(msg.content);
        const isLastAssistant = originalIndex === lastAssistantIndex;
        const showRegenerate =
          showActions &&
          !isStreaming &&
          isLastAssistant &&
          Boolean(pairedUserMessage);

        const usageSummary = (() => {
          if (!msgDone) return null;
          const resultEvent = msg.events?.find((event) => event.type === "result");
          if (!resultEvent) return null;
          const meta = resultEvent.metadata?.metadata as
            | Record<string, unknown>
            | undefined;
          const summary = meta?.cost_summary as
            | {
                total_tokens?: number;
                total_calls?: number;
              }
            | undefined;
          if (!summary?.total_tokens && !summary?.total_calls) return null;
          return {
            tokens: summary?.total_tokens ?? 0,
          };
        })();

        return (
          <div key={`${msg.role}-${originalIndex}`} className="w-full">
            <AssistantMessage
              msg={msg}
              isStreaming={isActiveAssistant}
            />
            {showActions || usageSummary ? (
              <div className="mt-2 flex items-center">
                <div className="flex gap-2">
                  <RoughActionButton
                    icon={Copy}
                    label={t("Copy")}
                    onClick={() => void onCopyAssistantMessage(msg.content)}
                  />
                  {showRegenerate ? (
                    <RoughActionButton
                      icon={RefreshCcw}
                      label={t("Regenerate")}
                      onClick={() => onRegenerateMessage()}
                    />
                  ) : null}
                </div>
                {usageSummary ? (
                  <div className="ml-auto">
                    <UsageFooter
                      tokens={usageSummary.tokens}
                    />
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </>
  );
});

ChatMessageList.displayName = "ChatMessageList";
