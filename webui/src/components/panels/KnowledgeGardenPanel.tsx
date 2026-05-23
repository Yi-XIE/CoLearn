import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  RotateCcw,
  Settings2,
  Upload,
  X,
} from "lucide-react";

import {
  createKnowledgeBase,
  fetchKnowledgeFilePreview,
  fetchKnowledgeGraph,
  listKnowledgeBases,
  listKnowledgeFiles,
  uploadKnowledgeFiles,
} from "@/lib/api";
import type {
  KnowledgeBaseSummary,
  KnowledgeFilePreview,
  KnowledgeGraphPayload,
} from "@/lib/types";

import { MarkdownText } from "@/components/MarkdownText";

import {
  KnowledgeGraphView,
  type KnowledgeGraphPreviewNode,
  type KnowledgeGraphSettings,
} from "./knowledge/KnowledgeGraphView";
import { EmptyHint, InfoCard } from "./knowledge/KnowledgePanelPrimitives";
import { PanelView, type PanelShellProps } from "./PanelView";

type PreviewDocument = KnowledgeFilePreview & { sourceLabel?: string };

const DEFAULT_GRAPH_SETTINGS: KnowledgeGraphSettings = {
  showLabels: true,
  labelOpacity: 0.72,
  nodeScale: 1,
  edgeWidth: 1,
  centerForce: 0.0025,
  repulsionForce: 1,
  springForce: 1,
  edgeLength: 1,
};

function statusLabel(status: string): "已完成" | "待处理" {
  const normalized = status.toLowerCase();
  if (normalized === "ready" || normalized === "completed") return "已完成";
  return "待处理";
}

function buildNodeMarkdown(
  node: KnowledgeGraphPreviewNode,
  libraries: KnowledgeBaseSummary[],
): PreviewDocument {
  const library = libraries.find((item) => item.id === node.libraryId) ?? null;

  if (node.kind === "library") {
    const files = library?.files ?? [];
    return {
      name: node.label,
      path: node.id,
      kind: "markdown",
      content: `# ${node.label}

资料库

## ${node.label}

- 状态：${library ? statusLabel(library.status) : "待处理"}
- 文件数：${files.length}

${files.length ? "这个资料库已经进入知识花园。" : "这个资料库里还没有文件。"}`,
      sourceLabel: "资料库",
    };
  }

  if (node.kind === "concept") {
    const source = typeof node.metadata?.source === "string" ? node.metadata.source : "图谱提取";
    const libraryLine = library ? `\n- 资料库：${library.name}` : "";
    return {
      name: node.label,
      path: node.id,
      kind: "markdown",
      content: `# ${node.label}

概念节点

## ${node.label}

- 类型：概念
- 来源：${source}${libraryLine}`,
      sourceLabel: "概念节点",
    };
  }

  const libraryLine = library ? `\n- 资料库：${library.name}` : "";
  return {
    name: node.label,
    path: node.id,
    kind: "markdown",
    content: `# ${node.label}

## ${node.label}

- 类型：${node.kind}${libraryLine}`,
    sourceLabel: "节点预览",
  };
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-[0_1px_3px_rgba(15,23,42,0.04)] transition hover:bg-slate-50 hover:text-slate-900"
    >
      {children}
    </button>
  );
}

function SettingSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block space-y-2">
      <div className="text-[13px] text-slate-700">{label}</div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-slate-700"
      />
    </label>
  );
}

export function KnowledgeGardenPanel({
  token,
  ...panelProps
}: PanelShellProps & {
  token: string;
}) {
  const DEFAULT_GRAPH_SCALE = 1.3;
  const [libraries, setLibraries] = useState<KnowledgeBaseSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [graphPayload, setGraphPayload] = useState<KnowledgeGraphPayload | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [resetVersion, setResetVersion] = useState(0);
  const [graphScale, setGraphScale] = useState(DEFAULT_GRAPH_SCALE);
  const [previewNode, setPreviewNode] = useState<KnowledgeGraphPreviewNode | null>(null);
  const [previewDocument, setPreviewDocument] = useState<PreviewDocument | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [expandedLibraries, setExpandedLibraries] = useState<Record<string, boolean>>({});
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [graphSettings, setGraphSettings] = useState<KnowledgeGraphSettings>(DEFAULT_GRAPH_SETTINGS);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
      setSelectedId((current) => {
        if (current && withFiles.some((base) => base.id === current)) return current;
        return withFiles[0]?.id ?? "";
      });
      setExpandedLibraries((current) => {
        const next: Record<string, boolean> = {};
        withFiles.forEach((base) => {
          next[base.id] = current[base.id] ?? false;
        });
        return next;
      });
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
    if (!selectedId) {
      setGraphPayload(null);
      setGraphLoading(false);
      return;
    }

    let cancelled = false;
    setGraphLoading(true);
    fetchKnowledgeGraph(token, selectedId)
      .then((payload) => {
        if (!cancelled) setGraphPayload(payload.nodes.length > 0 ? payload : null);
      })
      .catch((err) => {
        if (!cancelled) {
          setGraphPayload(null);
          setError((err as Error).message);
        }
      })
      .finally(() => {
        if (!cancelled) setGraphLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId, token]);

  const selectedLibrary = useMemo(
    () => libraries.find((library) => library.id === selectedId) ?? null,
    [libraries, selectedId],
  );

  const completedLibraries = useMemo(
    () => libraries.filter((library) => statusLabel(library.status) === "已完成"),
    [libraries],
  );
  const pendingLibraries = useMemo(
    () => libraries.filter((library) => statusLabel(library.status) === "待处理"),
    [libraries],
  );

  const handlePickFiles = () => {
    fileInputRef.current?.click();
  };

  const handleFilesChanged = (event: ChangeEvent<HTMLInputElement>) => {
    setSelectedFiles(Array.from(event.target.files ?? []));
  };

  const handleUpload = async () => {
    if (!selectedFiles.length) return;
    const targetName = draftName.trim() || selectedLibrary?.id || "";
    if (!targetName) return;

    setSubmitting(true);
    setError(null);
    try {
      const existing =
        libraries.find((library) => library.id === targetName)
        ?? libraries.find((library) => library.name === targetName);
      if (existing) {
        await uploadKnowledgeFiles(token, { name: existing.id, files: selectedFiles });
      } else {
        await createKnowledgeBase(token, { name: targetName, files: selectedFiles });
      }
      await refreshKnowledge();
      setSelectedId(existing?.id ?? targetName);
      setDraftName("");
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const handlePreviewNode = useCallback(
    async (node: KnowledgeGraphPreviewNode) => {
      setPreviewNode(node);
      setPreviewLoading(true);
      setPreviewDocument(null);
      try {
        if (node.kind === "file" && node.libraryId) {
          const filePath = typeof node.metadata?.path === "string" ? node.metadata.path : node.label;
          const preview = await fetchKnowledgeFilePreview(token, node.libraryId, filePath);
          setPreviewDocument({ ...preview, sourceLabel: node.libraryId });
        } else {
          setPreviewDocument(buildNodeMarkdown(node, libraries));
        }
      } catch (err) {
        setPreviewDocument({
          name: node.label,
          path: node.id,
          kind: "markdown",
          content: `# ${node.label}\n\n预览加载失败。\n\n${(err as Error).message}`,
          sourceLabel: "预览",
        });
      } finally {
        setPreviewLoading(false);
      }
    },
    [libraries, token],
  );

  const renderLibraryItem = (library: KnowledgeBaseSummary) => {
    const active = library.id === selectedId;
    const isExpanded = expandedLibraries[library.id] ?? false;
    const files = (library.files ?? []).filter((file) => file.name);

    return (
      <div key={library.id} className="rounded-xl px-2 py-0.5 transition">
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={isExpanded ? `收起 ${library.name}` : `展开 ${library.name}`}
            onClick={() =>
              setExpandedLibraries((current) => ({
                ...current,
                [library.id]: !isExpanded,
              }))}
            className="flex h-5.5 w-5.5 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          >
            {isExpanded ? (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden />
            )}
          </button>
          <button
            type="button"
            onClick={() => setSelectedId(library.id)}
            className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-1 text-left"
          >
            <FolderOpen className="h-4 w-4 shrink-0 text-slate-400" aria-hidden />
            <span
              className={`truncate text-[14px] leading-[18px] ${
                active ? "font-medium text-slate-900" : "text-slate-600"
              }`}
            >
              {library.name}
            </span>
          </button>
        </div>

        {isExpanded ? (
          <div className="mt-0.5 space-y-0.5 pl-8">
            {files.length ? (
              files.map((file) => (
                <button
                  key={`${library.id}-${file.path}`}
                  type="button"
                  onClick={() =>
                    void handlePreviewNode({
                      id: `file:${library.id}:${file.path}`,
                      label: file.name,
                      kind: "file",
                      metadata: {
                        library_id: library.id,
                        path: file.path,
                        size: file.size,
                        modified: file.modified,
                        mime_type: file.mime_type,
                      },
                      libraryId: library.id,
                    })}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left text-slate-500 transition hover:bg-[#F2F3F3] hover:text-slate-700"
                >
                  <FileText className="h-3.5 w-3.5 shrink-0 text-slate-300" aria-hidden />
                  <span className="truncate text-[13px] leading-[18px]">{file.name}</span>
                </button>
              ))
            ) : (
              <div className="px-2 py-1 text-[13px] leading-[18px] text-slate-400">暂无文件</div>
            )}
          </div>
        ) : null}
      </div>
    );
  };

  const graphToolbar = (
    <div className="relative flex items-center gap-3 rounded-full border border-slate-200 bg-white/96 px-3 py-2 shadow-[0_6px_18px_rgba(15,23,42,0.06)] backdrop-blur">
      <IconButton label="上传资料" onClick={handlePickFiles}>
        <Upload className="h-4 w-4" aria-hidden />
      </IconButton>
      <IconButton
        label="复位图谱"
        onClick={() => {
          setResetVersion((value) => value + 1);
          setGraphScale(DEFAULT_GRAPH_SCALE);
        }}
      >
        <RotateCcw className="h-4 w-4" aria-hidden />
      </IconButton>
      <IconButton label="图谱设置" onClick={() => setSettingsOpen((open) => !open)}>
        <Settings2 className="h-4 w-4" aria-hidden />
      </IconButton>

      <label className="ml-1 flex items-center">
        <span className="sr-only">图谱缩放</span>
        <div className="relative w-32">
          <div className="absolute left-0 right-0 top-1/2 h-[2px] -translate-y-1/2 rounded-full bg-slate-200" />
          <div
            className="absolute left-0 top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-[#013FF8]"
            style={{ width: `${((graphScale - 0.72) / (2.2 - 0.72)) * 100}%` }}
          />
          <input
            aria-label="图谱缩放"
            type="range"
            min={0.72}
            max={2.2}
            step={0.01}
            value={graphScale}
            onChange={(event) => setGraphScale(Number(event.target.value))}
            className="knowledge-garden-zoom relative top-px z-10 h-6 w-full cursor-pointer appearance-none bg-transparent"
          />
        </div>
      </label>

      {settingsOpen ? (
        <div className="absolute bottom-full left-0 z-30 mb-3 w-[320px] rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_14px_34px_rgba(15,23,42,0.08)]">
          <div className="space-y-4">
            <div>
              <div className="pb-3 text-sm font-semibold text-slate-900">外观</div>
              <div className="space-y-3">
                <label className="flex items-center justify-between gap-3 text-[13px] text-slate-700">
                  <span>显示标签</span>
                  <button
                    type="button"
                    aria-pressed={graphSettings.showLabels}
                    onClick={() =>
                      setGraphSettings((current) => ({
                        ...current,
                        showLabels: !current.showLabels,
                      }))}
                    className={`relative h-6 w-11 rounded-full transition ${
                      graphSettings.showLabels ? "bg-slate-900" : "bg-slate-200"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition ${
                        graphSettings.showLabels ? "left-[22px]" : "left-0.5"
                      }`}
                    />
                  </button>
                </label>
                <SettingSlider
                  label="文本透明度"
                  min={20}
                  max={100}
                  step={1}
                  value={Math.round(graphSettings.labelOpacity * 100)}
                  onChange={(value) =>
                    setGraphSettings((current) => ({ ...current, labelOpacity: value / 100 }))}
                />
                <SettingSlider
                  label="节点大小"
                  min={70}
                  max={150}
                  step={1}
                  value={Math.round(graphSettings.nodeScale * 100)}
                  onChange={(value) =>
                    setGraphSettings((current) => ({ ...current, nodeScale: value / 100 }))}
                />
                <SettingSlider
                  label="连线粗细"
                  min={50}
                  max={180}
                  step={1}
                  value={Math.round(graphSettings.edgeWidth * 100)}
                  onChange={(value) =>
                    setGraphSettings((current) => ({ ...current, edgeWidth: value / 100 }))}
                />
              </div>
            </div>

            <div className="border-t border-slate-100 pt-4">
              <div className="pb-3 text-sm font-semibold text-slate-900">力度</div>
              <div className="space-y-3">
                <SettingSlider
                  label="图谱向心力"
                  min={10}
                  max={80}
                  step={1}
                  value={Math.round(graphSettings.centerForce * 10000)}
                  onChange={(value) =>
                    setGraphSettings((current) => ({ ...current, centerForce: value / 10000 }))}
                />
                <SettingSlider
                  label="节点间排斥力"
                  min={50}
                  max={180}
                  step={1}
                  value={Math.round(graphSettings.repulsionForce * 100)}
                  onChange={(value) =>
                    setGraphSettings((current) => ({ ...current, repulsionForce: value / 100 }))}
                />
                <SettingSlider
                  label="相连节点间的吸引力"
                  min={50}
                  max={180}
                  step={1}
                  value={Math.round(graphSettings.springForce * 100)}
                  onChange={(value) =>
                    setGraphSettings((current) => ({ ...current, springForce: value / 100 }))}
                />
                <SettingSlider
                  label="连线长度"
                  min={70}
                  max={160}
                  step={1}
                  value={Math.round(graphSettings.edgeLength * 100)}
                  onChange={(value) =>
                    setGraphSettings((current) => ({ ...current, edgeLength: value / 100 }))}
                />
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );

  return (
    <PanelView
      title="知识花园"
      subtitle="把资料、概念和线索收进同一张可探索的知识图谱。"
      fluidContent
      contentClassName="px-6 pt-6 pb-0"
      {...panelProps}
    >
      {error ? <InfoCard title="当前状态" body={error} /> : null}

      <section className="relative min-h-0 flex-1">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFilesChanged}
          accept=".md,.txt,.pdf,.docx,.pptx,.xlsx"
        />

        {selectedFiles.length ? (
          <div className="absolute left-6 top-4 z-20 flex max-w-[min(520px,calc(100%-2rem))] flex-wrap items-center gap-2 rounded-2xl border border-white/80 bg-white/94 p-3 shadow-[0_18px_48px_rgba(15,23,42,0.12)] backdrop-blur">
            <input
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              placeholder={selectedLibrary ? `留空则上传到 ${selectedLibrary.name}` : "输入资料库名称"}
              className="h-9 min-w-[220px] flex-1 rounded-xl border border-slate-200 px-3 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-slate-300"
            />
            <button
              type="button"
              disabled={submitting}
              onClick={handleUpload}
              className="h-9 rounded-xl bg-slate-950 px-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "上传中..." : "开始上传"}
            </button>
            {selectedFiles.slice(0, 3).map((file) => (
              <span
                key={`${file.name}-${file.size}`}
                className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600"
              >
                {file.name}
              </span>
            ))}
            {selectedFiles.length > 3 ? (
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-500">
                +{selectedFiles.length - 3}
              </span>
            ) : null}
          </div>
        ) : null}

        {loading && libraries.length === 0 ? (
          <InfoCard title="知识花园" body={<EmptyHint text="正在整理知识图谱..." />} />
        ) : libraries.length === 0 ? (
          <InfoCard title="知识花园" body={<EmptyHint text="先上传资料，图谱会慢慢长出来。" />} />
        ) : (
          <>
            <div
              className={
                previewNode
                  ? "flex h-[calc(100vh-170px)] w-[60vw] max-w-[calc(100%-40vw)] items-center -translate-y-4"
                  : "flex h-[calc(100vh-170px)] w-[calc(100%-320px)] items-center -translate-y-4"
              }
            >
              <KnowledgeGraphView
                libraries={libraries}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onPreviewNode={handlePreviewNode}
                loading={graphLoading}
                graphPayload={graphPayload}
                minimal
                resetVersion={resetVersion}
                settings={graphSettings}
                scale={graphScale}
                onScaleChange={setGraphScale}
              />
            </div>

            <div className="pointer-events-none absolute bottom-10 left-6 z-20 flex">
              <div className="pointer-events-auto">{graphToolbar}</div>
            </div>

            {!previewNode ? (
              <aside className="fixed inset-y-0 right-0 z-30 w-[320px] border-l border-slate-200/90 bg-white">
                <div className="scrollbar-none h-full overflow-y-auto px-3 pb-3 pt-10">
                  {completedLibraries.length ? (
                    <div>
                      <div className="px-3 pb-2 text-[13px] font-medium text-slate-400">已完成</div>
                      <div className="space-y-1">{completedLibraries.map(renderLibraryItem)}</div>
                    </div>
                  ) : null}

                  {pendingLibraries.length ? (
                    <div className={completedLibraries.length ? "mt-5" : ""}>
                      <div className="px-3 pb-2 text-[13px] font-medium text-slate-400">待处理</div>
                      <div className="space-y-1">{pendingLibraries.map(renderLibraryItem)}</div>
                    </div>
                  ) : null}
                </div>
              </aside>
            ) : (
              <aside className="fixed inset-y-0 right-0 z-30 w-[40vw] min-w-[520px] border-l border-slate-200/90 bg-white">
                <button
                  type="button"
                  aria-label="关闭预览"
                  onClick={() => {
                    setPreviewNode(null);
                    setPreviewDocument(null);
                    setPreviewLoading(false);
                  }}
                  className="absolute right-6 top-6 z-10 flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
                >
                  <X className="h-4 w-4" aria-hidden />
                </button>

                <div className="h-full overflow-y-auto px-8 py-6">
                  {previewLoading ? (
                    <div className="pt-10 text-[15px] leading-7 text-slate-500">正在加载预览...</div>
                  ) : previewDocument ? (
                    <MarkdownText className="pr-10 text-[16px] leading-8 text-slate-700">
                      {previewDocument.content}
                    </MarkdownText>
                  ) : (
                    <div className="pt-10 text-[15px] leading-7 text-slate-500">暂无预览内容。</div>
                  )}
                </div>
              </aside>
            )}
          </>
        )}
      </section>
    </PanelView>
  );
}
