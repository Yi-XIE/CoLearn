import type { ReactNode } from "react";

import { ThreadHeader } from "@/components/thread/ThreadHeader";

export interface PanelViewProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  onToggleSidebar: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideSidebarToggleOnDesktop?: boolean;
}

export type PanelShellProps = Omit<PanelViewProps, "title" | "subtitle" | "children">;

export function PanelView({
  title,
  subtitle,
  children,
  onToggleSidebar,
  theme,
  onToggleTheme,
  hideSidebarToggleOnDesktop,
}: PanelViewProps) {
  return (
    <section className="absolute inset-0 flex min-h-0 flex-1 flex-col overflow-hidden">
      <ThreadHeader
        title={title}
        subtitle={subtitle}
        onToggleSidebar={onToggleSidebar}
        theme={theme}
        onToggleTheme={onToggleTheme}
        hideSidebarToggleOnDesktop={hideSidebarToggleOnDesktop}
        titleStyle="page"
      />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto flex max-w-5xl flex-col gap-4">{children}</div>
      </div>
    </section>
  );
}
