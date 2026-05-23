import { AlertTriangle, BookOpenCheck, Link2, Search, Target } from "lucide-react";

import type { LucideIcon } from "lucide-react";

import type { LearningSupportItem, LearningSupportPayload } from "@/lib/types";
import { cn } from "@/lib/utils";

interface LearningSupportPanelProps {
  support: LearningSupportPayload | null;
}

interface LearningSupportNotice {
  key: string;
  title: string;
  body: string;
  icon: LucideIcon;
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

export function LearningSupportPanel({ support }: LearningSupportPanelProps) {
  const items = support?.prompt_support_bundle?.length
    ? support.prompt_support_bundle
    : support?.retrieval_hits ?? [];
  const visibleItems = items.slice(0, 4);
  const misses = support?.retrieval_misses ?? [];
  const nextHint = nextRetrievalHint(support);
  const notices: LearningSupportNotice[] = [];

  if (misses.length > 0) {
    notices.push({
      key: "retrieval-miss",
      title: "资料补证提醒",
      body: `仍有 ${misses.length} 个资料缺口，下一轮会继续补证据。`,
      icon: AlertTriangle,
    });
  }

  if (nextHint) {
    notices.push({
      key: "next-retrieval-plan",
      title: "下一轮计划",
      body: `继续检索：${nextHint}`,
      icon: Search,
    });
  }

  if (visibleItems.length === 0 && notices.length === 0) return null;

  return (
    <aside
      aria-label="本轮参考依据"
      className={cn(
        "mb-3 px-3 py-2.5",
        "text-[12px] text-muted-foreground",
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 font-medium text-foreground">
          <BookOpenCheck className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="truncate">本轮依据</span>
        </div>
        <div className="shrink-0 text-[11px] tabular-nums">
          {visibleItems.length} 条资料
        </div>
      </div>

      {visibleItems.length > 0 ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {visibleItems.map((item, index) => (
            <div
              key={`${item.source_ref || item.source_path || "source"}-${item.chunk_id || index}`}
              className="min-w-0 rounded-md border border-border/70 bg-background/70 px-2.5 py-2"
            >
              <div className="mb-1 flex min-w-0 items-center gap-1.5">
                <span className="shrink-0 rounded-sm bg-foreground px-1.5 py-0.5 text-[10px] font-medium text-background">
                  {supportTypeLabel(item.support_type)}
                </span>
                <span className="min-w-0 truncate text-[11px] text-muted-foreground">
                  {itemSource(item)}
                </span>
              </div>
              <p className="line-clamp-2 text-[12px] leading-5 text-foreground/88">
                {itemSummary(item)}
              </p>
              <div className="mt-1.5 flex min-w-0 items-center gap-1.5 text-[11px]">
                <Target className="h-3 w-3 shrink-0" aria-hidden />
                <span className="min-w-0 truncate">{itemTarget(item)}</span>
                {item.chunk_id ? (
                  <>
                    <Link2 className="ml-auto h-3 w-3 shrink-0" aria-hidden />
                    <span className="max-w-[7rem] truncate tabular-nums">{item.chunk_id}</span>
                  </>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {notices.length > 0 ? (
        <div className="mt-2 space-y-2">
          {notices.map((notice) => {
            const Icon = notice.icon;

            return (
              <div
                key={notice.key}
                className="rounded-lg border border-border/60 bg-background/88 px-3 py-2.5 shadow-sm"
              >
                <div className="flex items-start gap-2">
                  <div className="mt-0.5 rounded-md border border-border/50 bg-muted/35 p-1 text-foreground/75">
                    <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] font-medium text-foreground/88">{notice.title}</div>
                    <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-muted-foreground">
                      {notice.body}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </aside>
  );
}
