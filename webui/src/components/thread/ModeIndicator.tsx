import { useEffect, useState } from "react";
import { BookOpen, MessageCircle, AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

interface ModeIndicatorProps {
  mode: "chat" | "learning" | undefined;
  learningPhase?: string;
  onToggleMode?: () => void;
}

export function ModeIndicator({ mode, learningPhase, onToggleMode }: ModeIndicatorProps) {
  const { t } = useTranslation();
  const isLearning = mode === "learning";
  const phaseLabel = learningPhase
    ? t(`learning.mode.phase.${learningPhase}`, { defaultValue: "" })
    : "";
  const interactive = typeof onToggleMode === "function";

  const className = cn(
    "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
    isLearning
      ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
      : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
    interactive &&
      (isLearning
        ? "hover:bg-blue-200 dark:hover:bg-blue-900/50"
        : "hover:bg-gray-200 dark:hover:bg-gray-700"),
  );

  const content = (
    <>
      {isLearning ? (
        <BookOpen className="h-3 w-3" />
      ) : (
        <MessageCircle className="h-3 w-3" />
      )}
      <span>{isLearning ? t("learning.mode.learning") : t("learning.mode.chat")}</span>
      {phaseLabel && (
        <span className="ml-0.5 text-xs opacity-75">· {phaseLabel}</span>
      )}
    </>
  );

  if (!interactive) {
    return <span className={className}>{content}</span>;
  }

  return (
    <button
      type="button"
      onClick={onToggleMode}
      className={className}
      title={isLearning ? t("learning.mode.switchToChat") : t("learning.mode.switchToLearning")}
    >
      {content}
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
