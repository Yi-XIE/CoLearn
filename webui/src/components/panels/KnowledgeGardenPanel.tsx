import { useCallback, useEffect, useState } from "react";
import { FileText, Network, RefreshCw, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createKnowledgeBase,
  fetchKnowledgeGraph,
  listKnowledgeBases,
  listKnowledgeFiles,
  reindexKnowledgeBase,
  uploadKnowledgeFiles,
} from "@/lib/api";
import type { KnowledgeBaseSummary, KnowledgeGraphPayload } from "@/lib/types";
import { cn } from "@/lib/utils";

import { KnowledgeGraphView } from "./knowledge/KnowledgeGraphView";
import { EmptyHint, InfoCard } from "./knowledge/KnowledgePanelPrimitives";
import { PanelView, type PanelShellProps } from "./PanelView";

type KnowledgeGardenMode = "graph" | "library";

export function KnowledgeGardenPanel({
  token,
  ...panelProps
}: PanelShellProps & {
  token: string;
}) {
  const [libraries, setLibraries] = useState<KnowledgeBaseSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [createFiles, setCreateFiles] = useState<File[]>([]);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [mode, setMode] = useState<KnowledgeGardenMode>("graph");
  const [knowledgeVersion, setKnowledgeVersion] = useState(0);
  const [graphPayload, setGraphPayload] = useState<KnowledgeGraphPayload | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);

  const refreshKnowledge = useCallback(async () => {
    setLoading(true);
    try {
      const bases = await listKnowledgeBases(token);
      const withFiles = await Promise.all(
        bases.map(async (base) => ({
          ...base,
          files: await listKnowledgeFiles(token, base.id).catch(() => []),
        })),
      );
      setLibraries(withFiles);
      setSelectedId((current) =>
        current && withFiles.some((base) => base.id === current)
          ? current
          : withFiles.find((base) => (base.files?.length ?? 0) > 0 || base.source_count > 0)?.id || withFiles[0]?.id || "",
      );
      setKnowledgeVersion((current) => current + 1);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refreshKnowledge();
  }, [refreshKnowledge]);

  useEffect(() => {
    if (mode !== "graph" || !selectedId) {
      setGraphPayload(null);
      setGraphLoading(false);
      return;
    }
    let cancelled = false;
    setGraphLoading(true);
    fetchKnowledgeGraph(token, selectedId)
      .then((payload) => {
        if (!cancelled) {
          setGraphPayload(payload.nodes.length > 0 ? payload : null);
        }
      })
      .catch(() => {
        if (!cancelled) setGraphPayload(null);
      })
      .finally(() => {
        if (!cancelled) setGraphLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [knowledgeVersion, mode, selectedId, token]);

  const selected = libraries.find((item) => item.id === selectedId) ?? null;

  const handleCreate = async () => {
    const name = draftName.trim();
    if (!name) return;
    setBusy("create");
    try {
      await createKnowledgeBase(token, { name, files: createFiles });
      setDraftName("");
      setCreateFiles([]);
      await refreshKnowledge();
      setSelectedId(name);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const handleUpload = async () => {
    if (!selected || uploadFiles.length === 0) return;
    setBusy("upload");
    try {
      await uploadKnowledgeFiles(token, { name: selected.id, files: uploadFiles });
      setUploadFiles([]);
      await refreshKnowledge();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const handleReindex = async () => {
    if (!selected) return;
    setBusy("reindex");
    try {
      await reindexKnowledgeBase(token, selected.id);
      await refreshKnowledge();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <PanelView title="知识花园" subtitle="像 Obsidian 一样查看资料、概念与学习线索之间的关系。" {...panelProps}>
      {error ? <InfoCard title="当前状态" body={error} /> : null}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/60 bg-card/80 p-3 shadow-[0_16px_50px_rgba(15,23,42,0.05)]">
        <div className="inline-flex rounded-full border border-border/60 bg-muted/40 p-1">
          <Button
            type="button"
            size="sm"
            variant={mode === "graph" ? "default" : "ghost"}
            onClick={() => setMode("graph")}
            className="h-8 rounded-full gap-2"
          >
            <Network className="h-4 w-4" />
            图谱
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === "library" ? "default" : "ghost"}
            onClick={() => setMode("library")}
            className="h-8 rounded-full gap-2"
          >
            <FileText className="h-4 w-4" />
            资料
          </Button>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void refreshKnowledge()}
          disabled={loading}
          className="h-8 rounded-full gap-2"
        >
          <RefreshCw className={cn("h-4 w-4", loading ? "animate-spin" : "")} />
          刷新
        </Button>
      </div>

      {mode === "graph" ? (
        <KnowledgeGraphView
          libraries={libraries}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={loading || graphLoading}
          graphPayload={graphPayload}
        />
      ) : null}

      {mode === "library" ? (
        <>
      <InfoCard
        title="新建资料库"
        body={
          <div className="space-y-3">
            <Input
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              placeholder="输入资料库名称"
              className="max-w-sm"
            />
            <input
              type="file"
              multiple
              onChange={(event) => setCreateFiles(Array.from(event.target.files ?? []))}
            />
            <div className="text-xs text-muted-foreground">
              支持上传 Markdown、文本、PDF、Office 文档，先建立最小可用闭环。
            </div>
          </div>
        }
        actions={
          <Button
            size="sm"
            onClick={handleCreate}
            disabled={busy === "create" || !draftName.trim()}
            className="rounded-full"
          >
            {busy === "create" ? "创建中..." : "创建"}
          </Button>
        }
      />

      <InfoCard
        title="资料库概览"
        body={
          loading ? (
            <EmptyHint text="正在读取知识花园..." />
          ) : libraries.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2">
              {libraries.map((library) => {
                const active = library.id === selectedId;
                return (
                  <button
                    key={library.id}
                    type="button"
                    onClick={() => setSelectedId(library.id)}
                    className={cn(
                      "rounded-2xl border px-4 py-3 text-left transition-colors",
                      active
                        ? "border-foreground/20 bg-muted/70"
                        : "border-border/50 hover:bg-muted/40",
                    )}
                  >
                    <div className="text-sm font-semibold text-foreground">{library.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {library.source_count} 份资料 · {library.status} · {library.provider ?? "LightRAG"}
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyHint text="还没有资料库。创建一个新的知识花园后，这里会显示索引和文件清单。" />
          )
        }
      />

      <InfoCard
        title="当前资料库"
        body={
          selected ? (
            <div className="space-y-4">
              <div className="text-sm text-foreground">
                <span className="font-medium">{selected.name}</span>
                <span className="ml-3 text-muted-foreground">
                  共 {selected.files?.length ?? 0} 个文件，状态 {selected.status}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  type="file"
                  multiple
                  onChange={(event) => setUploadFiles(Array.from(event.target.files ?? []))}
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleUpload}
                  disabled={busy === "upload" || uploadFiles.length === 0}
                  className="rounded-full gap-2"
                >
                  <Upload className="h-4 w-4" />
                  {busy === "upload" ? "上传中..." : "上传资料"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleReindex}
                  disabled={busy === "reindex"}
                  className="rounded-full gap-2"
                >
                  <RefreshCw className={cn("h-4 w-4", busy === "reindex" ? "animate-spin" : "")} />
                  {busy === "reindex" ? "索引中..." : "重建索引"}
                </Button>
              </div>
              {selected.files && selected.files.length > 0 ? (
                <div className="space-y-2">
                  {selected.files.map((file) => (
                    <div
                      key={file.path}
                      className="flex items-center justify-between rounded-xl border border-border/40 px-3 py-2 text-sm"
                    >
                      <span className="truncate pr-4">{file.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {Math.max(1, Math.round(file.size / 1024))} KB
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyHint text="当前资料库还没有文件。" />
              )}
            </div>
          ) : (
            <EmptyHint text="先在上面选择一个资料库，这里会显示文件、上传和索引操作。" />
          )
        }
      />
        </>
      ) : null}
    </PanelView>
  );
}
