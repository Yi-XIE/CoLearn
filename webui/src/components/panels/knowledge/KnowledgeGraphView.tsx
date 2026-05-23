import {
  useEffect,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
  useMemo,
  useState,
} from "react";

import type {
  KnowledgeBaseSummary,
  KnowledgeGraphEdge as ApiKnowledgeGraphEdge,
  KnowledgeGraphNode as ApiKnowledgeGraphNode,
  KnowledgeGraphPayload,
} from "@/lib/types";
import { cn } from "@/lib/utils";

import { EmptyHint, InfoCard } from "./KnowledgePanelPrimitives";

export type KnowledgeGraphPreviewNode = {
  id: string;
  label: string;
  kind: ApiKnowledgeGraphNode["kind"];
  metadata?: Record<string, unknown>;
  libraryId?: string;
};

export interface KnowledgeGraphSettings {
  showLabels: boolean;
  labelOpacity: number;
  nodeScale: number;
  edgeWidth: number;
  centerForce: number;
  repulsionForce: number;
  springForce: number;
  edgeLength: number;
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

const GRAPH_WIDTH = 1160;
const GRAPH_HEIGHT = 640;
const GRAPH_CENTER_X = GRAPH_WIDTH / 2;
const GRAPH_CENTER_Y = GRAPH_HEIGHT / 2;
const MIN_GRAPH_SCALE = 0.72;
const MAX_GRAPH_SCALE = 2.2;

function centeredTransform(scale: number) {
  return {
    x: GRAPH_CENTER_X - GRAPH_CENTER_X * scale,
    y: GRAPH_CENTER_Y - GRAPH_CENTER_Y * scale,
    scale,
  };
}

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

function buildKnowledgeGraph(libraries: KnowledgeBaseSummary[], _settings?: KnowledgeGraphSettings): {
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

  return { nodes: resolveNodeCollisions(nodes), edges };
}

function graphNodeSize(kind: ApiKnowledgeGraphNode["kind"]): number {
  if (kind === "library") return 10;
  if (kind === "file") return 4.5;
  return 3.2;
}

function graphNodeColor(kind: ApiKnowledgeGraphNode["kind"]): string {
  if (kind === "library") return "#111827";
  if (kind === "file") return "#6b7280";
  if (kind === "lesson") return "#9ca3af";
  if (kind === "exercise") return "#9ca3af";
  if (kind === "evidence") return "#9ca3af";
  return "#d1d5db";
}

function graphEdgeColor(kind: ApiKnowledgeGraphEdge["kind"]): string {
  if (kind === "contains") return "rgba(203, 213, 225, 0.82)";
  if (kind === "supports") return "rgba(209, 213, 219, 0.72)";
  if (kind === "practices") return "rgba(209, 213, 219, 0.72)";
  return "rgba(229, 231, 235, 0.7)";
}

function resolveNodeCollisions(nodes: KnowledgeGraphVisualNode[]): KnowledgeGraphVisualNode[] {
  const next = nodes.map((node) => ({ ...node }));
  for (let pass = 0; pass < 24; pass += 1) {
    for (let a = 0; a < next.length; a += 1) {
      for (let b = a + 1; b < next.length; b += 1) {
        const first = next[a];
        const second = next[b];
        const minDistance = (first.size + second.size) * 1.9 + 12;
        const dx = second.x - first.x;
        const dy = second.y - first.y;
        const distance = Math.max(Math.hypot(dx, dy), 0.01);
        if (distance >= minDistance) continue;
        const push = (minDistance - distance) / 2;
        const ux = dx / distance;
        const uy = dy / distance;
        first.x = Math.max(48, Math.min(GRAPH_WIDTH - 48, first.x - ux * push));
        first.y = Math.max(54, Math.min(GRAPH_HEIGHT - 54, first.y - uy * push));
        second.x = Math.max(48, Math.min(GRAPH_WIDTH - 48, second.x + ux * push));
        second.y = Math.max(54, Math.min(GRAPH_HEIGHT - 54, second.y + uy * push));
      }
    }
  }
  return next;
}

function metadataString(metadata: Record<string, unknown> | undefined, key: string): string | undefined {
  const value = metadata?.[key];
  return typeof value === "string" && value.trim() ? value : undefined;
}

function graphLibraryIdForNode(node: ApiKnowledgeGraphNode): string | undefined {
  return metadataString(node.metadata, "library_id") ?? (node.kind === "library" ? node.id.replace(/^library:/, "") : undefined);
}

function layoutKnowledgeGraphPayload(payload: KnowledgeGraphPayload, _settings?: KnowledgeGraphSettings): {
  nodes: KnowledgeGraphVisualNode[];
  edges: KnowledgeGraphVisualEdge[];
} {
  const centerX = GRAPH_CENTER_X;
  const centerY = GRAPH_CENTER_Y;
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
    node.x = Math.max(48, Math.min(GRAPH_WIDTH - 48, x));
    node.y = Math.max(54, Math.min(GRAPH_HEIGHT - 54, y));
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
    nodes: resolveNodeCollisions(Array.from(visualById.values())),
    edges: payload.edges.map((edge) => ({
      id: edge.id,
      from: edge.source,
      to: edge.target,
      kind: edge.kind,
      metadata: edge.metadata,
    })),
  };
}

export function KnowledgeGraphView({
  libraries,
  selectedId,
  onSelect,
  onPreviewNode,
  loading,
  graphPayload,
  minimal = false,
  resetVersion = 0,
  settings,
  scale = 1,
  onScaleChange,
}: {
  libraries: KnowledgeBaseSummary[];
  selectedId: string;
  onSelect: (id: string) => void;
  onPreviewNode?: (node: KnowledgeGraphPreviewNode) => void;
  loading: boolean;
  graphPayload: KnowledgeGraphPayload | null;
  minimal?: boolean;
  resetVersion?: number;
  settings: KnowledgeGraphSettings;
  scale?: number;
  onScaleChange?: (value: number) => void;
}) {
  const fallbackGraph = useMemo(() => buildKnowledgeGraph(libraries, settings), [libraries, settings]);
  const apiGraph = useMemo(
    () => (graphPayload ? layoutKnowledgeGraphPayload(graphPayload, settings) : null),
    [graphPayload, settings],
  );
  const { nodes, edges } = apiGraph ?? fallbackGraph;
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const libraryCount = nodes.filter((node) => node.kind === "library").length || libraries.length;
  const fileCount =
    nodes.filter((node) => node.kind === "file").length ||
    libraries.reduce((total, item) => total + (item.files?.length ?? 0), 0);
  const relatedCount = nodes.filter((node) => !["library", "file"].includes(node.kind)).length;
  const [viewTransform, setViewTransform] = useState(() => centeredTransform(scale));
  const [dragStart, setDragStart] = useState<{
    pointerX: number;
    pointerY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const activeNodeId = hoveredNodeId ?? focusedNodeId;
  const normalizedBaseScale = Math.min(MAX_GRAPH_SCALE, Math.max(MIN_GRAPH_SCALE, scale));
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
    setViewTransform(centeredTransform(normalizedBaseScale));
    setFocusedNodeId(null);
    onScaleChange?.(normalizedBaseScale);
  };

  const applyScale = (nextScale: number) => {
    const normalized = Math.min(MAX_GRAPH_SCALE, Math.max(MIN_GRAPH_SCALE, nextScale));
    setViewTransform((current) => {
      const ratio = normalized / current.scale;
      return {
        x: GRAPH_CENTER_X - (GRAPH_CENTER_X - current.x) * ratio,
        y: GRAPH_CENTER_Y - (GRAPH_CENTER_Y - current.y) * ratio,
        scale: normalized,
      };
    });
    onScaleChange?.(normalized);
  };

  useEffect(() => {
    setViewTransform(centeredTransform(normalizedBaseScale));
    setFocusedNodeId(null);
  }, [normalizedBaseScale, resetVersion]);

  useEffect(() => {
    setViewTransform((current) => {
      const normalized = Math.min(MAX_GRAPH_SCALE, Math.max(MIN_GRAPH_SCALE, scale));
      const ratio = normalized / current.scale;
      return {
        x: GRAPH_CENTER_X - (GRAPH_CENTER_X - current.x) * ratio,
        y: GRAPH_CENTER_Y - (GRAPH_CENTER_Y - current.y) * ratio,
        scale: normalized,
      };
    });
  }, [scale]);

  const handleGraphWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const direction = event.deltaY > 0 ? -1 : 1;
    applyScale(viewTransform.scale + direction * 0.12);
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
    <div className={cn("relative min-h-[620px] overflow-hidden bg-white", minimal ? "rounded-none border-0 shadow-none" : "rounded-lg border border-slate-200 shadow-[0_18px_50px_rgba(15,23,42,0.08)]")}>
      {!minimal ? <div className="absolute inset-x-0 top-0 z-10 flex h-10 items-center justify-center border-b border-slate-200/80 bg-white/88 text-[12px] text-slate-500 backdrop-blur">
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
      </div> : null}

      <svg
        viewBox="0 0 1160 640"
        role="img"
        aria-label="知识花园图谱"
        className={cn(minimal ? "h-full min-h-[720px] w-full touch-none" : "h-[clamp(620px,72vh,820px)] w-full touch-none", dragStart ? "cursor-grabbing" : "cursor-grab")}
        onWheel={handleGraphWheel}
        onPointerDown={handleGraphPointerDown}
        onPointerMove={handleGraphPointerMove}
        onPointerUp={handleGraphPointerUp}
        onPointerLeave={handleGraphPointerUp}
      >
        <rect width="1160" height="640" fill="#FFFFFF" />
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
                strokeWidth={(active ? (edge.kind === "contains" ? 0.85 : 0.65) : 0.35) * settings.edgeWidth}
                opacity={active ? 1 : 0.16}
                strokeLinecap="round"
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
                  onPreviewNode?.({ id: node.id, label: node.label, kind: node.kind, metadata: node.metadata, libraryId: node.libraryId });
                }}
                className="cursor-pointer"
              >
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={(node.size + (focused ? 1.6 : selected ? 1 : 0)) * settings.nodeScale}
                  fill={fill}
                  opacity={graphActive ? 0.96 : 0.28}
                  stroke={
                    selected || focused
                      ? node.kind === "library"
                        ? "rgba(17,24,39,0.18)"
                        : "rgba(15,23,42,0.16)"
                      : "rgba(255,255,255,0.78)"
                  }
                  strokeWidth={selected || focused ? 2 : 0.5}
                />
                {settings.showLabels ? (
                  <text
                    x={node.x}
                    y={labelY + (settings.nodeScale - 1) * node.size}
                    textAnchor="middle"
                    pointerEvents="none"
                    opacity={settings.labelOpacity}
                    style={{
                      fill:
                        focused && node.kind === "library"
                          ? "#111827"
                          : focused
                            ? "#374151"
                            : graphActive
                              ? node.kind === "library"
                                ? "#111827"
                                : "#6b7280"
                              : "#d1d5db",
                      fontSize: node.kind === "library" ? 10.5 : 8.6,
                      fontWeight: focused || node.kind === "library" ? 560 : 430,
                      letterSpacing: 0,
                    }}
                  >
                    {graphNodeLabel(node.label, node.kind)}
                  </text>
                ) : null}
              </g>
            );
          })}
        </g>
      </svg>

    </div>
  );
}
