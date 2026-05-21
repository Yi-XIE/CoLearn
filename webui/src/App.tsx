import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { DeleteConfirm } from "@/components/DeleteConfirm";
import { MemoryPanel } from "@/components/panels/MemoryPanel";
import { KnowledgeGardenPanel } from "@/components/panels/KnowledgeGardenPanel";
import { SkillsPanel } from "@/components/panels/SkillsPanel";
import { SettingsView } from "@/components/settings/SettingsView";
import { Sidebar } from "@/components/Sidebar";
import { ThreadShell } from "@/components/thread/ThreadShell";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { useSessions } from "@/hooks/useSessions";
import { useTheme } from "@/hooks/useTheme";
import { ColearnWsClient } from "@/lib/nanobot-client";
import type { ChatSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ClientProvider, useClient } from "@/providers/ClientProvider";

type BootState = {
  client: ColearnWsClient;
  token: string;
  modelName: string | null;
};

const SIDEBAR_STORAGE_KEY = "nanobot-webui.sidebar";
const SIDEBAR_WIDTH = 272;
const BRAND_NAME = "CoLearn";

type ShellView = "chat" | "knowledge" | "memory" | "skills" | "settings";

function readSidebarOpen(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const raw = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (raw === null) return true;
    return raw === "1";
  } catch {
    return true;
  }
}

function deriveApiWsUrl(): string {
  if (typeof window === "undefined") return "ws://127.0.0.1:8001/api/v1/ws";
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/v1/ws`;
}

function viewTitle(view: ShellView): string {
  switch (view) {
    case "knowledge":
      return "\u77e5\u8bc6\u82b1\u56ed";
    case "memory":
      return "\u8bb0\u5fc6";
    case "skills":
      return "\u6280\u80fd";
    case "settings":
      return "\u8bbe\u7f6e";
    default:
      return BRAND_NAME;
  }
}

export default function App() {
  const [state, setState] = useState<BootState>(() => ({
    client: new ColearnWsClient({ url: deriveApiWsUrl(), baseUrl: "" }),
    token: "",
    modelName: null,
  }));
  useEffect(() => {
    let cancelled = false;
    state.client.connect();
    (async () => {
      try {
        const boot = await fetch("/api/v1/system/status", { credentials: "same-origin" });
        const status = boot.ok ? await boot.json() : null;
        if (cancelled) return;
        setState((current) => ({ ...current, modelName: status?.llm?.model ?? null }));
      } catch {
        if (cancelled) return;
      }
    })();
    return () => {
      cancelled = true;
      state.client.close();
    };
  }, [state.client]);

  const handleModelNameChange = useCallback((modelName: string | null) => {
    setState((current) => ({ ...current, modelName }));
  }, []);
  return (
    <ClientProvider client={state.client} token={state.token} modelName={state.modelName}>
      <Shell onModelNameChange={handleModelNameChange} onLogout={undefined} />
    </ClientProvider>
  );
}

function Shell({
  onModelNameChange,
  onLogout,
}: {
  onModelNameChange: (modelName: string | null) => void;
  onLogout?: () => void;
}) {
  const { t } = useTranslation();
  const { client, token } = useClient();
  void onLogout;
  const { theme, toggle } = useTheme();
  const { sessions, loading, refresh, createChat, deleteChat } = useSessions();
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [view, setView] = useState<ShellView>("chat");
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState<boolean>(readSidebarOpen);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<{ key: string; label: string } | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, desktopSidebarOpen ? "1" : "0");
    } catch {
      // ignore storage errors
    }
  }, [desktopSidebarOpen]);

  const activeSession = useMemo<ChatSummary | null>(() => {
    if (!activeKey) return null;
    return sessions.find((session) => session.key === activeKey) ?? null;
  }, [sessions, activeKey]);

  const closeDesktopSidebar = useCallback(() => setDesktopSidebarOpen(false), []);
  const closeMobileSidebar = useCallback(() => setMobileSidebarOpen(false), []);

  const toggleSidebar = useCallback(() => {
    const isDesktop =
      typeof window !== "undefined" &&
      window.matchMedia("(min-width: 1024px)").matches;
    if (isDesktop) {
      setDesktopSidebarOpen((value) => !value);
    } else {
      setMobileSidebarOpen((value) => !value);
    }
  }, []);

  const onCreateChat = useCallback(async () => {
    try {
      const chatId = await createChat();
      setActiveKey(chatId);
      setView("chat");
      setMobileSidebarOpen(false);
      return chatId;
    } catch (error) {
      console.error("Failed to create chat", error);
      return null;
    }
  }, [createChat]);

  const onNewChat = useCallback(() => {
    setActiveKey(null);
    setView("chat");
    setMobileSidebarOpen(false);
  }, []);

  const onSelectChat = useCallback((key: string) => {
    setActiveKey(key);
    setView("chat");
    setMobileSidebarOpen(false);
  }, []);

  const onBackToChat = useCallback(() => {
    setView("chat");
    setMobileSidebarOpen(false);
    setActiveKey((current) => {
      if (!current) return null;
      if (sessions.some((session) => session.key === current)) return current;
      return sessions[0]?.key ?? null;
    });
  }, [sessions]);

  useEffect(() => {
    return client.onRuntimeModelUpdate((modelName) => onModelNameChange(modelName));
  }, [client, onModelNameChange]);

  const onConfirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    const key = pendingDelete.key;
    const deletingActive = activeKey === key;
    const currentIndex = sessions.findIndex((session) => session.key === key);
    const fallbackKey = deletingActive
      ? sessions[currentIndex + 1]?.key ?? sessions[currentIndex - 1]?.key ?? null
      : activeKey;
    setPendingDelete(null);
    if (deletingActive) setActiveKey(fallbackKey);
    try {
      await deleteChat(key);
    } catch (error) {
      if (deletingActive) setActiveKey(key);
      console.error("Failed to delete session", error);
    }
  }, [activeKey, deleteChat, pendingDelete, sessions]);

  const headerTitle = activeSession
    ? activeSession.title ||
      activeSession.preview ||
      t("chat.fallbackTitle", { id: activeSession.chatId.slice(0, 6) })
    : BRAND_NAME;

  useEffect(() => {
    if (view !== "chat") {
      document.title = `${viewTitle(view)} - ${BRAND_NAME}`;
      return;
    }
    document.title = activeSession ? `${headerTitle} - ${BRAND_NAME}` : BRAND_NAME;
  }, [activeSession, headerTitle, view]);

  const sidebarProps = {
    activeView: view,
    sessions,
    activeKey,
    loading,
    onOpenKnowledge: () => {
      setView("knowledge");
      setMobileSidebarOpen(false);
    },
    onOpenMemory: () => {
      setView("memory");
      setMobileSidebarOpen(false);
    },
    onOpenSkills: () => {
      setView("skills");
      setMobileSidebarOpen(false);
    },
    onNewChat,
    onSelect: onSelectChat,
    onRequestDelete: (key: string, label: string) => setPendingDelete({ key, label }),
    onOpenSettings: () => {
      setView("settings");
      setMobileSidebarOpen(false);
    },
  };

  return (
    <div className="relative flex h-full w-full overflow-hidden">
      <aside
        className={cn(
          "relative z-20 hidden shrink-0 overflow-hidden lg:block",
          "transition-[width] duration-300 ease-out",
        )}
        style={{ width: desktopSidebarOpen ? SIDEBAR_WIDTH : 0 }}
      >
        <div
          className={cn(
            "absolute inset-y-0 left-0 h-full overflow-hidden bg-sidebar shadow-inner-right",
            "transition-transform duration-300 ease-out",
            desktopSidebarOpen ? "translate-x-0" : "-translate-x-full",
          )}
          style={{ width: SIDEBAR_WIDTH }}
        >
          <Sidebar {...sidebarProps} onCollapse={closeDesktopSidebar} />
        </div>
      </aside>

      <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
        <SheetContent
          side="left"
          showCloseButton={false}
          className="p-0 lg:hidden"
          style={{ width: SIDEBAR_WIDTH, maxWidth: SIDEBAR_WIDTH }}
        >
          <Sidebar {...sidebarProps} onCollapse={closeMobileSidebar} />
        </SheetContent>
      </Sheet>

      <main className="relative flex h-full min-w-0 flex-1 flex-col">
        {view === "chat" ? (
          <div className="absolute inset-0 flex flex-col">
            <ThreadShell
              session={activeSession}
              title={headerTitle}
              onToggleSidebar={toggleSidebar}
              onNewChat={onNewChat}
              onCreateChat={onCreateChat}
              onTurnEnd={() => void refresh()}
              theme={theme}
              onToggleTheme={toggle}
              hideSidebarToggleOnDesktop={desktopSidebarOpen}
            />
          </div>
        ) : null}

        {view === "knowledge" ? (
          <KnowledgeGardenPanel
            token={token}
            onToggleSidebar={toggleSidebar}
            theme={theme}
            onToggleTheme={toggle}
            hideSidebarToggleOnDesktop={desktopSidebarOpen}
          />
        ) : null}

        {view === "memory" ? (
          <MemoryPanel
            token={token}
            onToggleSidebar={toggleSidebar}
            theme={theme}
            onToggleTheme={toggle}
            hideSidebarToggleOnDesktop={desktopSidebarOpen}
          />
        ) : null}

        {view === "skills" ? (
          <SkillsPanel
            token={token}
            onToggleSidebar={toggleSidebar}
            theme={theme}
            onToggleTheme={toggle}
            hideSidebarToggleOnDesktop={desktopSidebarOpen}
          />
        ) : null}

        {view === "settings" ? (
          <div className="absolute inset-0 flex flex-col">
            <SettingsView
              theme={theme}
              onToggleTheme={toggle}
              onBackToChat={onBackToChat}
              onModelNameChange={onModelNameChange}
              onLogout={onLogout}
              onRestart={undefined}
              isRestarting={false}
            />
          </div>
        ) : null}
      </main>

      <DeleteConfirm
        open={!!pendingDelete}
        title={pendingDelete?.label ?? ""}
        onCancel={() => setPendingDelete(null)}
        onConfirm={onConfirmDelete}
      />
    </div>
  );
}
