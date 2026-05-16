"use client";

import { createPortal } from "react-dom";
import { Check, EllipsisVertical, Pencil, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { type SessionSummary } from "@/lib/session-api";
import { normalizeMessageContent, truncateText } from "@/lib/message-content";

interface SessionListProps {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading?: boolean;
  compact?: boolean;
  onSelect: (sessionId: string) => void | Promise<void>;
  onRename: (sessionId: string, title: string) => void | Promise<void>;
  onDelete: (sessionId: string) => void | Promise<void>;
}

function UnreadIndicator({
  visible,
  className = "ml-1.5",
}: {
  visible?: boolean;
  className?: string;
}) {
  if (!visible) return null;
  return (
    <span
      className={`${className} inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-[#b8794a]`}
    />
  );
}

function groupLabel(timestamp: number): string {
  const now = new Date();
  const date = new Date(timestamp * 1000);
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const startOfItemDay = new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
  ).getTime();
  const diffDays = Math.floor((startOfToday - startOfItemDay) / 86400000);
  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return "Last 7 days";
  return "Earlier";
}

function relativeTime(timestamp: number): string {
  const diffSeconds = Math.round(timestamp - Date.now() / 1000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const abs = Math.abs(diffSeconds);
  if (abs < 60) return formatter.format(diffSeconds, "second");
  if (abs < 3600)
    return formatter.format(Math.round(diffSeconds / 60), "minute");
  if (abs < 86400)
    return formatter.format(Math.round(diffSeconds / 3600), "hour");
  return formatter.format(Math.round(diffSeconds / 86400), "day");
}

export default function SessionList({
  sessions,
  activeSessionId,
  loading = false,
  compact = false,
  onSelect,
  onRename,
  onDelete,
}: SessionListProps) {
  const { t } = useTranslation();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [menuSessionId, setMenuSessionId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuButtonRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);

  const grouped = useMemo(() => {
    const buckets = new Map<string, SessionSummary[]>();
    for (const session of sessions) {
      const label = groupLabel(session.updated_at);
      const current = buckets.get(label) ?? [];
      current.push(session);
      buckets.set(label, current);
    }
    return Array.from(buckets.entries());
  }, [sessions]);

  const startEdit = (session: SessionSummary) => {
    setEditingId(session.session_id);
    setDraftTitle(session.title);
  };

  const commitEdit = async () => {
    if (!editingId) return;
    const nextTitle = draftTitle.trim();
    if (!nextTitle) {
      setEditingId(null);
      setDraftTitle("");
      return;
    }
    await onRename(editingId, nextTitle);
    setEditingId(null);
    setDraftTitle("");
  };

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuSessionId(null);
        setMenuPosition(null);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuSessionId(null);
        setMenuPosition(null);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  useEffect(() => {
    if (!menuSessionId) return;
    const anchor = menuButtonRefs.current[menuSessionId];
    if (!anchor) return;

    const syncPosition = () => {
      const rect = anchor.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + 6,
        left: rect.right - 116,
      });
    };

    syncPosition();
    window.addEventListener("resize", syncPosition);
    window.addEventListener("scroll", syncPosition, true);
    return () => {
      window.removeEventListener("resize", syncPosition);
      window.removeEventListener("scroll", syncPosition, true);
    };
  }, [menuSessionId]);

  const renderSessionMenu = (session: SessionSummary) => {
    if (typeof document === "undefined" || menuSessionId !== session.session_id || !menuPosition) {
      return null;
    }

    return createPortal(
      <div
        ref={menuRef}
        className="fixed z-[70] min-w-[116px] rounded-lg border border-[var(--border)] bg-[var(--popover)] py-1 shadow-lg"
        style={{ top: menuPosition.top, left: menuPosition.left }}
      >
        <button
          onClick={(event) => {
            event.stopPropagation();
            setMenuSessionId(null);
            setMenuPosition(null);
            startEdit(session);
          }}
          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)]/40 hover:text-[var(--foreground)]"
        >
          <Pencil size={11} />
          <span>{t("Rename")}</span>
        </button>
        <button
          onClick={(event) => {
            event.stopPropagation();
            setMenuSessionId(null);
            setMenuPosition(null);
            void onDelete(session.session_id);
          }}
          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)]/40 hover:text-[var(--destructive)]"
        >
          <Trash2 size={11} />
          <span>{t("Delete")}</span>
        </button>
      </div>,
      document.body,
    );
  };

  if (loading) {
    if (compact) {
      return (
        <div className="space-y-1.5 py-1">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="ml-[38px] h-4 w-3/4 animate-pulse rounded bg-[var(--muted)]/40"
            />
          ))}
        </div>
      );
    }
    return (
      <div className="space-y-2 px-1.5 py-2">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-10 animate-pulse rounded-md bg-[var(--muted)]/60"
          />
        ))}
      </div>
    );
  }

  if (sessions.length === 0) {
    if (compact) return null;
    return (
      <div className="px-3 py-4 text-center text-[11px] text-[var(--muted-foreground)]/70">
        {t("No conversations yet")}
      </div>
    );
  }

  /* ---- Compact tree-line style (under Chat nav item) ---- */
  if (compact) {
    return (
      <div className="pt-0.5 pb-1">
        {grouped.map(([, items], groupIdx) => (
          <div key={groupIdx}>
            {groupIdx > 0 && (
              <div className="my-1 ml-[38px] mr-2 border-t border-[var(--border)]/20" />
            )}
            {items.map((session) => {
              const active = activeSessionId === session.session_id;
              const isEditing = editingId === session.session_id;
              const menuOpen = menuSessionId === session.session_id;
              return (
                <div
                  key={session.session_id}
                  onClick={() => void onSelect(session.session_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      void onSelect(session.session_id);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  className={`group relative flex min-h-[36px] items-center rounded-lg px-3 py-1.5 pr-12 text-left transition-colors ${
                    active
                      ? "bg-[var(--background)]/70 text-[var(--foreground)]"
                      : "text-[var(--muted-foreground)] hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
                  }`}
                >
                  <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center">
                    <UnreadIndicator
                      visible={session.has_unread_reply}
                      className=""
                    />
                  </span>
                  {isEditing ? (
                    <input
                      value={draftTitle}
                      autoFocus
                      onChange={(event) => setDraftTitle(event.target.value)}
                      onBlur={() => void commitEdit()}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void commitEdit();
                        if (event.key === "Escape") {
                          setEditingId(null);
                          setDraftTitle("");
                        }
                      }}
                      onClick={(event) => event.stopPropagation()}
                      className="ml-2.5 min-w-0 flex-1 rounded border border-[var(--border)] bg-[var(--background)] px-1.5 py-px text-[12px] text-[var(--foreground)] outline-none focus:ring-1 focus:ring-[var(--primary)]/40"
                    />
                  ) : (
                    <div className="ml-2.5 flex min-w-0 flex-1 items-center">
                      <span
                        className={`block min-w-0 flex-1 truncate text-[13.5px] leading-[1.35] ${active ? "font-medium" : ""}`}
                      >
                        {session.title || "Untitled chat"}
                      </span>
                    </div>
                  )}
                  <div
                    className={`absolute right-2 top-1/2 -translate-y-1/2 transition-opacity ${
                      menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                    }`}
                  >
                    {isEditing ? (
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          void commitEdit();
                        }}
                        className="rounded p-0.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                        aria-label={t("Save title")}
                      >
                        <Check size={10} />
                      </button>
                    ) : (
                      <>
                        <button
                          ref={(node) => {
                            menuButtonRefs.current[session.session_id] = node;
                          }}
                          onClick={(event) => {
                            event.stopPropagation();
                            setMenuSessionId((current) =>
                              current === session.session_id
                                ? null
                                : session.session_id,
                            );
                            setMenuPosition(null);
                          }}
                          className="rounded p-0.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                          aria-label={t("Chat actions")}
                        >
                          <EllipsisVertical size={12} />
                        </button>
                        {renderSessionMenu(session)}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    );
  }

  /* ---- Classic style ---- */
  return (
    <div className="space-y-4">
      {grouped.map(([label, items]) => (
        <div key={label}>
          <div className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">
            {label}
          </div>
          <div className="divide-y divide-[var(--border)]/45 overflow-hidden rounded-lg border border-[var(--border)]/45 bg-[var(--card)]/50">
            {items.map((session) => {
              const active = activeSessionId === session.session_id;
              const isEditing = editingId === session.session_id;
              const menuOpen = menuSessionId === session.session_id;
              return (
                <div
                  key={session.session_id}
                  onClick={() => void onSelect(session.session_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      void onSelect(session.session_id);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  className={`group relative w-full px-3 py-2.5 text-left transition-colors duration-150 ${
                    active
                      ? "bg-[var(--background)]/70 text-[var(--foreground)]"
                      : "text-[var(--muted-foreground)] hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
                  }`}
                >
                  {active && (
                    <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--primary)]" />
                  )}
                  <div className="flex items-start gap-1.5">
                    <div className="min-w-0 flex-1">
                      {isEditing ? (
                        <input
                          value={draftTitle}
                          autoFocus
                          onChange={(event) =>
                            setDraftTitle(event.target.value)
                          }
                          onBlur={() => void commitEdit()}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") void commitEdit();
                            if (event.key === "Escape") {
                              setEditingId(null);
                              setDraftTitle("");
                            }
                          }}
                          onClick={(event) => event.stopPropagation()}
                          className="w-full rounded border border-[var(--border)] bg-[var(--background)] px-2 py-0.5 text-[12px] text-[var(--foreground)] outline-none focus:ring-1 focus:ring-[var(--primary)]/40"
                        />
                      ) : (
                        <div className="flex items-center">
                          <UnreadIndicator
                            visible={session.has_unread_reply}
                            className="mr-1.5"
                          />
                          <span
                            className={`line-clamp-1 min-w-0 flex-1 text-[12px] leading-snug ${
                              active ? "font-medium" : "font-normal"
                            }`}
                          >
                            {session.title || "Untitled chat"}
                          </span>
                        </div>
                      )}
                      {!isEditing && (
                        <div className="mt-0.5 line-clamp-1 text-[11px] leading-tight text-[var(--muted-foreground)]">
                          {truncateText(
                            normalizeMessageContent(session.last_message),
                            120,
                          ) || relativeTime(session.updated_at)}
                        </div>
                      )}
                    </div>
                    <div
                      className={`relative flex shrink-0 items-center gap-0.5 pt-px transition-opacity ${
                        menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                      }`}
                    >
                      {isEditing ? (
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            void commitEdit();
                          }}
                          className="rounded p-0.5 text-[var(--muted-foreground)] hover:bg-[var(--background)] hover:text-[var(--foreground)]"
                          aria-label={t("Save title")}
                        >
                          <Check size={12} />
                        </button>
                      ) : (
                        <>
                          <button
                            ref={(node) => {
                              menuButtonRefs.current[session.session_id] = node;
                            }}
                            onClick={(event) => {
                              event.stopPropagation();
                              setMenuSessionId((current) =>
                                current === session.session_id
                                  ? null
                                  : session.session_id,
                              );
                              setMenuPosition(null);
                            }}
                            className="rounded p-0.5 text-[var(--muted-foreground)] hover:bg-[var(--background)] hover:text-[var(--foreground)]"
                            aria-label={t("Chat actions")}
                          >
                            <EllipsisVertical size={12} />
                          </button>
                          {renderSessionMenu(session)}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
