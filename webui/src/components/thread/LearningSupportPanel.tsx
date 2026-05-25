import { AlertTriangle, Link2, Search, Target } from "lucide-react";

import { EmptyHint, InfoCard } from "@/components/panels/knowledge/KnowledgePanelPrimitives";
import type { LearningSupportItem, LearningSupportPayload } from "@/lib/types";
import { cn } from "@/lib/utils";

interface LearningSupportPanelProps {
  support: LearningSupportPayload | null;
  focusLabel?: string | null;
}

function itemSource(item: LearningSupportItem): string {
  const raw = item.title || item.source_ref || item.source_path || "资料来源";
  return raw.split(/[\\/]/).filter(Boolean).pop() || raw;
}

function itemTarget(item: LearningSupportItem): string {
  return item.target_label || item.target_id || item.target_type || "当前学习目标";
}

function itemSummary(item: LearningSupportItem): string {
  return item.summary || item.support_reason || itemSource(item);
}

function supportTypeLabel(value?: string): string {
  const labels: Record<string, string> = {
    definition: "定义",
    prerequisite: "先修",
    example: "例子",
    counterexample: "反例",
    procedure: "步骤",
    reference: "依据",
    extension: "拓展",
    comparison: "对照",
  };

  return labels[String(value || "")] || "资料";
}

function nextRetrievalHint(support: LearningSupportPayload | null): string {
  const continuation = support?.continuation_retrieval_hint ?? {};
  const continuationQuery = continuation.retrieval_query_context as Record<string, unknown> | undefined;
  const ownQuery = support?.retrieval_query_context ?? {};
  const finalQuery = String(
    continuationQuery?.final_query
      ?? ownQuery.final_query
      ?? continuationQuery?.default_query
      ?? ownQuery.default_query
      ?? "",
  ).trim();

  return finalQuery;
}

function modeLabel(value?: string): string {
  const mode = String(value || "").toUpperCase();
  if (mode === "LEARN" || mode === "CHECK" || mode === "PAUSED") return mode;
  return "";
}

function countLabel(label: string, value: number): string {
  return `${label} ${value}`;
}

function isStaleProfileGoal(value: string): boolean {
  const text = value.trim();
  if (!text) return false;
  return text.length > 48 || /我是\s*Yi|colearn|AI产品经理|理想化产品/i.test(text);
}

function compactText(value: string, max = 44): string {
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

export function LearningSupportPanel({ support, focusLabel }: LearningSupportPanelProps) {
  const items = support?.prompt_support_bundle?.length
    ? support.prompt_support_bundle
    : support?.retrieval_hits ?? [];
  const visibleItems = items.slice(0, 4);
  const misses = support?.retrieval_misses ?? [];
  const nextHint = nextRetrievalHint(support);
  const plan = support?.learning_plan;
  const board = support?.learning_board;
  const mode = modeLabel(support?.turn_mode);
  const currentNode = plan?.plan_nodes?.find((node) => node.id === plan.current_node_id);
  const rawGoal = plan?.goal?.trim() ?? "";
  const goal = focusLabel?.trim() || (isStaleProfileGoal(rawGoal) ? "" : rawGoal);
  const currentProgress = board?.current_progress?.trim() || currentNode?.label?.trim();
  const completedCount = board?.completed_nodes?.length ?? 0;
  const pendingChecks = plan?.pending_checks?.length ?? 0;
  const blockerCount = (board?.blockers?.length ?? 0) + (board?.objections?.length ?? 0);
  const hasBoardSummary = Boolean(goal || currentProgress || completedCount || pendingChecks || blockerCount);

  if (visibleItems.length === 0 && misses.length === 0 && !nextHint && !hasBoardSummary) return null;

  return (
    <aside aria-label="本轮参考依据" className="mb-3 min-w-0 max-w-full space-y-3 overflow-hidden px-3 py-2.5 text-sm text-muted-foreground">
      <InfoCard
        title="本轮依据"
        actions={
          <div className="flex shrink-0 items-center gap-2 text-sm text-muted-foreground">
            {mode ? (
              <span className="rounded-md border border-border/70 px-1.5 py-0.5 font-medium text-foreground/80">
                {mode}
              </span>
            ) : null}
            <span className="tabular-nums">{visibleItems.length} 条资料</span>
          </div>
        }
        body={
          <div className="space-y-3">
            {hasBoardSummary ? (
              <div className="min-w-0">
                {goal ? (
                  <div className="whitespace-normal break-words text-sm font-medium text-foreground/90">
                    目标：{compactText(goal)}
                  </div>
                ) : null}
                {currentProgress ? (
                  <div className="mt-1 flex min-w-0 items-start gap-1.5 text-sm text-muted-foreground">
                    <Target className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    <span className="min-w-0 whitespace-normal break-words">{compactText(currentProgress)}</span>
                  </div>
                ) : null}
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                  <span className="rounded-md border border-border/55 bg-muted/25 px-2 py-1">
                    {countLabel("已完成", completedCount)}
                  </span>
                  <span className="rounded-md border border-border/55 bg-muted/25 px-2 py-1">
                    {countLabel("待检查", pendingChecks)}
                  </span>
                  <span className="rounded-md border border-border/55 bg-muted/25 px-2 py-1">
                    {countLabel("阻塞", blockerCount)}
                  </span>
                </div>
              </div>
            ) : null}

            {visibleItems.length > 0 ? (
              <div className="space-y-2">
                {visibleItems.map((item, index) => (
                  <div
                    key={`${item.source_ref || item.source_path || "source"}-${item.chunk_id || index}`}
                    className="min-w-0 rounded-xl border border-border/60 bg-background/72 px-3 py-2.5"
                  >
                    <div className="mb-1 flex min-w-0 items-center gap-1.5">
                      <span className="shrink-0 rounded-md bg-foreground px-1.5 py-0.5 text-xs font-medium text-background">
                        {supportTypeLabel(item.support_type)}
                      </span>
                      <span className="min-w-0 whitespace-normal break-words text-sm text-muted-foreground">
                        {itemSource(item)}
                      </span>
                    </div>
                    <p className="text-sm leading-5 text-foreground/88">
                      {itemSummary(item)}
                    </p>
                    <div className="mt-1.5 flex min-w-0 items-start gap-1.5 text-sm">
                      <Target className="h-3 w-3 shrink-0" aria-hidden />
                      <span className="min-w-0 whitespace-normal break-words">{itemTarget(item)}</span>
                      {item.chunk_id ? (
                        <>
                          <Link2 className="ml-auto h-3 w-3 shrink-0" aria-hidden />
                          <span className="max-w-[7rem] break-words tabular-nums">{item.chunk_id}</span>
                        </>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyHint text="这一轮没有命中可展示的资料片段。" />
            )}
          </div>
        }
      />

      {misses.length > 0 ? (
        <InfoCard
          title="资料缺口"
          body={
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-1 h-4 w-4 shrink-0 text-foreground/70" aria-hidden />
              <span>仍有 {misses.length} 个资料缺口，下一轮会继续补证据。</span>
            </div>
          }
        />
      ) : null}

      {nextHint ? (
        <InfoCard
          title="下轮检索"
          body={
            <div className="flex items-start gap-2">
              <Search className="mt-1 h-4 w-4 shrink-0 text-foreground/70" aria-hidden />
              <span className={cn("min-w-0 whitespace-normal break-words", focusLabel && isStaleProfileGoal(nextHint) && "text-muted-foreground/70")}>
                {focusLabel && isStaleProfileGoal(nextHint)
                  ? `围绕“${compactText(focusLabel, 28)}”继续补资料依据。`
                  : `继续检索：${compactText(nextHint, 72)}`}
              </span>
            </div>
          }
        />
      ) : null}
    </aside>
  );
}
