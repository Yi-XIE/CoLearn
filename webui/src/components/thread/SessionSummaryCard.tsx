import { CheckCircle2, AlertCircle, ArrowRight, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

interface SessionSummaryCardProps {
  summary: {
    topics_covered?: string[];
    concepts_mastered?: string[];
    concepts_blocked?: string[];
    duration_minutes?: number;
    next_focus?: string;
  };
  className?: string;
}

export function SessionSummaryCard({ summary, className }: SessionSummaryCardProps) {
  const { topics_covered, concepts_mastered, concepts_blocked, duration_minutes, next_focus } = summary;

  if (!topics_covered?.length && !concepts_mastered?.length && !concepts_blocked?.length) {
    return null;
  }

  return (
    <div className={cn(
      "rounded-lg border border-blue-100 bg-gradient-to-br from-blue-50 to-indigo-50 p-4 dark:border-blue-900/40 dark:from-blue-950/20 dark:to-indigo-950/20",
      className,
    )}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-blue-900 dark:text-blue-200">
          本次学习总结
        </h3>
        {duration_minutes != null && duration_minutes > 0 && (
          <span className="inline-flex items-center gap-1 text-xs text-blue-600/70 dark:text-blue-400/70">
            <Clock className="h-3 w-3" />
            {duration_minutes} 分钟
          </span>
        )}
      </div>

      {topics_covered && topics_covered.length > 0 && (
        <div className="mb-2">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">学习内容</span>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {topics_covered.map((topic) => (
              <span key={topic} className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                {topic}
              </span>
            ))}
          </div>
        </div>
      )}

      {concepts_mastered && concepts_mastered.length > 0 && (
        <div className="mb-2">
          <span className="inline-flex items-center gap-1 text-xs font-medium text-green-600 dark:text-green-400">
            <CheckCircle2 className="h-3 w-3" /> 已掌握
          </span>
          <ul className="mt-1 space-y-0.5">
            {concepts_mastered.map((c) => (
              <li key={c} className="text-xs text-gray-700 dark:text-gray-300">• {c}</li>
            ))}
          </ul>
        </div>
      )}

      {concepts_blocked && concepts_blocked.length > 0 && (
        <div className="mb-2">
          <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-600 dark:text-amber-400">
            <AlertCircle className="h-3 w-3" /> 需要巩固
          </span>
          <ul className="mt-1 space-y-0.5">
            {concepts_blocked.map((c) => (
              <li key={c} className="text-xs text-gray-700 dark:text-gray-300">• {c}</li>
            ))}
          </ul>
        </div>
      )}

      {next_focus && (
        <div className="mt-3 flex items-center gap-1.5 rounded-md bg-white/60 px-2.5 py-1.5 text-xs text-indigo-700 dark:bg-white/5 dark:text-indigo-300">
          <ArrowRight className="h-3 w-3" />
          <span>下次重点：{next_focus}</span>
        </div>
      )}
    </div>
  );
}
