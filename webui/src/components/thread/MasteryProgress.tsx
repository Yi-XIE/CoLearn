import { TrendingUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

interface MasteryProgressProps {
  level: number;
  completedNodes?: number;
  totalNodes?: number;
  className?: string;
}

export function MasteryProgress({ level, completedNodes, totalNodes, className }: MasteryProgressProps) {
  const { t } = useTranslation();
  const percent = Math.round(Math.min(1, Math.max(0, level)) * 100);

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div className="flex-1">
        <div className="mb-1 flex items-center justify-between">
          <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-600 dark:text-gray-400">
            <TrendingUp className="h-3 w-3" />
            {t("learning.mastery.label")}
          </span>
          <span className="text-xs font-semibold text-gray-800 dark:text-gray-200">
            {percent}%
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
          <div
            className="h-full rounded-full bg-gradient-to-r from-blue-400 to-indigo-500 transition-all duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>
      {totalNodes != null && totalNodes > 0 && (
        <span className="whitespace-nowrap text-xs text-gray-500 dark:text-gray-500">
          {t("learning.mastery.nodes", { completed: completedNodes ?? 0, total: totalNodes })}
        </span>
      )}
    </div>
  );
}
