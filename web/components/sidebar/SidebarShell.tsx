"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode } from "react";
import {
  BookOpen,
  Brain,
  ChevronDown,
  ChevronRight,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import SessionList from "@/components/SessionList";
import { Tooltip } from "@/components/ui/Tooltip";
import { useAppShell } from "@/context/AppShellContext";
import type { SessionSummary } from "@/lib/session-api";

interface NavEntry {
  href: string;
  label: string;
  icon: LucideIcon;
  tooltipKey?: string;
}

const PRIMARY_NAV: NavEntry[] = [
  {
    href: "/knowledge",
    label: "知识花园",
    icon: BookOpen,
    tooltipKey: "Knowledge tooltip",
  },
  { href: "/memory", label: "Memory", icon: Brain, tooltipKey: "Memory" },
  {
    href: "/chat",
    label: "Chat",
    icon: MessageSquare,
    tooltipKey: "Chat tooltip",
  },
];

const DEFAULT_SESSION_VIEWPORT_CLASS_NAME = "";

interface SidebarShellProps {
  sessions?: SessionSummary[];
  activeSessionId?: string | null;
  loadingSessions?: boolean;
  showSessions?: boolean;
  sessionViewportClassName?: string;
  onNewChat?: () => void;
  onSelectSession?: (sessionId: string) => void | Promise<void>;
  onRenameSession?: (sessionId: string, title: string) => void | Promise<void>;
  onDeleteSession?: (sessionId: string) => void | Promise<void>;
  footerSlot?: ReactNode;
}

export function SidebarShell({
  sessions = [],
  activeSessionId = null,
  loadingSessions = false,
  showSessions = false,
  sessionViewportClassName = DEFAULT_SESSION_VIEWPORT_CLASS_NAME,
  onNewChat,
  onSelectSession,
  onRenameSession,
  onDeleteSession,
  footerSlot,
}: SidebarShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useTranslation();
  const appName = t("CoLearn");
  const {
    sidebarCollapsed: collapsed,
    setSidebarCollapsed: setCollapsed,
    setActiveSessionId,
    chatSessionsOpen,
    setChatSessionsOpen,
  } = useAppShell();
  const chatSessionsVisible = chatSessionsOpen;

  const handleNewChat = () => {
    if (onNewChat) {
      onNewChat();
      return;
    }

    router.push("/chat");
  };

  if (collapsed) {
    return (
      <aside className="group/sb relative flex h-screen w-[60px] shrink-0 flex-col items-center bg-[var(--secondary)] py-3 transition-all duration-200">
        <div className="relative mb-2 flex h-9 w-9 items-center justify-center">
          <Link
            href="/"
            aria-label={appName}
            className="flex items-center justify-center transition-opacity duration-150 group-hover/sb:opacity-0"
          >
            <Image
              src="/logo-ver2.png"
              alt={appName}
              width={24}
              height={24}
              className="h-[24px] w-[24px] rounded-md object-cover"
            />
          </Link>
          <button
            onClick={() => setCollapsed(false)}
            className="absolute inset-0 flex items-center justify-center rounded-lg text-[var(--muted-foreground)] opacity-0 transition-all duration-150 hover:bg-[var(--background)]/60 hover:text-[var(--foreground)] group-hover/sb:opacity-100"
            aria-label={t("Expand sidebar")}
          >
            <PanelLeftOpen size={16} />
          </button>
        </div>

        <button
          onClick={handleNewChat}
          title={t("New Session") as string}
          className="mb-2 flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--border)]/50 bg-[var(--background)]/40 text-[var(--foreground)] shadow-sm transition-all duration-150 hover:border-[var(--border)] hover:bg-[var(--background)]/80"
          aria-label={t("New Session")}
        >
          <Plus size={16} strokeWidth={2.2} />
        </button>

        <div className="my-1.5 h-px w-7 bg-[var(--border)]/40" />

        <nav className="flex w-full flex-col items-center gap-1 px-1.5">
          {PRIMARY_NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            const description = item.tooltipKey
              ? t(item.tooltipKey)
              : undefined;

            return (
              <Tooltip
                key={item.href}
                label={t(item.label)}
                description={description}
                side="right"
              >
                <Link
                  href={item.href}
                  aria-label={t(item.label)}
                  className={`relative flex h-9 w-9 items-center justify-center rounded-xl transition-all duration-150 ${
                    active
                      ? "bg-[var(--background)]/80 text-[var(--foreground)] shadow-sm"
                      : "text-[var(--muted-foreground)] hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
                  }`}
                >
                  {active && (
                    <span className="absolute -left-1.5 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-[var(--foreground)]/80" />
                  )}
                  <item.icon size={18} strokeWidth={active ? 2 : 1.6} />
                </Link>
              </Tooltip>
            );
          })}
        </nav>

        <div className="flex-1" />

        <div className="flex w-full flex-col items-center gap-1 px-1.5">
          <div className="my-1 h-px w-7 bg-[var(--border)]/40" />
          {footerSlot}
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex h-screen min-h-0 w-[260px] shrink-0 flex-col bg-[var(--secondary)] transition-all duration-200">
      <div className="flex h-14 items-center justify-between px-4">
        <Link href="/" className="group flex items-center gap-2">
          <Image
            src="/logo-ver2.png"
            alt={appName}
            width={24}
            height={24}
            className="h-[24px] w-[24px] rounded-md object-cover transition-transform duration-200 group-hover:scale-105"
          />
          <span className="text-[16px] font-semibold leading-none tracking-[-0.02em] text-[var(--foreground)]">
            {appName}
          </span>
        </Link>
        <button
          onClick={() => setCollapsed(true)}
          className="rounded-md p-1 text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
          aria-label={t("Collapse sidebar")}
        >
          <PanelLeftClose size={15} />
        </button>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-2 pt-1">
        <div className="space-y-px">
          <button
            onClick={handleNewChat}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--background)]/60 hover:text-[var(--foreground)]"
          >
            <Plus size={16} strokeWidth={2} />
            <span>{t("New Session")}</span>
          </button>

          {PRIMARY_NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            const hasSessionsBelow =
              item.href === "/chat" &&
              showSessions &&
              onSelectSession &&
              onRenameSession &&
              onDeleteSession;

            return (
              <div key={item.href}>
                <div>
                  {item.href === "/chat" ? (
                    <div
                      className={`flex items-center rounded-lg transition-colors ${
                        active
                          ? "bg-[var(--background)]/70 font-medium text-[var(--foreground)]"
                          : "text-[var(--muted-foreground)] hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
                      }`}
                    >
                      <Link
                        href={item.href}
                        onClick={() => {
                          setCollapsed(false);
                          if (!pathname.startsWith("/chat")) {
                            setActiveSessionId(null);
                          }
                        }}
                        className="flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2 text-[13.5px]"
                      >
                        <item.icon size={16} strokeWidth={active ? 1.9 : 1.5} />
                        <span>{t(item.label)}</span>
                      </Link>
                      {hasSessionsBelow && (
                        <button
                          type="button"
                          onClick={() => {
                            if (!pathname.startsWith("/chat")) {
                              router.push("/chat");
                              setCollapsed(false);
                              setActiveSessionId(null);
                              return;
                            }
                            setChatSessionsOpen(!chatSessionsOpen);
                          }}
                          className="mr-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[var(--muted-foreground)] transition-colors hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
                          aria-label={
                            chatSessionsVisible
                              ? t("Collapse sessions")
                              : t("Expand sessions")
                          }
                          aria-expanded={chatSessionsVisible}
                        >
                          {chatSessionsVisible ? (
                            <ChevronDown size={15} strokeWidth={1.8} />
                          ) : (
                            <ChevronRight size={15} strokeWidth={1.8} />
                          )}
                        </button>
                      )}
                    </div>
                  ) : (
                    <Link
                      href={item.href}
                      className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] transition-colors ${
                        active
                          ? "bg-[var(--background)]/70 font-medium text-[var(--foreground)]"
                          : "text-[var(--muted-foreground)] hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
                      }`}
                    >
                      <item.icon size={16} strokeWidth={active ? 1.9 : 1.5} />
                      <span>{t(item.label)}</span>
                    </Link>
                  )}
                </div>
                {hasSessionsBelow && chatSessionsVisible && (
                  <div className={sessionViewportClassName}>
                    <SessionList
                      sessions={sessions}
                      activeSessionId={activeSessionId}
                      loading={loadingSessions}
                      onSelect={onSelectSession}
                      onRename={onRenameSession}
                      onDelete={onDeleteSession}
                      compact
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </nav>

      <div className="shrink-0 px-2 py-2">
        {footerSlot}
      </div>
    </aside>
  );
}
