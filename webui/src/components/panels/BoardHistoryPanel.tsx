import { useCallback, useEffect, useState } from "react";
import { Clock, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { fetchBoardHistory, type BoardHistoryEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

import { PanelView, type PanelShellProps } from "./PanelView";

interface BoardHistoryPanelProps extends PanelShellProps {
  sessionId: string;
  token: string;
}

export function BoardHistoryPanel({ sessionId, token, ...shellProps }: BoardHistoryPanelProps) {
  const [history, setHistory] = useState<BoardHistoryEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    if (!sessionId || !token) return;
    setLoading(true);
    setError(null);
    try {
      const events = await fetchBoardHistory(token, sessionId);
      setHistory(events);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [sessionId, token]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  return (
    <PanelView {...shellProps}>
      <div className="flex flex-col gap-4 p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-sans text-[15px] font-semibold text-foreground/92">
            学习状态演化历史
          </h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={loadHistory}
            disabled={loading}
            className="h-7 px-2"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Clock className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {!loading && history.length === 0 && (
          <p className="text-sm text-muted-foreground">暂无状态快照记录</p>
        )}

        <div className="flex flex-col gap-2">
          {history.map((event) => (
            <EventCard key={event.event_id} event={event} />
          ))}
        </div>
      </div>
    </PanelView>
  );
}

function EventCard({ event }: { event: BoardHistoryEvent }) {
  const isDerived = event.kind === "board_snapshot_derived";
  const isFailed = event.kind === "board_snapshot_failed";
  const isPatched = event.kind === "board_patch_applied";

  const changes = (event.payload.changes as Record<string, unknown>) ?? {};
  const changeKeys = Object.keys(changes);

  return (
    <div
      className={cn(
        "rounded-lg border p-3 text-sm",
        isDerived && "border-green-200/60 bg-green-50/40 dark:border-green-900/40 dark:bg-green-950/20",
        isFailed && "border-red-200/60 bg-red-50/40 dark:border-red-900/40 dark:bg-red-950/20",
        isPatched && "border-blue-200/60 bg-blue-50/40 dark:border-blue-900/40 dark:bg-blue-950/20",
      )}
    >
      <div className="flex items-start gap-2">
        {isDerived && <CheckCircle2 className="mt-0.5 h-4 w-4 text-green-600 dark:text-green-400" />}
        {isFailed && <AlertCircle className="mt-0.5 h-4 w-4 text-red-600 dark:text-red-400" />}
        {isPatched && <Clock className="mt-0.5 h-4 w-4 text-blue-600 dark:text-blue-400" />}

        <div className="flex-1">
          <div className="font-medium">
            {isDerived && "LLM 重新推导快照"}
            {isFailed && "快照推导失败"}
            {isPatched && "即时状态更新"}
          </div>

          {isDerived && changeKeys.length > 0 && (
            <div className="mt-2 space-y-1 text-xs text-muted-foreground">
              {changeKeys.map((key) => (
                <div key={key} className="font-mono">
                  {key}: {JSON.stringify(changes[key])}
                </div>
              ))}
            </div>
          )}

          {isDerived && (
            <div className="mt-1 text-xs text-muted-foreground">
              基于 {event.payload.event_count} 个事件
            </div>
          )}

          {isFailed && event.payload.error && (
            <div className="mt-1 text-xs text-red-600 dark:text-red-400">
              {String(event.payload.error)}
            </div>
          )}

          {isPatched && event.payload.patch_keys && (
            <div className="mt-1 text-xs text-muted-foreground">
              更新字段: {(event.payload.patch_keys as string[]).join(", ")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
