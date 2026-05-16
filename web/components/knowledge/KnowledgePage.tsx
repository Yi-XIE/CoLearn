"use client";

import { useMemo, useState } from "react";
import {
  BookOpen,
  Brain,
  FileText,
  FolderOpen,
  Network,
  Plus,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import CreateKbModal from "@/components/knowledge/CreateKbModal";
import KnowledgeBaseDetail from "@/components/knowledge/KnowledgeBaseDetail";
import KnowledgeBaseList from "@/components/knowledge/KnowledgeBaseList";
import { useKnowledgeBases } from "@/hooks/useKnowledgeBases";
import { useAppShell } from "@/context/AppShellContext";

export default function KnowledgePage() {
  const { t } = useTranslation();
  const { activeProjectId } = useAppShell();
  const {
    kbs,
    providers,
    uploadPolicy,
    loading,
    error,
    setError,
    tasksByKb,
    historyByKb,
    clearHistory,
    createKb,
    uploadFiles,
    setDefault,
    reindex,
    deleteKb,
  } = useKnowledgeBases();

  const [selectedKbName, setSelectedKbName] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const effectiveSelectedKbName = useMemo(() => {
    if (!kbs.length) {
      return null;
    }
    if (selectedKbName && kbs.some((item) => item.name === selectedKbName)) {
      return selectedKbName;
    }
    const defaultKb = kbs.find((item) => item.is_default) ?? kbs[0];
    return defaultKb?.name ?? null;
  }, [kbs, selectedKbName]);

  const selectedKb =
    kbs.find((item) => item.name === effectiveSelectedKbName) ?? null;

  const lightragEnabled = useMemo(
    () => providers.some((provider) => provider.id.toLowerCase().includes("llama") || provider.id.toLowerCase().includes("light")),
    [providers],
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--background)]">
      <div className="border-b border-[var(--border)] bg-[var(--background)] px-6 py-6">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-2 text-sm text-[var(--muted-foreground)]">
                {t("Knowledge workspace")}
              </div>
              <h1 className="text-3xl font-semibold tracking-normal text-[var(--foreground)]">
                {t("Local files + LLM wiki + LightRAG")}
              </h1>
              <p className="mt-3 text-sm leading-6 text-[var(--muted-foreground)]">
                {t(
                  "This page is now assembled as CoLearn's local knowledge workspace: bring in your files, keep them as source libraries, and let LightRAG turn them into retrieval context for learning turns.",
                )}
              </p>
            </div>

            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--foreground)] px-4 py-2.5 text-sm font-medium text-[var(--background)] transition-opacity hover:opacity-90"
            >
              <Plus size={16} />
              {t("New source library")}
            </button>
          </div>

          <div className="grid gap-4 lg:grid-cols-4">
            <AssemblyCard
              icon={<FolderOpen size={18} />}
              title={t("Local file ingestion")}
              body={t(
                "Upload PDFs, docs, notes, and code files from this machine into source libraries.",
              )}
            />
            <AssemblyCard
              icon={<BookOpen size={18} />}
              title={t("LLM wiki shell")}
              body={t(
                "Treat each source library like a local wiki surface for your learning materials, not a generic enterprise KB.",
              )}
            />
            <AssemblyCard
              icon={<Network size={18} />}
              title={t("LightRAG retrieval")}
              body={
                lightragEnabled
                  ? t(
                      "LightRAG is available as the retrieval layer behind these sources and will feed learning-turn context.",
                    )
                  : t(
                      "LightRAG is still configurable from Settings; source libraries are ready for that retrieval layer to use.",
                    )
              }
            />
            <AssemblyCard
              icon={<Brain size={18} />}
              title={t("Current learning project")}
              body={
                activeProjectId
                  ? t("Active project id: {{projectId}}", {
                      projectId: activeProjectId,
                    })
                  : t("No active learning project is selected yet.")
              }
            />
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {error && (
          <div className="border-b border-rose-200 bg-rose-50 px-6 py-3 text-sm text-rose-700">
            <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => setError(null)}
                className="rounded-md border border-rose-200 px-2 py-1 text-xs font-medium transition-colors hover:bg-rose-100"
              >
                {t("Dismiss")}
              </button>
            </div>
          </div>
        )}

        <div className="mx-auto flex h-full max-w-7xl min-h-0">
          <KnowledgeBaseList
            kbs={kbs}
            selectedKbName={effectiveSelectedKbName}
            onSelect={setSelectedKbName}
            onCreate={() => setCreateOpen(true)}
            onSetDefault={(name) => void setDefault(name)}
            onDelete={(name) => void deleteKb(name)}
            tasksByKb={tasksByKb}
          />

          <div className="min-h-0 flex-1">
            <KnowledgeBaseDetail
              kb={selectedKb}
              uploadPolicy={uploadPolicy}
              task={
                effectiveSelectedKbName
                  ? tasksByKb[effectiveSelectedKbName]
                  : undefined
              }
              history={
                effectiveSelectedKbName
                  ? historyByKb[effectiveSelectedKbName] || []
                  : []
              }
              onCreate={() => setCreateOpen(true)}
              onUpload={async (kbName, files) => {
                await uploadFiles(kbName, files);
              }}
              onReindex={async (kbName) => {
                await reindex(kbName);
              }}
              onSetDefault={async (kbName) => {
                await setDefault(kbName);
              }}
              onDelete={async (kbName) => {
                await deleteKb(kbName);
              }}
              onClearHistory={(kbName) => clearHistory(kbName)}
            />
          </div>
        </div>
      </div>

      <CreateKbModal
        isOpen={createOpen}
        providers={providers}
        uploadPolicy={uploadPolicy}
        onClose={() => setCreateOpen(false)}
        onCreate={async ({ name, provider, files }) => {
          await createKb({ name, provider, files });
          setCreateOpen(false);
          setSelectedKbName(name);
        }}
      />
    </div>
  );
}

function AssemblyCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border)]/70 bg-[var(--secondary)]/35 p-4">
      <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--background)] text-[var(--foreground)] shadow-sm">
        {icon}
      </div>
      <div className="text-sm font-medium text-[var(--foreground)]">{title}</div>
      <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
        {body}
      </p>
    </div>
  );
}
