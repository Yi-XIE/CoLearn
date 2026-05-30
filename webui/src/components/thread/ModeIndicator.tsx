import { useEffect, useState } from "react";
import { BookOpen, MessageCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ModeIndicatorProps {
  mode: "chat" | "learning" | undefined;
  learningPhase?: string;
  onToggleMode?: () => void;
}

const PHASE_LABELS: Record<string, string> = {
  intake: "引导中",
  diagnose: "诊断中",
  ready: "",
  reflect: "总结中",
  recall: "复习中",
};

export function ModeIndicator({ mode, learningPhase, onToggleMode }: ModeIndicatorProps) {
  const isLearning = mode === "learning";
  const phaseLabel = learningPhase ? PHASE_LABELS[learningPhase] || "" : "";

  return (
    <button
      type="button"
      onClick={onToggleMode}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
        isLearning
          ? "bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50"
          : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700",
      )}
      title={isLearning ? "切换到聊天模式" : "切换到学习模式"}
    >
      {isLearning ? (
        <BookOpen className="h-3 w-3" />
      ) : (
        <MessageCircle className="h-3 w-3" />
      )}
      <span>{isLearning ? "学习" : "聊天"}</span>
      {phaseLabel && (
        <span className="ml-0.5 text-xs opacity-75">· {phaseLabel}</span>
      )}
    </button>
  );
}

interface LightRAGHealthBannerProps {
  apiBase?: string;
}

type HealthStatus = "healthy" | "disabled" | "unreachable" | "unavailable" | "loading";

export function LightRAGHealthBanner({ apiBase = "" }: LightRAGHealthBannerProps) {
  const [status, setStatus] = useState<HealthStatus>("loading");

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const res = await fetch(`${apiBase}/api/v1/system/lightrag-health`);
        if (!res.ok) {
          if (!cancelled) setStatus("unavailable");
          return;
        }
        const data = await res.json();
        if (!cancelled) setStatus(data.status || "unavailable");
      } catch {
        if (!cancelled) setStatus("unreachable");
      }
    }
    check();
    const interval = setInterval(check, 60_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [apiBase]);

  if (status === "healthy" || status === "loading") return null;

  return (
    <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
      <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
      <span>
        {status === "disabled"
          ? "知识检索已禁用 — 回答将基于通用知识"
          : "知识检索不可用 — 请检查 LightRAG 服务"}
      </span>
    </div>
  );
}
