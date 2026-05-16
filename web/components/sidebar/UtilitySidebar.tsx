"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { Settings } from "lucide-react";
import { SidebarShell } from "@/components/sidebar/SidebarShell";
import SessionDeleteModal from "@/components/sidebar/SessionDeleteModal";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { useAppShell } from "@/context/AppShellContext";
import {
  readStoredSessionUnreadMap,
  SESSION_UNREAD_EVENT,
  SESSION_UNREAD_STORAGE_KEY,
  type SessionUnreadMap,
} from "@/context/app-shell-storage";
import {
  deleteSession,
  listSessions,
  updateSessionTitle,
  type SessionSummary,
} from "@/lib/session-api";

export default function UtilitySidebar() {
  const { t } = useTranslation();
  const router = useRouter();
  const { activeProjectId, activeSessionId, setActiveSessionId } = useAppShell();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [sessionUnreadReplies, setSessionUnreadReplies] =
    useState<SessionUnreadMap>({});
  const hasLoadedSessionsRef = useRef(false);

  const refreshSessions = useCallback(async () => {
    if (!hasLoadedSessionsRef.current) {
      setLoadingSessions(true);
    }
    try {
      setSessions(
        await listSessions(50, 0, {
          force: true,
          projectId: activeProjectId || undefined,
        }),
      );
      hasLoadedSessionsRef.current = true;
    } catch (error) {
      console.error("Failed to load sessions", error);
    } finally {
      setLoadingSessions(false);
    }
  }, [activeProjectId]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setSessionUnreadReplies(readStoredSessionUnreadMap());

    const syncUnread = () => {
      setSessionUnreadReplies(readStoredSessionUnreadMap());
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === SESSION_UNREAD_STORAGE_KEY) {
        syncUnread();
      }
    };

    window.addEventListener(SESSION_UNREAD_EVENT, syncUnread);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(SESSION_UNREAD_EVENT, syncUnread);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const decoratedSessions = sessions.map((session) => ({
    ...session,
    has_unread_reply: sessionUnreadReplies[session.session_id] ?? false,
  }));

  const handleNewChat = useCallback(() => {
    setActiveSessionId(null);
    router.push("/chat");
  }, [router, setActiveSessionId]);

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      setActiveSessionId(sessionId);
      router.push(`/chat/${sessionId}`);
    },
    [router, setActiveSessionId],
  );

  const handleRenameSession = useCallback(
    async (sessionId: string, title: string) => {
      const updated = await updateSessionTitle(sessionId, title);
      setSessions((prev) =>
        prev.map((session) =>
          session.session_id === sessionId
            ? {
                ...session,
                title: updated.title,
                updated_at: updated.updated_at,
              }
            : session,
        ),
      );
    },
    [],
  );

  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      setPendingDeleteId(sessionId);
    },
    [],
  );

  const confirmDeleteSession = useCallback(async () => {
    if (!pendingDeleteId) return;
    setDeleting(true);
    try {
      await deleteSession(pendingDeleteId);
      setSessions((prev) =>
        prev.filter((session) => session.session_id !== pendingDeleteId),
      );
      if (activeSessionId === pendingDeleteId) {
        setActiveSessionId(null);
      }
      setPendingDeleteId(null);
    } finally {
      setDeleting(false);
    }
  }, [activeSessionId, pendingDeleteId, setActiveSessionId]);

  const pendingDeleteSession =
    sessions.find((session) => session.session_id === pendingDeleteId) ?? null;

  return (
    <>
      <SidebarShell
        showSessions
        sessions={decoratedSessions}
        activeSessionId={activeSessionId}
        loadingSessions={loadingSessions}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        footerSlot={
          <div className="flex flex-col gap-2">
            <Link
              href="/settings"
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
            >
              <Settings size={16} strokeWidth={1.6} />
              <span>{t("Settings")}</span>
            </Link>
            <LogoutButton />
          </div>
        }
      />
      <SessionDeleteModal
        open={Boolean(pendingDeleteSession)}
        session={pendingDeleteSession}
        deleting={deleting}
        onClose={() => setPendingDeleteId(null)}
        onConfirm={confirmDeleteSession}
      />
    </>
  );
}
