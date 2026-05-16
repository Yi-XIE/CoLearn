"use client";

import { memo } from "react";
import { Brain } from "lucide-react";
import { useTranslation } from "react-i18next";

type SelectableProjectKey = "memory";

export interface ChatProjectSelectionCounts {
  memory: number;
}

interface ChatProjectMenuProps {
  variant: "toolbar" | "mention";
  selectedCounts: ChatProjectSelectionCounts;
  onSelectItem: (key: SelectableProjectKey) => void;
}

const ITEMS: Array<{
  key: SelectableProjectKey;
  label: string;
  description: string;
  icon: typeof Brain;
}> = [
  {
    key: "memory",
    label: "Memory",
    description: "Attach the learner memory relevant to this turn.",
    icon: Brain,
  },
];

export default memo(function ChatProjectMenu({
  variant,
  selectedCounts,
  onSelectItem,
}: ChatProjectMenuProps) {
  const { t } = useTranslation();
  const compact = variant === "toolbar";

  return (
    <div
      className={`rounded-xl border border-[var(--border)] bg-[var(--popover)] shadow-lg backdrop-blur-md ${
        compact ? "w-[260px] py-1.5" : "w-64 p-2"
      }`}
    >
      <div className={compact ? "space-y-0.5" : "space-y-1"}>
        {ITEMS.map(({ key, label, description, icon: Icon }) => {
          const count = selectedCounts.memory;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onSelectItem(key)}
              className={`flex w-full items-center gap-2.5 text-left transition-colors hover:bg-[var(--muted)]/40 ${
                compact
                  ? "px-3 py-1.5 text-[12px]"
                  : "rounded-xl px-3 py-2.5 text-[13px]"
              }`}
            >
              <Icon
                size={compact ? 13 : 14}
                strokeWidth={1.7}
                className="shrink-0 text-[var(--muted-foreground)]"
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-[var(--foreground)]">
                  {t(label)}
                </span>
                {!compact && (
                  <span className="mt-0.5 block truncate text-[11px] text-[var(--muted-foreground)]">
                    {t(description)}
                  </span>
                )}
              </span>
              {count > 0 && (
                <span className="rounded-full bg-[var(--primary)]/10 px-1.5 py-px text-[9px] font-semibold text-[var(--primary)]">
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
});
