"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";
import {
  getStoredTheme,
  getSystemTheme,
  setTheme as applyThemePreference,
  subscribeToThemeChanges,
  type Theme,
} from "@/lib/theme";
import {
  ACTIVE_PROJECT_EVENT,
  ACTIVE_PROJECT_STORAGE_KEY,
  ACTIVE_SESSION_EVENT,
  ACTIVE_SESSION_STORAGE_KEY,
  CHAT_SESSIONS_OPEN_EVENT,
  CHAT_SESSIONS_OPEN_STORAGE_KEY,
  LANGUAGE_EVENT,
  LANGUAGE_STORAGE_KEY,
  SIDEBAR_COLLAPSED_EVENT,
  SIDEBAR_COLLAPSED_STORAGE_KEY,
  normalizeLanguage,
  readStoredActiveProjectId,
  readStoredActiveSessionId,
  readStoredChatSessionsOpen,
  readStoredLanguage,
  readStoredSidebarCollapsed,
  writeStoredActiveProjectId,
  writeStoredActiveSessionId,
  writeStoredChatSessionsOpen,
  writeStoredLanguage,
  writeStoredSidebarCollapsed,
  type AppLanguage,
} from "@/context/app-shell-storage";

interface AppShellContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  language: AppLanguage;
  setLanguage: (language: AppLanguage) => void;
  activeProjectId: string | null;
  setActiveProjectId: (projectId: string | null) => void;
  activeSessionId: string | null;
  setActiveSessionId: (sessionId: string | null) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  chatSessionsOpen: boolean;
  setChatSessionsOpen: (open: boolean) => void;
}

const AppShellContext = createContext<AppShellContextValue | null>(null);

function subscribeStorageKey(
  storageKey: string,
  eventName: string,
  onStoreChange: () => void,
) {
  if (typeof window === "undefined") {
    return () => {};
  }

  const onStorage = (event: StorageEvent) => {
    if (event.key === storageKey) {
      onStoreChange();
    }
  };

  window.addEventListener("storage", onStorage);
  window.addEventListener(eventName, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(eventName, onStoreChange);
  };
}

function subscribeTheme(onStoreChange: () => void) {
  return subscribeToThemeChanges(() => {
    onStoreChange();
  });
}

function getThemeSnapshot(): Theme {
  return getStoredTheme() ?? getSystemTheme();
}

function getThemeServerSnapshot(): Theme {
  return "light";
}

function subscribeLanguage(onStoreChange: () => void) {
  return subscribeStorageKey(
    LANGUAGE_STORAGE_KEY,
    LANGUAGE_EVENT,
    onStoreChange,
  );
}

function getLanguageServerSnapshot(): AppLanguage {
  return "en";
}

function subscribeActiveProject(onStoreChange: () => void) {
  return subscribeStorageKey(
    ACTIVE_PROJECT_STORAGE_KEY,
    ACTIVE_PROJECT_EVENT,
    onStoreChange,
  );
}

function getNullServerSnapshot(): string | null {
  return null;
}

function subscribeActiveSession(onStoreChange: () => void) {
  return subscribeStorageKey(
    ACTIVE_SESSION_STORAGE_KEY,
    ACTIVE_SESSION_EVENT,
    onStoreChange,
  );
}

function subscribeSidebarCollapsed(onStoreChange: () => void) {
  return subscribeStorageKey(
    SIDEBAR_COLLAPSED_STORAGE_KEY,
    SIDEBAR_COLLAPSED_EVENT,
    onStoreChange,
  );
}

function getSidebarCollapsedServerSnapshot(): boolean {
  return false;
}

function subscribeChatSessionsOpen(onStoreChange: () => void) {
  return subscribeStorageKey(
    CHAT_SESSIONS_OPEN_STORAGE_KEY,
    CHAT_SESSIONS_OPEN_EVENT,
    onStoreChange,
  );
}

function getChatSessionsOpenServerSnapshot(): boolean {
  return true;
}

export function AppShellProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(
    subscribeTheme,
    getThemeSnapshot,
    getThemeServerSnapshot,
  );
  const language = useSyncExternalStore(
    subscribeLanguage,
    readStoredLanguage,
    getLanguageServerSnapshot,
  );
  const activeProjectId = useSyncExternalStore(
    subscribeActiveProject,
    readStoredActiveProjectId,
    getNullServerSnapshot,
  );
  const activeSessionId = useSyncExternalStore(
    subscribeActiveSession,
    readStoredActiveSessionId,
    getNullServerSnapshot,
  );
  const sidebarCollapsed = useSyncExternalStore(
    subscribeSidebarCollapsed,
    readStoredSidebarCollapsed,
    getSidebarCollapsedServerSnapshot,
  );
  const chatSessionsOpen = useSyncExternalStore(
    subscribeChatSessionsOpen,
    readStoredChatSessionsOpen,
    getChatSessionsOpenServerSnapshot,
  );

  const setTheme = useCallback((nextTheme: Theme) => {
    applyThemePreference(nextTheme);
  }, []);

  const setLanguage = useCallback((nextLanguage: AppLanguage) => {
    writeStoredLanguage(nextLanguage);
  }, []);

  const setActiveProjectId = useCallback((projectId: string | null) => {
    writeStoredActiveProjectId(projectId);
  }, []);

  const setActiveSessionId = useCallback((sessionId: string | null) => {
    writeStoredActiveSessionId(sessionId);
  }, []);

  const setSidebarCollapsed = useCallback((collapsed: boolean) => {
    writeStoredSidebarCollapsed(collapsed);
  }, []);

  const setChatSessionsOpen = useCallback((open: boolean) => {
    writeStoredChatSessionsOpen(open);
  }, []);

  const value = useMemo<AppShellContextValue>(
    () => ({
      theme,
      setTheme,
      language,
      setLanguage,
      activeProjectId,
      setActiveProjectId,
      activeSessionId,
      setActiveSessionId,
      sidebarCollapsed,
      setSidebarCollapsed,
      chatSessionsOpen,
      setChatSessionsOpen,
    }),
    [
      activeProjectId,
      activeSessionId,
      chatSessionsOpen,
      language,
      setActiveProjectId,
      setActiveSessionId,
      setChatSessionsOpen,
      setLanguage,
      setSidebarCollapsed,
      setTheme,
      sidebarCollapsed,
      theme,
    ],
  );

  return (
    <AppShellContext.Provider value={value}>
      {children}
    </AppShellContext.Provider>
  );
}

export function useAppShell() {
  const context = useContext(AppShellContext);
  if (!context) {
    throw new Error("useAppShell must be used inside AppShellProvider");
  }
  return context;
}
