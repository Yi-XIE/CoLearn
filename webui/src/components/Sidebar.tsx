import { useMemo, useState } from "react";
import {
  Brain,
  Compass,
  Flower2,
  Menu,
  Search,
  Settings,
  Sparkles,
  SquarePen,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { ChatList } from "@/components/ChatList";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChatSummary } from "@/lib/types";

interface SidebarProps {
  activeView: "chat" | "knowledge" | "memory" | "skills" | "settings";
  sessions: ChatSummary[];
  activeKey: string | null;
  loading: boolean;
  onOpenKnowledge: () => void;
  onOpenMemory: () => void;
  onOpenSkills: () => void;
  onNewChat: () => void;
  onSelect: (key: string) => void;
  onRequestDelete: (key: string, label: string) => void;
  onOpenSettings: () => void;
  onCollapse: () => void;
}

export function Sidebar(props: SidebarProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const filteredSessions = useMemo(() => {
    if (!normalizedQuery) return props.sessions;
    const terms = normalizedQuery.split(/\s+/).filter(Boolean);
    return props.sessions.filter((session) => {
      const haystack = [
        session.title,
        session.preview,
        session.chatId,
        session.channel,
        session.key,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return terms.every((term) => haystack.includes(term));
    });
  }, [normalizedQuery, props.sessions]);

  const navItems = [
    { key: "knowledge", label: "知识花园", icon: Flower2, onClick: props.onOpenKnowledge },
    { key: "memory", label: "记忆", icon: Brain, onClick: props.onOpenMemory },
    { key: "skills", label: "技能", icon: Sparkles, onClick: props.onOpenSkills },
  ] as const;

  return (
    <nav
      aria-label={t("sidebar.navigation")}
      className="flex h-full w-full min-w-0 flex-col border-r border-sidebar-border/60 bg-sidebar text-sidebar-foreground"
    >
      <div className="flex items-center justify-between px-3 pb-2.5 pt-3">
        <div className="flex min-w-0 items-center gap-2">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-sidebar-accent/80 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.18)]">
            <Compass className="h-4 w-4 text-sidebar-foreground" />
          </div>
          <div className="truncate text-[15px] font-semibold tracking-tight text-sidebar-foreground">
            CoLearn
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("sidebar.collapse")}
          onClick={props.onCollapse}
          className="h-7 w-7 rounded-lg text-muted-foreground/85 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground"
        >
          <Menu className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="space-y-1 px-2 pb-2">
        <label className="relative block">
          <span className="sr-only">{t("sidebar.searchAria")}</span>
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/70"
            aria-hidden
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("sidebar.searchPlaceholder")}
            aria-label={t("sidebar.searchAria")}
            className={cn(
              "h-8 w-full rounded-full border border-transparent bg-sidebar-accent/45",
              "pl-8 pr-3 text-[12.5px] text-sidebar-foreground outline-none",
              "placeholder:text-muted-foreground/75",
              "transition-colors hover:bg-sidebar-accent/65",
              "focus:border-sidebar-border/80 focus:bg-sidebar-accent/70",
              "focus:ring-1 focus:ring-sidebar-border/70",
            )}
          />
        </label>
        <Button
          onClick={props.onNewChat}
          className="h-8 w-full justify-start gap-2 rounded-full px-3 text-[12.5px] font-medium leading-none text-sidebar-foreground/92 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground"
          variant="ghost"
        >
          <SquarePen className="h-3.5 w-3.5" />
          {t("sidebar.newChat")}
        </Button>
        <div className="space-y-1">
          {navItems.map(({ key, label, icon: Icon, onClick }) => {
            const active = props.activeView === key;
            return (
              <Button
                key={key}
                type="button"
                variant="ghost"
                onClick={onClick}
                className={cn(
                  "h-8 w-full justify-start gap-2 rounded-full px-3 text-[12.5px] font-medium",
                  active
                    ? "bg-sidebar-accent/80 text-sidebar-foreground"
                    : "text-sidebar-foreground/82 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground",
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </Button>
            );
          })}
        </div>
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <ChatList
          sessions={filteredSessions}
          activeKey={props.activeKey}
          loading={props.loading}
          emptyLabel={
            normalizedQuery ? t("sidebar.noSearchResults") : t("chat.noSessions")
          }
          onSelect={props.onSelect}
          onRequestDelete={props.onRequestDelete}
        />
      </div>
      <div className="space-y-1 px-2.5 py-2.5 text-xs">
        <Button
          type="button"
          variant="ghost"
          onClick={props.onOpenSettings}
          className="h-8 w-full justify-start gap-2 rounded-full px-2.5 text-[12.5px] font-medium text-sidebar-foreground/85 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground"
        >
          <Settings className="h-3.5 w-3.5" aria-hidden />
          {t("sidebar.settings")}
        </Button>
      </div>
    </nav>
  );
}
