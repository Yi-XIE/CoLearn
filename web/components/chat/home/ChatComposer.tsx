"use client";

import Image from "next/image";
import {
  ArrowUp,
  ChevronDown,
  FolderOpen,
  Layers,
  Plus,
  Square,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  memo,
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import { useTranslation } from "react-i18next";
import {
  ATTACHMENT_ACCEPT,
  docIconFor,
  formatBytes,
  isSvgFilename,
} from "@/lib/doc-attachments";
import type { LLMSelection } from "@/lib/unified-ws";
import type { LLMOption } from "@/lib/llm-options";
import ChatProjectMenu from "@/components/chat/project/ChatProjectMenu";
import type {
  LearningProjectRef,
  MemoryReferenceFile,
} from "@/lib/learning-context";
import ModelSelector from "./ModelSelector";
import { ProjectContextChips } from "./ChatMessages";
import { ComposerInput, type ComposerInputHandle } from "./ComposerInput";

interface PendingAttachment {
  type: string;
  filename: string;
  base64?: string;
  previewUrl?: string;
  size?: number;
  mimeType?: string;
}

type ToolName =
  | "brainstorm"
  | "rag"
  | "web_search"
  | "code_execution"
  | "reason"
  | "paper_search";

interface ToolDef {
  name: ToolName;
  label: string;
  icon: LucideIcon;
}

type ProjectSelectionCounts = {
  memory: number;
};

export default memo(function ChatComposer({
  composerRef,
  toolMenuRef,
  toolBtnRef,
  projectMenuRef,
  projectBtnRef,
  dragCounter,
  dragging,
  toolMenuOpen,
  projectMenuOpen,
  hasMessages,
  attachments,
  attachmentError,
  visibleTools,
  selectedTools,
  llmOptions,
  activeLLMDefault,
  llmSelection,
  llmOptionsLoading,
  llmOptionsError,
  currentProject,
  selectedMemoryFiles,
  isStreaming,
  onSetToolMenuOpen,
  onSetProjectMenuOpen,
  onSelectLLM,
  onSelectMemoryPicker,
  onToggleTool,
  onToggleMemoryFile,
  onSend,
  onRemoveAttachment,
  onPreviewAttachment,
  onDragEnter,
  onDragLeave,
  onDragOver,
  onDrop,
  onPaste,
  onAddFiles,
  onCancelStreaming,
}: {
  composerRef: RefObject<HTMLDivElement | null>;
  toolMenuRef: RefObject<HTMLDivElement | null>;
  toolBtnRef: RefObject<HTMLButtonElement | null>;
  projectMenuRef: RefObject<HTMLDivElement | null>;
  projectBtnRef: RefObject<HTMLButtonElement | null>;
  dragCounter: RefObject<number>;
  dragging: boolean;
  toolMenuOpen: boolean;
  projectMenuOpen: boolean;
  hasMessages: boolean;
  attachments: PendingAttachment[];
  attachmentError: string | null;
  visibleTools: ToolDef[];
  selectedTools: Set<string>;
  llmOptions: LLMOption[];
  activeLLMDefault: LLMSelection | null;
  llmSelection: LLMSelection | null;
  llmOptionsLoading: boolean;
  llmOptionsError: boolean;
  currentProject: LearningProjectRef;
  selectedMemoryFiles: MemoryReferenceFile[];
  isStreaming: boolean;
  onSetToolMenuOpen: (open: boolean | ((prev: boolean) => boolean)) => void;
  onSetProjectMenuOpen: (open: boolean | ((prev: boolean) => boolean)) => void;
  onSelectLLM: (selection: LLMSelection | null) => void;
  onSelectMemoryPicker: () => void;
  onToggleTool: (tool: ToolName) => void;
  onToggleMemoryFile: (file: MemoryReferenceFile) => void;
  onSend: (content: string) => void;
  onRemoveAttachment: (index: number) => void;
  onPreviewAttachment?: (index: number) => void;
  onDragEnter: (event: React.DragEvent) => void;
  onDragLeave: (event: React.DragEvent) => void;
  onDragOver: (event: React.DragEvent) => void;
  onDrop: (event: React.DragEvent) => void;
  onPaste: (event: React.ClipboardEvent) => void;
  onAddFiles: (files: File[]) => void;
  onCancelStreaming: () => void;
}) {
  const { t } = useTranslation();
  const [hasContent, setHasContent] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputHandleRef = useRef<ComposerInputHandle>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!hasMessages) textareaRef.current?.focus();
  }, [hasMessages]);

  const handlePickFiles = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const picked = Array.from(event.target.files ?? []);
      if (picked.length) onAddFiles(picked);
      event.target.value = "";
    },
    [onAddFiles],
  );

  const handleInputChange = useCallback((value: string) => {
    const next = !!value.trim();
    setHasContent((prev) => (prev === next ? prev : next));
  }, []);

  const doSend = useCallback(
    (content: string) => {
      onSend(content);
      setHasContent(false);
      inputHandleRef.current?.clear();
    },
    [onSend],
  );

  const hasReferences = attachments.length > 0 || selectedMemoryFiles.length > 0;
  const canSend = (hasContent || hasReferences) && !isStreaming;

  const projectSelectionCounts: ProjectSelectionCounts = {
    memory: selectedMemoryFiles.length,
  };
  const projectSelectionCount = projectSelectionCounts.memory;

  const handleManualSend = useCallback(() => {
    if (!canSend) return;
    const content = inputHandleRef.current?.getValue() || "";
    doSend(content);
  }, [canSend, doSend]);

  return (
    <div
      ref={composerRef}
      className={`relative z-20 mx-auto w-full shrink-0 pb-5 ${hasMessages ? "pt-1" : ""}`}
    >
      {hasMessages && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-transparent to-[var(--background)]/72" />
      )}

      <div className="relative">
        <div
          className={`relative rounded-2xl border bg-[var(--card)] shadow-[0_1px_8px_rgba(0,0,0,0.03)] transition-colors ${
            dragging
              ? "border-[var(--primary)] bg-[var(--primary)]/[0.03]"
              : "border-[var(--border)]"
          }`}
          onDragEnter={onDragEnter}
          onDragLeave={onDragLeave}
          onDragOver={onDragOver}
          onDrop={onDrop}
          data-drag-counter={dragCounter.current}
        >
          {dragging && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-2xl border-2 border-dashed border-[var(--primary)]/50 bg-[var(--primary)]/[0.04]">
              <div className="flex flex-col items-center gap-1 text-[var(--primary)]">
                <Plus size={22} strokeWidth={1.6} />
                <span className="text-[13px] font-medium">
                  {t("Drop files here")}
                </span>
                <span className="text-[11px] text-[var(--primary)]/70">
                  {t("Images, Office docs, code & text")}
                </span>
              </div>
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ATTACHMENT_ACCEPT}
            onChange={handleFileInputChange}
            className="hidden"
            aria-hidden="true"
            tabIndex={-1}
          />

          {hasReferences && (
            <div className="px-4 pt-3.5 [&>div]:mb-0">
              <ProjectContextChips
                currentProject={currentProject}
                memoryFiles={selectedMemoryFiles}
                onRemoveMemoryFile={onToggleMemoryFile}
              />
            </div>
          )}

          <ComposerInput
            ref={inputHandleRef}
            textareaRef={textareaRef}
            canSendEmpty={hasReferences}
            onSend={doSend}
            onInputChange={handleInputChange}
            onPaste={onPaste}
            selectedCounts={projectSelectionCounts}
            onSelectMemoryPicker={onSelectMemoryPicker}
          />

          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 px-4 pb-2">
              {attachments.map((attachment, index) => {
                const previewLabel = t("Preview");
                const removeLabel = t("Remove attachment");

                if (attachment.type === "image" && attachment.previewUrl) {
                  return (
                    <div
                      key={`${attachment.filename}-${index}`}
                      className="group relative"
                    >
                      <button
                        type="button"
                        onClick={() => onPreviewAttachment?.(index)}
                        title={attachment.filename || previewLabel}
                        aria-label={previewLabel}
                        className="relative block h-16 w-16 overflow-hidden rounded-lg border border-[var(--border)] transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)]/40"
                      >
                        <Image
                          src={attachment.previewUrl}
                          alt={attachment.filename || t("Attachment preview")}
                          fill
                          unoptimized
                          className="object-cover"
                        />
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          onRemoveAttachment(index);
                        }}
                        aria-label={removeLabel}
                        className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--foreground)] text-[var(--background)] opacity-0 shadow-sm transition-opacity group-hover:opacity-100"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  );
                }

                if (isSvgFilename(attachment.filename) && attachment.previewUrl) {
                  return (
                    <div
                      key={`${attachment.filename}-${index}`}
                      className="group relative"
                      title={attachment.filename}
                    >
                      <button
                        type="button"
                        onClick={() => onPreviewAttachment?.(index)}
                        aria-label={previewLabel}
                        className="relative block h-16 w-16 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--card)] transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)]/40"
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={attachment.previewUrl}
                          alt={attachment.filename || t("Attachment preview")}
                          className="h-full w-full object-contain p-1"
                        />
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          onRemoveAttachment(index);
                        }}
                        aria-label={removeLabel}
                        className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--foreground)] text-[var(--background)] opacity-0 shadow-sm transition-opacity group-hover:opacity-100"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  );
                }

                const spec = docIconFor(attachment.filename);
                const Icon = spec.Icon;
                const sizeLabel = attachment.size
                  ? formatBytes(attachment.size)
                  : "";

                return (
                  <div
                    key={`${attachment.filename}-${index}`}
                    className="group relative"
                    title={attachment.filename}
                  >
                    <button
                      type="button"
                      onClick={() => onPreviewAttachment?.(index)}
                      aria-label={previewLabel}
                      className="flex h-16 w-[160px] items-center gap-2.5 rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 text-left transition-colors hover:border-[var(--primary)]/40 hover:bg-[var(--muted)]/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)]/40"
                    >
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-[var(--muted)]/60">
                        <Icon
                          size={22}
                          strokeWidth={1.5}
                          className={spec.tint}
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[12px] font-medium text-[var(--foreground)]">
                          {attachment.filename}
                        </div>
                        <div className="truncate text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                          {sizeLabel ? `${spec.label} 路 ${sizeLabel}` : spec.label}
                        </div>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onRemoveAttachment(index);
                      }}
                      aria-label={removeLabel}
                      className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--foreground)] text-[var(--background)] opacity-0 shadow-sm transition-opacity group-hover:opacity-100"
                    >
                      <X size={10} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {attachmentError && (
            <div className="px-4 pb-2 text-[11px] text-red-600">
              {attachmentError}
            </div>
          )}

          <div className="border-t border-[var(--border)]/35 px-3 py-2">
            <div className="flex items-center gap-2">
              <div className="flex min-w-0 flex-1 items-center gap-1">
                <button
                  type="button"
                  onClick={handlePickFiles}
                  title={t("Attach files")}
                  aria-label={t("Attach files")}
                  className="inline-flex shrink-0 items-center gap-1 px-1.5 py-1 text-[11px] font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
                >
                  <Plus size={12} strokeWidth={1.9} />
                  {t("Attach")}
                </button>

                {visibleTools.length > 0 && (
                  <div className="relative flex items-center gap-0.5">
                    <button
                      ref={toolBtnRef}
                      onClick={() => onSetToolMenuOpen((open) => !open)}
                      className="inline-flex shrink-0 items-center gap-1 py-1 px-1.5 text-[11px] font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
                    >
                      <Layers size={12} strokeWidth={1.7} />
                      {t("Tools")}
                      <ChevronDown
                        size={10}
                        className={`transition-transform ${toolMenuOpen ? "rotate-180" : ""}`}
                      />
                    </button>
                    {selectedTools.size > 0 && (
                      <div className="flex items-center gap-[3px] overflow-hidden">
                        {visibleTools
                          .filter((tool) => selectedTools.has(tool.name))
                          .map((tool, index) => (
                            <span
                              key={tool.name}
                              className="shrink-0 text-[10px] text-[var(--muted-foreground)]/35"
                            >
                              {index > 0 && (
                                <span className="text-[12px] leading-none">
                                  路
                                </span>
                              )}
                              {t(tool.label)}
                            </span>
                          ))}
                      </div>
                    )}
                    {toolMenuOpen && (
                      <div
                        ref={toolMenuRef}
                        className="absolute bottom-full left-0 z-50 mb-1.5 min-w-[180px] rounded-lg border border-[var(--border)] bg-[var(--popover)] py-1 shadow-lg backdrop-blur-md"
                      >
                        {visibleTools.map((tool) => {
                          const active = selectedTools.has(tool.name);
                          const Icon = tool.icon;
                          return (
                            <button
                              key={tool.name}
                              onClick={() => onToggleTool(tool.name)}
                              className={`flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[12px] transition-colors ${
                                active
                                  ? "text-[var(--primary)]"
                                  : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                              } hover:bg-[var(--muted)]/40`}
                            >
                              <Icon size={13} strokeWidth={1.7} />
                              <span className="flex-1 font-medium">
                                {t(tool.label)}
                              </span>
                              {active && (
                                <div className="h-1.5 w-1.5 rounded-full bg-[var(--primary)]" />
                              )}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                <div className="relative flex items-center gap-0.5">
                  <button
                    ref={projectBtnRef}
                    type="button"
                    onClick={() => onSetProjectMenuOpen((open) => !open)}
                    className="inline-flex shrink-0 items-center gap-1 py-1 px-1.5 text-[11px] font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
                  >
                    <FolderOpen size={12} strokeWidth={1.7} />
                    {t("Project")}
                    <ChevronDown
                      size={10}
                      className={`transition-transform ${projectMenuOpen ? "rotate-180" : ""}`}
                    />
                  </button>
                  {projectSelectionCount > 0 && (
                    <span className="shrink-0 rounded-full bg-[var(--primary)]/10 px-1.5 py-px text-[9px] font-semibold text-[var(--primary)]">
                      {projectSelectionCount}
                    </span>
                  )}
                  {projectMenuOpen && (
                    <div
                      ref={projectMenuRef}
                      className="absolute bottom-full left-0 z-50 mb-1.5"
                    >
                      <ChatProjectMenu
                        variant="toolbar"
                        selectedCounts={projectSelectionCounts}
                        onSelectItem={(key) => {
                          onSetProjectMenuOpen(false);
                          if (key === "memory") onSelectMemoryPicker();
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>

              <div className="ml-auto flex shrink-0 items-center gap-1.5">
                <ModelSelector
                  options={llmOptions}
                  activeDefault={activeLLMDefault}
                  value={llmSelection}
                  loading={llmOptionsLoading}
                  error={llmOptionsError}
                  onChange={onSelectLLM}
                />

                {isStreaming ? (
                  <button
                    type="button"
                    onClick={onCancelStreaming}
                    className="group relative inline-flex h-[29px] w-[29px] shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-white shadow-[0_4px_12px_rgba(195,90,44,0.18)] transition-[background-color,box-shadow] hover:bg-[var(--primary)]/90 hover:shadow-[0_6px_16px_rgba(195,90,44,0.28)]"
                    aria-label={t("Stop generating")}
                    title={t("Stop generating")}
                  >
                    <span className="pointer-events-none absolute inset-0 rounded-full border-[1.5px] border-white/30 border-t-white/85 animate-spin opacity-90 transition-opacity group-hover:opacity-40" />
                    <Square
                      size={9}
                      strokeWidth={2.6}
                      className="relative z-10 fill-current"
                    />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleManualSend}
                    disabled={!canSend}
                    className="rounded-full bg-[var(--primary)] p-[7px] text-white shadow-[0_4px_12px_rgba(195,90,44,0.15)] transition-[transform,opacity,box-shadow] hover:shadow-[0_6px_16px_rgba(195,90,44,0.22)] disabled:opacity-25 disabled:shadow-none"
                    aria-label={t("Send")}
                  >
                    <ArrowUp size={15} strokeWidth={2.5} />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});
