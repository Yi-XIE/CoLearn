import {
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type WheelEvent as ReactWheelEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
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
import type {
  KnowledgeBaseSummary,
  KnowledgeGraphEdge as ApiKnowledgeGraphEdge,
  KnowledgeGraphNode as ApiKnowledgeGraphNode,
  KnowledgeGraphPayload,
} from "@/lib/types";
import { cn } from "@/lib/utils";

import { PanelView, type PanelShellProps } from "./PanelView";

type KnowledgeGardenMode = "graph" | "library";

function InfoCard({
  title,
  body,
  actions,
}: {
  title: string;
  body: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border/50 bg-card/85 p-5 shadow-[0_16px_50px_rgba(15,23,42,0.06)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-semibold text-foreground">{title}</div>
          <div className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{body}</div>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return <div className="text-sm text-muted-foreground">{text}</div>;
}

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

type KnowledgeGraphVisualNode = {
  id: string;
  label: string;
  kind: ApiKnowledgeGraphNode["kind"];
  metadata?: Record<string, unknown>;
  x: number;
  y: number;
  size: number;
  libraryId?: string;
};

type KnowledgeGraphVisualEdge = {
  id: string;
  from: string;
  to: string;
  kind: ApiKnowledgeGraphEdge["kind"];
  metadata?: Record<string, unknown>;
};

const CONCEPT_HINTS = [
  "machine",
  "learning",
  "dataset",
  "feature",
  "label",
  "model",
  "training",
  "prediction",
  "regression",
  "classification",
  "evaluation",
  "lightrag",
  "agent",
  "state",
  "science",
  "math",
  "ai",
  "ml",
];

function titleCaseToken(value: string): string {
  if (!value) return value;
  if (value.length <= 3) return value.toUpperCase();
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

function graphNodeLabel(value: string, kind: KnowledgeGraphVisualNode["kind"]): string {
  const label = kind === "file" ? value.replace(/\.[^.]+$/, "") : value;
  return label.length > 34 ? `${label.slice(0, 33)}…` : label;
}

function conceptHintsForFile(fileName: string): string[] {
  const normalized = fileName
    .replace(/\.[^.]+$/, "")
    .split(/[^a-zA-Z0-9\u4e00-\u9fa5]+/)
    .filter(Boolean);
  const english = normalized
    .map((token) => token.toLowerCase())
    .filter((token) => CONCEPT_HINTS.includes(token));
  const chinese = normalized.filter((token) => /[\u4e00-\u9fa5]/.test(token)).slice(0, 2);
  return Array.from(new Set([...english.map(titleCaseToken), ...chinese])).slice(0, 3);
}

function buildKnowledgeGraph(libraries: KnowledgeBaseSummary[]): {
  nodes: KnowledgeGraphVisualNode[];
  edges: KnowledgeGraphVisualEdge[];
} {
  const nodes: KnowledgeGraphVisualNode[] = [];
  const edges: KnowledgeGraphVisualEdge[] = [];
  const conceptIndex = new Map<string, string>();
  const centerX = 580;
  const centerY = 320;
  const libraryRadius = 210;
  const fileRadius = 150;

  libraries.forEach((library, libraryIndex) => {
    const angle = (Math.PI * 2 * libraryIndex) / Math.max(libraries.length, 1) - Math.PI / 2;
    const libraryX = centerX + Math.cos(angle) * libraryRadius;
    const libraryY = centerY + Math.sin(angle) * libraryRadius;
    const libraryNodeId = `library:${library.id}`;
    nodes.push({
      id: libraryNodeId,
      label: library.name || library.id,
      kind: "library",
      metadata: {
        library_id: library.id,
        status: library.status,
        provider: library.provider,
      },
      x: libraryX,
      y: libraryY,
      size: graphNodeSize("library"),
      libraryId: library.id,
    });

    const files = (library.files ?? []).slice(0, 7);
    files.forEach((file, fileIndex) => {
      const fileAngle =
        angle + (files.length === 1 ? 0 : (fileIndex - (files.length - 1) / 2) * 0.46);
      const fileNodeId = `file:${library.id}:${file.path}`;
      const fileX = libraryX + Math.cos(fileAngle) * fileRadius;
      const fileY = libraryY + Math.sin(fileAngle) * fileRadius;
      nodes.push({
        id: fileNodeId,
        label: file.name,
        kind: "file",
        metadata: {
          library_id: library.id,
          path: file.path,
          size: file.size,
          modified: file.modified,
          mime_type: file.mime_type,
        },
        x: fileX,
        y: fileY,
        size: graphNodeSize("file"),
        libraryId: library.id,
      });
      edges.push({
        id: `edge:contains:${libraryNodeId}:${fileNodeId}`,
        from: libraryNodeId,
        to: fileNodeId,
        kind: "contains",
        metadata: { library_id: library.id },
      });

      conceptHintsForFile(file.name).forEach((concept, conceptIndexForFile) => {
        const conceptKey = concept.toLowerCase();
        let conceptNodeId = conceptIndex.get(conceptKey);
        if (!conceptNodeId) {
          conceptNodeId = `concept:${conceptKey}`;
          conceptIndex.set(conceptKey, conceptNodeId);
          const conceptAngle =
            fileAngle + 0.72 + conceptIndexForFile * 0.36 + conceptIndex.size * 0.17;
          nodes.push({
            id: conceptNodeId,
            label: concept,
            kind: "concept",
            metadata: { source: "frontend-fallback" },
            x: centerX + Math.cos(conceptAngle) * 345,
            y: centerY + Math.sin(conceptAngle) * 235,
            size: graphNodeSize("concept"),
          });
        }
        edges.push({
          id: `edge:mentions:${fileNodeId}:${conceptNodeId}`,
          from: fileNodeId,
          to: conceptNodeId,
          kind: "mentions",
          metadata: { library_id: library.id, source: "frontend-fallback" },
        });
      });
    });
  });

  return { nodes, edges };
}

function graphNodeSize(kind: ApiKnowledgeGraphNode["kind"]): number {
  if (kind === "library") return 18;
  if (kind === "file") return 7;
  return 5;
}

function graphNodeColor(kind: ApiKnowledgeGraphNode["kind"]): string {
  if (kind === "library") return "#2563eb";
  if (kind === "file") return "#0ea5e9";
  if (kind === "lesson") return "#4f46e5";
  if (kind === "exercise") return "#f59e0b";
  if (kind === "evidence") return "#10b981";
  return "#f97316";
}

function graphEdgeColor(kind: ApiKnowledgeGraphEdge["kind"]): string {
  if (kind === "contains") return "rgba(37, 99, 235, 0.24)";
  if (kind === "supports") return "rgba(16, 185, 129, 0.28)";
  if (kind === "practices") return "rgba(245, 158, 11, 0.28)";
  return "rgba(100, 116, 139, 0.22)";
}

function metadataString(metadata: Record<string, unknown> | undefined, key: string): string | undefined {
  const value = metadata?.[key];
  return typeof value === "string" && value.trim() ? value : undefined;
}

function graphLibraryIdForNode(node: ApiKnowledgeGraphNode): string | undefined {
  return metadataString(node.metadata, "library_id") ?? (node.kind === "library" ? node.id.replace(/^library:/, "") : undefined);
}

function layoutKnowledgeGraphPayload(payload: KnowledgeGraphPayload): {
  nodes: KnowledgeGraphVisualNode[];
  edges: KnowledgeGraphVisualEdge[];
} {
  const centerX = 580;
  const centerY = 320;
  const libraryRadius = 180;
  const fileRadius = 155;
  const relatedRadius = 92;
  const placed = new Set<string>();
  const visualById = new Map<string, KnowledgeGraphVisualNode>();

  payload.nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(payload.nodes.length, 1) - Math.PI / 2;
    visualById.set(node.id, {
      id: node.id,
      label: node.label,
      kind: node.kind,
      metadata: node.metadata,
      x: centerX + Math.cos(angle) * 360,
      y: centerY + Math.sin(angle) * 245,
      size: graphNodeSize(node.kind),
      libraryId: graphLibraryIdForNode(node),
    });
  });

  const outgoing = new Map<string, ApiKnowledgeGraphEdge[]>();
  payload.edges.forEach((edge) => {
    const edges = outgoing.get(edge.source) ?? [];
    edges.push(edge);
    outgoing.set(edge.source, edges);
  });

  const place = (id: string, x: number, y: number) => {
    const node = visualById.get(id);
    if (!node) return;
    node.x = Math.max(42, Math.min(1118, x));
    node.y = Math.max(52, Math.min(588, y));
    placed.add(id);
  };

  const libraryNodes = payload.nodes.filter((node) => node.kind === "library");
  libraryNodes.forEach((library, libraryIndex) => {
    const libraryAngle =
      libraryNodes.length === 1
        ? -Math.PI / 2
        : (Math.PI * 2 * libraryIndex) / libraryNodes.length - Math.PI / 2;
    const libraryX =
      libraryNodes.length === 1 ? centerX : centerX + Math.cos(libraryAngle) * libraryRadius;
    const libraryY =
      libraryNodes.length === 1 ? centerY : centerY + Math.sin(libraryAngle) * libraryRadius;
    place(library.id, libraryX, libraryY);

    const files = (outgoing.get(library.id) ?? [])
      .filter((edge) => edge.kind === "contains")
      .map((edge) => edge.target)
      .filter((target) => visualById.get(target)?.kind === "file");
    files.forEach((fileId, fileIndex) => {
      const fileAngle =
        libraryAngle + (files.length === 1 ? 0 : (fileIndex - (files.length - 1) / 2) * 0.55);
      const fileNode = visualById.get(fileId);
      if (!fileNode) return;
      const fileX = libraryX + Math.cos(fileAngle) * fileRadius;
      const fileY = libraryY + Math.sin(fileAngle) * fileRadius;
      fileNode.libraryId = graphLibraryIdForNode(library);
      place(fileId, fileX, fileY);

      const related = (outgoing.get(fileId) ?? []).map((edge) => edge.target);
      related.forEach((relatedId, relatedIndex) => {
        const relatedNode = visualById.get(relatedId);
        if (!relatedNode) return;
        const relatedAngle =
          fileAngle + 0.78 + (related.length === 1 ? 0 : (relatedIndex - (related.length - 1) / 2) * 0.42);
        relatedNode.libraryId = fileNode.libraryId;
        place(
          relatedId,
          fileX + Math.cos(relatedAngle) * relatedRadius,
          fileY + Math.sin(relatedAngle) * relatedRadius,
        );
      });
    });
  });

  const unplaced = Array.from(visualById.values()).filter((node) => !placed.has(node.id));
  unplaced.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(unplaced.length, 1) - Math.PI / 2;
    place(node.id, centerX + Math.cos(angle) * 395, centerY + Math.sin(angle) * 255);
  });

  return {
    nodes: Array.from(visualById.values()),
    edges: payload.edges.map((edge) => ({
      id: edge.id,
      from: edge.source,
      to: edge.target,
      kind: edge.kind,
      metadata: edge.metadata,
    })),
  };
}

function KnowledgeGraphView({
  libraries,
  selectedId,
  onSelect,
  loading,
  graphPayload,
}: {
  libraries: KnowledgeBaseSummary[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading: boolean;
  graphPayload: KnowledgeGraphPayload | null;
}) {
  const fallbackGraph = useMemo(() => buildKnowledgeGraph(libraries), [libraries]);
  const apiGraph = useMemo(
    () => (graphPayload ? layoutKnowledgeGraphPayload(graphPayload) : null),
    [graphPayload],
  );
  const { nodes, edges } = apiGraph ?? fallbackGraph;
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const selectedLibrary = libraries.find((library) => library.id === selectedId) ?? libraries[0] ?? null;
  const libraryCount = nodes.filter((node) => node.kind === "library").length || libraries.length;
  const fileCount =
    nodes.filter((node) => node.kind === "file").length ||
    libraries.reduce((total, item) => total + (item.files?.length ?? 0), 0);
  const relatedCount = nodes.filter((node) => !["library", "file"].includes(node.kind)).length;
  const [viewTransform, setViewTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [dragStart, setDragStart] = useState<{
    pointerX: number;
    pointerY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const activeNodeId = hoveredNodeId ?? focusedNodeId;
  const connectedNodeIds = useMemo(() => {
    if (!activeNodeId) return new Set<string>();
    const next = new Set<string>([activeNodeId]);
    edges.forEach((edge) => {
      if (edge.from === activeNodeId) next.add(edge.to);
      if (edge.to === activeNodeId) next.add(edge.from);
    });
    return next;
  }, [activeNodeId, edges]);

  const resetGraphView = () => {
    setViewTransform({ x: 0, y: 0, scale: 1 });
    setFocusedNodeId(null);
  };

  const handleGraphWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const direction = event.deltaY > 0 ? -1 : 1;
    setViewTransform((current) => ({
      ...current,
      scale: Math.min(2.4, Math.max(0.55, current.scale + direction * 0.12)),
    }));
  };

  const handleGraphPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    setDragStart({
      pointerX: event.clientX,
      pointerY: event.clientY,
      originX: viewTransform.x,
      originY: viewTransform.y,
    });
  };

  const handleGraphPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!dragStart) return;
    setViewTransform((current) => ({
      ...current,
      x: dragStart.originX + event.clientX - dragStart.pointerX,
      y: dragStart.originY + event.clientY - dragStart.pointerY,
    }));
  };

  const handleGraphPointerUp = () => {
    setDragStart(null);
  };

  if (loading) {
    return (
      <InfoCard
        title="知识图谱"
        body={<EmptyHint text="正在读取知识花园，图谱马上长出来。" />}
      />
    );
  }

  if (!libraries.length) {
    return (
      <InfoCard
        title="知识图谱"
        body="还没有资料库。先上传课程、笔记或教材，知识花园会自动生成第一张关系图。"
      />
    );
  }

  return (
    <div className="relative min-h-[620px] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
      <div className="absolute inset-x-0 top-0 z-10 flex h-10 items-center justify-center border-b border-slate-200/80 bg-white/88 text-[12px] text-slate-500 backdrop-blur">
        <div className="absolute left-4 flex items-center gap-2">
          <button
            type="button"
            onClick={resetGraphView}
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600 shadow-sm hover:bg-slate-50"
          >
            复位
          </button>
          <span className="text-[11px] text-slate-400">拖拽移动 · 滚轮缩放 · 点击聚焦</span>
        </div>
        <span className="font-medium tracking-[0.02em] text-slate-700">关系图谱</span>
        <div className="absolute right-4 flex items-center gap-3 text-[11px] text-slate-500">
          <span>{libraryCount} 库</span>
          <span>{fileCount} 文件</span>
          <span>{relatedCount} 线索</span>
          <span>{Math.round(viewTransform.scale * 100)}%</span>
        </div>
      </div>

      <svg
        viewBox="0 0 1160 640"
        role="img"
        aria-label="知识花园图谱"
        className={cn("h-[clamp(620px,72vh,820px)] w-full touch-none", dragStart ? "cursor-grabbing" : "cursor-grab")}
        onWheel={handleGraphWheel}
        onPointerDown={handleGraphPointerDown}
        onPointerMove={handleGraphPointerMove}
        onPointerUp={handleGraphPointerUp}
        onPointerLeave={handleGraphPointerUp}
      >
        <rect width="1160" height="640" fill="#ffffff" />
        <path d="M0 84H1160M0 320H1160M0 556H1160M160 0V640M580 0V640M1000 0V640" stroke="rgba(148,163,184,0.13)" strokeWidth="1" />
        <g transform={`translate(${viewTransform.x} ${viewTransform.y}) scale(${viewTransform.scale})`}>
          {edges.map((edge, index) => {
            const from = nodeById.get(edge.from);
            const to = nodeById.get(edge.to);
            if (!from || !to) return null;
            const active = !activeNodeId || (connectedNodeIds.has(edge.from) && connectedNodeIds.has(edge.to));
            return (
              <line
                key={edge.id || `${edge.from}-${edge.to}-${index}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={graphEdgeColor(edge.kind)}
                strokeWidth={active ? (edge.kind === "contains" ? 1.55 : 1.1) : 0.55}
                opacity={active ? 1 : 0.16}
              />
            );
          })}
          {nodes.map((node) => {
            const selected = node.libraryId === selectedId || node.id === `library:${selectedId}`;
            const graphActive = !activeNodeId || connectedNodeIds.has(node.id);
            const focused = activeNodeId === node.id;
            const fill = graphNodeColor(node.kind);
            const labelY = node.y + node.size + (node.kind === "library" ? 16 : 12);
            return (
              <g
                key={node.id}
                role={node.kind === "library" ? "button" : undefined}
                tabIndex={node.kind === "library" ? 0 : undefined}
                onPointerDown={(event) => event.stopPropagation()}
                onMouseEnter={() => setHoveredNodeId(node.id)}
                onMouseLeave={() => setHoveredNodeId(null)}
                onClick={() => {
                  setFocusedNodeId((current) => (current === node.id ? null : node.id));
                  if (node.libraryId) onSelect(node.libraryId);
                }}
                className="cursor-pointer"
              >
                {selected || focused ? (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.size + (focused ? 12 : 8)}
                    fill={fill}
                    opacity={focused ? 0.15 : 0.1}
                  />
                ) : null}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.size + (focused ? 2.5 : selected ? 1.5 : 0)}
                  fill={fill}
                  opacity={graphActive ? (node.kind === "library" ? 0.98 : 0.9) : 0.25}
                  stroke="#ffffff"
                  strokeWidth={focused ? 2.4 : node.kind === "library" ? 1.8 : 1}
                />
                <text
                  x={node.x}
                  y={labelY}
                  textAnchor="middle"
                  pointerEvents="none"
                  style={{
                    fill: focused ? "#0f172a" : graphActive ? "#475569" : "#cbd5e1",
                    fontSize: node.kind === "library" ? 12 : 10.5,
                    fontWeight: focused || node.kind === "library" ? 650 : 480,
                  }}
                >
                  {graphNodeLabel(node.label, node.kind)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="absolute bottom-4 left-4 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span className="rounded-full border border-slate-200 bg-white/90 px-2.5 py-1 shadow-sm">蓝色：资料库 / 文件</span>
        <span className="rounded-full border border-slate-200 bg-white/90 px-2.5 py-1 shadow-sm">橙绿：概念 / 练习 / 证据</span>
        <span className="rounded-full border border-slate-200 bg-white/90 px-2.5 py-1 shadow-sm">
          {graphPayload ? "后端 graph API" : "前端 fallback"}
        </span>
      </div>

      {selectedLibrary ? (
        <div className="absolute bottom-4 right-4 w-[min(300px,calc(100%-2rem))] rounded-lg border border-slate-200 bg-white/92 p-3 text-slate-700 shadow-[0_14px_34px_rgba(15,23,42,0.10)] backdrop-blur">
          <div className="flex items-center justify-between gap-3">
            <div className="truncate text-[13px] font-semibold">{selectedLibrary.name}</div>
            <div className="shrink-0 text-[11px] text-slate-500">{selectedLibrary.status}</div>
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            {selectedLibrary.files?.length ?? 0} 个文件 · {selectedLibrary.provider ?? "LightRAG"}
          </div>
          <div className="mt-2 space-y-1">
            {(selectedLibrary.files ?? []).slice(0, 4).map((file) => (
              <div key={file.path} className="truncate text-[11px] text-slate-600">
                {file.name}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
