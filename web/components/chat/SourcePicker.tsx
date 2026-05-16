"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, FileText, Globe, Loader2, Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { docIconFor, formatBytes } from "@/lib/doc-attachments";
import {
  listKnowledgeBaseFiles,
  listKnowledgeBases,
  type KnowledgeBaseFile,
  type KnowledgeBaseSummary,
} from "@/lib/knowledge-api";
import type { LearningProjectRef } from "@/lib/learning-context";
import type { SelectedSourceRef } from "@/lib/source-references";

interface SourcePickerProps {
  open: boolean;
  project: LearningProjectRef;
  preferredKbName?: string;
  initialReferences: SelectedSourceRef[];
  pendingAttachments?: Array<{
    filename: string;
    mimeType?: string;
    size?: number;
  }>;
  onClose: () => void;
  onApply: (references: SelectedSourceRef[]) => void | Promise<void>;
}

function kbRef(kb: KnowledgeBaseSummary): string {
  return kb.id?.trim() || kb.name.trim();
}

function sourceIdFor(kb: KnowledgeBaseSummary, fileName: string): string {
  return `${kbRef(kb)}:${fileName}`;
}

export default function SourcePicker({
  open,
  project,
  preferredKbName,
  initialReferences,
  pendingAttachments = [],
  onClose,
  onApply,
}: SourcePickerProps) {
  const { t } = useTranslation();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseSummary[]>(
    [],
  );
  const [activeKbRef, setActiveKbRef] = useState("");
  const [files, setFiles] = useState<KnowledgeBaseFile[]>([]);
  const [selected, setSelected] = useState<SelectedSourceRef[]>([]);
  const [query, setQuery] = useState("");
  const [webUrl, setWebUrl] = useState("");
  const [webNote, setWebNote] = useState("");
  const [loadingKbs, setLoadingKbs] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    if (!open) return;
    let mounted = true;
    void (async () => {
      setSelected(initialReferences);
      setLoadingKbs(true);
      try {
        const items = await listKnowledgeBases({ force: true });
        if (!mounted) return;
        setKnowledgeBases(items);
        const preferred =
          items.find((item) => item.name === preferredKbName) ??
          items.find((item) => item.is_default) ??
          items[0];
        setActiveKbRef(preferred ? kbRef(preferred) : "");
      } catch {
        if (!mounted) return;
        setKnowledgeBases([]);
        setActiveKbRef("");
        setWebUrl("");
        setWebNote("");
      } finally {
        if (mounted) setLoadingKbs(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [initialReferences, open, preferredKbName]);

  const activeKb =
    knowledgeBases.find((item) => kbRef(item) === activeKbRef) ?? null;

  useEffect(() => {
    let mounted = true;
    void (async () => {
      if (!open || !activeKb) {
        setFiles([]);
        return;
      }
      setLoadingFiles(true);
      try {
        const items = await listKnowledgeBaseFiles(activeKb.name, {
          force: true,
        });
        if (mounted) setFiles(items);
      } catch {
        if (mounted) setFiles([]);
      } finally {
        if (mounted) setLoadingFiles(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [activeKb, open]);

  const filteredFiles = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return files;
    return files.filter((file) => file.name.toLowerCase().includes(keyword));
  }, [files, query]);

  const selectedIds = useMemo(
    () => new Set(selected.map((item) => item.sourceId)),
    [selected],
  );

  const webSourceId = useMemo(() => {
    const trimmedUrl = webUrl.trim();
    return trimmedUrl ? `web:${trimmedUrl}` : "";
  }, [webUrl]);

  const pendingAttachmentRefs = useMemo(
    () =>
      pendingAttachments.map((item) => ({
        sourceId: `attachment:${item.filename}`,
        sourceType: "attachment_file" as const,
        title: item.filename,
        fileName: item.filename,
        mimeType: item.mimeType,
        size: item.size,
      })),
    [pendingAttachments],
  );

  const toggleFile = (file: KnowledgeBaseFile) => {
    if (!activeKb) return;
    const sourceId = sourceIdFor(activeKb, file.name);
    setSelected((prev) =>
      prev.some((item) => item.sourceId === sourceId)
        ? prev.filter((item) => item.sourceId !== sourceId)
        : [
            ...prev,
            {
              sourceId,
              sourceType: "knowledge_file",
              title: file.name,
              kbId: kbRef(activeKb),
              kbName: activeKb.name,
              fileName: file.name,
              mimeType: file.mime_type,
              size: file.size,
              modified: file.modified,
            },
          ],
    );
  };

  const handleApply = async () => {
    setApplying(true);
    try {
      const refs = [...selected];
      const trimmedUrl = webUrl.trim();
      const trimmedNote = webNote.trim();
      if (trimmedUrl || trimmedNote) {
        refs.push({
          sourceId: webSourceId || `web-note:${trimmedNote.slice(0, 24)}`,
          sourceType: "web_note",
          title: trimmedUrl || t("Web note"),
          url: trimmedUrl || undefined,
          textPreview: trimmedNote || undefined,
        });
      }
      await onApply(refs);
      onClose();
    } finally {
      setApplying(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[85] flex items-center justify-center bg-[var(--background)]/65 p-4 backdrop-blur-md">
      <div className="surface-card flex h-[76vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)] text-[var(--card-foreground)] shadow-[0_22px_70px_rgba(0,0,0,0.18)]">
        <div className="flex items-start justify-between gap-3 border-b border-[var(--border)] px-5 py-4">
          <div className="min-w-0">
            <div className="mb-1 inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--primary)]">
              <FileText className="h-3 w-3" />
              {t("Project Knowledge Garden")}
            </div>
            <h2 className="text-lg font-semibold text-[var(--foreground)]">
              {t("Select Knowledge Garden Files")}
            </h2>
            <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
              {t("Attach knowledge garden files from the current CoLearn project to this turn.")}
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={applying}
            className="rounded-lg p-2 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
            aria-label={t("Close")}
          >
            <X size={18} />
          </button>
        </div>

        <div className="border-b border-[var(--border)] bg-[var(--background)]/40 px-5 py-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-[12px] text-[var(--muted-foreground)]">
              {t("Project")} ·{" "}
              <span className="font-medium text-[var(--foreground)]">
                {t(project.title)}
              </span>
            </div>
            <div className="min-w-[220px] flex-1">
              <select
                value={activeKbRef}
                onChange={(event) => setActiveKbRef(event.target.value)}
                disabled={loadingKbs || knowledgeBases.length === 0}
                className="h-[38px] w-full rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 text-[13px] outline-none transition focus:border-[var(--primary)]/50 focus:ring-2 focus:ring-[var(--primary)]/15 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {knowledgeBases.length === 0 ? (
                  <option value="">{t("No knowledge sources available")}</option>
                ) : (
                  knowledgeBases.map((kb) => (
                    <option key={kbRef(kb)} value={kbRef(kb)}>
                      {kb.name}
                    </option>
                  ))
                )}
              </select>
            </div>
            <div className="text-[12px] text-[var(--muted-foreground)]">
              {selected.length === 1
                ? t("1 source selected")
                : t("{{n}} sources selected", { n: selected.length })}
            </div>
          </div>
        </div>

        <div className="flex min-h-0 flex-1 flex-col p-5">
          {pendingAttachmentRefs.length ? (
            <div className="mb-4 rounded-2xl border border-[var(--border)] bg-[var(--background)]/50 p-4">
              <div className="mb-2 inline-flex items-center gap-2 text-[12px] font-medium text-[var(--foreground)]">
                <FileText className="h-4 w-4" />
                {t("Add current attachments")}
              </div>
              <div className="space-y-2">
                {pendingAttachmentRefs.map((attachment) => {
                  const active = selectedIds.has(attachment.sourceId);
                  const spec = docIconFor(attachment.fileName || attachment.title);
                  const Icon = spec.Icon;
                  return (
                    <button
                      key={attachment.sourceId}
                      type="button"
                      onClick={() =>
                        setSelected((prev) =>
                          prev.some((item) => item.sourceId === attachment.sourceId)
                            ? prev.filter((item) => item.sourceId !== attachment.sourceId)
                            : [...prev, attachment],
                        )
                      }
                      className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors ${
                        active
                          ? "border-[var(--primary)] bg-[var(--primary)]/8"
                          : "border-[var(--border)] hover:bg-[var(--muted)]/40"
                      }`}
                    >
                      <div
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
                          active
                            ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)]"
                            : "border-[var(--border)] text-transparent"
                        }`}
                      >
                        <Check size={12} />
                      </div>
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[var(--muted)]/60">
                        <Icon size={16} strokeWidth={1.5} className={spec.tint} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] font-medium text-[var(--foreground)]">
                          {attachment.title}
                        </div>
                        {attachment.size ? (
                          <div className="text-[11px] text-[var(--muted-foreground)]">
                            {formatBytes(attachment.size)}
                          </div>
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          <div className="mb-4 rounded-2xl border border-[var(--border)] bg-[var(--background)]/50 p-4">
            <div className="mb-2 inline-flex items-center gap-2 text-[12px] font-medium text-[var(--foreground)]">
              <Globe className="h-4 w-4" />
              {t("Add web excerpt")}
            </div>
            <div className="grid gap-3 md:grid-cols-[1.2fr_1.8fr]">
              <input
                value={webUrl}
                onChange={(event) => setWebUrl(event.target.value)}
                placeholder={t("Paste a source URL")}
                className="rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2.5 text-[13px] outline-none transition focus:border-[var(--primary)]/50 focus:ring-2 focus:ring-[var(--primary)]/15"
              />
              <textarea
                value={webNote}
                onChange={(event) => setWebNote(event.target.value)}
                placeholder={t("Add a short excerpt or note from the page")}
                className="min-h-[84px] rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2.5 text-[13px] outline-none transition focus:border-[var(--primary)]/50 focus:ring-2 focus:ring-[var(--primary)]/15"
              />
            </div>
          </div>

          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("Search source files")}
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--card)] py-2.5 pl-9 pr-3 text-[13px] outline-none transition focus:border-[var(--primary)]/50 focus:ring-2 focus:ring-[var(--primary)]/15"
            />
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-[var(--border)] bg-[var(--card)]">
            {loadingFiles ? (
              <div className="flex h-full min-h-[220px] items-center justify-center">
                <Loader2 className="h-5 w-5 animate-spin text-[var(--muted-foreground)]" />
              </div>
            ) : filteredFiles.length === 0 ? (
              <div className="flex h-full min-h-[220px] items-center justify-center px-6 text-center text-[13px] text-[var(--muted-foreground)]">
                {activeKb
                  ? t("No source files found in this source library.")
                  : t("Choose a source library to browse source files.")}
              </div>
            ) : (
              <div className="divide-y divide-[var(--border)]">
                {filteredFiles.map((file) => {
                  const sourceId = activeKb ? sourceIdFor(activeKb, file.name) : "";
                  const active = selectedIds.has(sourceId);
                  const spec = docIconFor(file.name);
                  const Icon = spec.Icon;
                  return (
                    <button
                      key={file.name}
                      type="button"
                      onClick={() => toggleFile(file)}
                      className={`flex w-full items-center gap-3 px-4 py-3 text-left transition-colors ${
                        active
                          ? "bg-[var(--primary)]/8"
                          : "hover:bg-[var(--muted)]/40"
                      }`}
                    >
                      <div
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
                          active
                            ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)]"
                            : "border-[var(--border)] text-transparent"
                        }`}
                      >
                        <Check size={12} />
                      </div>
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[var(--muted)]/60">
                        <Icon size={18} strokeWidth={1.5} className={spec.tint} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] font-medium text-[var(--foreground)]">
                          {file.name}
                        </div>
                        <div className="truncate text-[11px] text-[var(--muted-foreground)]">
                          {formatBytes(file.size)}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="text-[12px] text-[var(--muted-foreground)]">
              {activeKb
                ? t("Selected files will be added as learning sources for the next response.")
                : t("No source library selected.")}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSelected([])}
                disabled={applying}
                className="rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2.5 text-[12px] font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
              >
                {t("Clear")}
              </button>
              <button
                onClick={handleApply}
                disabled={(!selected.length && !webUrl.trim() && !webNote.trim()) || applying}
                className="btn-primary rounded-xl bg-[var(--primary)] px-4 py-2.5 text-[13px] font-medium text-[var(--primary-foreground)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {applying
                  ? t("Saving...")
                  : t("Use Selected Sources ({{n}})", {
                      n:
                        selected.length +
                        (webUrl.trim() || webNote.trim() ? 1 : 0),
                    })}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
