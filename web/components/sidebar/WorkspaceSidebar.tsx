"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { Settings } from "lucide-react";
import { SidebarShell } from "@/components/sidebar/SidebarShell";
import SessionDeleteModal from "@/components/sidebar/SessionDeleteModal";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { useUnifiedChat } from "@/context/UnifiedChatContext";
import { useAppShell } from "@/context/AppShellContext";
import {
  deleteSession,
  listSessions,
  updateSessionTitle,
  type SessionSummary,
} from "@/lib/session-api";
import { getProject } from "@/lib/projects-api";
import { openLearningEntry } from "@/lib/learning-session-entry";

export default function WorkspaceSidebar() {
  const { t } = useTranslation();
  const router = useRouter();
  const { activeProjectId, setActiveSessionId } = useAppShell();
  const {
    newSession,
    selectedSessionId,
    sessionStatuses,
    sessionUnreadReplies,
    sidebarRefreshToken,
  } = useUnifiedChat();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const hasLoadedSessionsRef = useRef(false);

  const refreshSessions = useCallback(async () => {
    if (!hasLoadedSessionsRef.current) {
      setLoadingSessions(true);
    }
    try {
      setSessions(
        await listSessions(50, 0, { force: true, projectId: activeProjectId || undefined }),
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
  }, [refreshSessions, sidebarRefreshToken]);

  const orderedSessions = sessions
    .map((session, index) => {
      const runtime = sessionStatuses[session.session_id];
      return {
        index,
        session: runtime
          ? {
              ...session,
              status: runtime.status,
              active_turn_id: runtime.activeTurnId || session.active_turn_id,
            }
          : session,
        has_unread_reply: sessionUnreadReplies[session.session_id] ?? false,
      };
    })
    .sort((a, b) => {
      const aPriority = a.session.status === "running" ? 0 : 1;
      const bPriority = b.session.status === "running" ? 0 : 1;
      if (aPriority !== bPriority) return aPriority - bPriority;
      return a.index - b.index;
    })
    .map(({ session, has_unread_reply }) => ({
      ...session,
      has_unread_reply,
    }));

  const handleNewChat = useCallback(async () => {
    if (!activeProjectId) {
      newSession();
      router.push("/chat");
      return;
    }
    const project = await getProject(activeProjectId);
    const session = await openLearningEntry(project, {
      untitledLabel: t("Untitled"),
    });
    setActiveSessionId(session.session_id);
    router.push(`/chat/${session.session_id}`);
  }, [activeProjectId, newSession, router, setActiveSessionId, t]);

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      router.push(`/chat/${sessionId}`);
    },
    [router],
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
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("colearn:session-renamed", {
            detail: {
              sessionId,
              title: updated.title,
            },
          }),
        );
      }
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
      if (selectedSessionId === pendingDeleteId) {
        newSession();
        router.push("/chat");
      }
      setPendingDeleteId(null);
    } finally {
      setDeleting(false);
    }
  }, [newSession, pendingDeleteId, router, selectedSessionId]);

  const pendingDeleteSession =
    sessions.find((session) => session.session_id === pendingDeleteId) ?? null;

  return (
    <>
      <SidebarShell
        showSessions
        sessions={orderedSessions}
        activeSessionId={selectedSessionId}
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
