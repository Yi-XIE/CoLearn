"use client";

export type AppLanguage = "en" | "zh";

export const ACTIVE_SESSION_STORAGE_KEY = "deeptutor.activeSessionId.tab";
export const ACTIVE_PROJECT_STORAGE_KEY = "colearn.activeProjectId";
export const LANGUAGE_STORAGE_KEY = "deeptutor-language";
export const SIDEBAR_COLLAPSED_STORAGE_KEY = "deeptutor.sidebarCollapsed";
export const CHAT_SESSIONS_OPEN_STORAGE_KEY = "colearn.chatSessionsOpen";
export const SESSION_UNREAD_STORAGE_KEY = "colearn.sessionUnreadMap";
export const SESSION_SEEN_STORAGE_KEY = "colearn.sessionSeenMap";

export const ACTIVE_SESSION_EVENT = "deeptutor:active-session";
export const ACTIVE_PROJECT_EVENT = "colearn:active-project";
export const LANGUAGE_EVENT = "deeptutor:language";
export const SIDEBAR_COLLAPSED_EVENT = "deeptutor:sidebar-collapsed";
export const CHAT_SESSIONS_OPEN_EVENT = "colearn:chat-sessions-open";
export const SESSION_UNREAD_EVENT = "colearn:session-unread";

export type SessionUnreadMap = Record<string, boolean>;
type SessionSeenMap = Record<string, number>;

export function normalizeLanguage(
  value: string | null | undefined,
): AppLanguage {
  return value === "zh" ? "zh" : "en";
}

export function readStoredLanguage(): AppLanguage {
  if (typeof window === "undefined") return "en";
  try {
    return normalizeLanguage(window.localStorage.getItem(LANGUAGE_STORAGE_KEY));
  } catch {
    return "en";
  }
}

export function writeStoredLanguage(language: AppLanguage): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    window.dispatchEvent(
      new CustomEvent(LANGUAGE_EVENT, {
        detail: { language },
      }),
    );
  } catch {
    // localStorage may be unavailable
  }
}

export function readStoredActiveSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeStoredActiveSessionId(sessionId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (sessionId) {
      window.sessionStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
    } else {
      window.sessionStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
    }
    window.dispatchEvent(
      new CustomEvent(ACTIVE_SESSION_EVENT, {
        detail: { sessionId },
      }),
    );
  } catch {
    // sessionStorage may be unavailable
  }
}

export function readStoredActiveProjectId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeStoredActiveProjectId(projectId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (projectId) {
      window.localStorage.setItem(ACTIVE_PROJECT_STORAGE_KEY, projectId);
    } else {
      window.localStorage.removeItem(ACTIVE_PROJECT_STORAGE_KEY);
    }
    window.dispatchEvent(
      new CustomEvent(ACTIVE_PROJECT_EVENT, {
        detail: { projectId },
      }),
    );
  } catch {
    // localStorage may be unavailable
  }
}

export function readStoredSidebarCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeStoredSidebarCollapsed(collapsed: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      SIDEBAR_COLLAPSED_STORAGE_KEY,
      collapsed ? "1" : "0",
    );
    window.dispatchEvent(
      new CustomEvent(SIDEBAR_COLLAPSED_EVENT, {
        detail: { collapsed },
      }),
    );
  } catch {
    // localStorage may be unavailable
  }
}

export function readStoredChatSessionsOpen(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const value = window.localStorage.getItem(CHAT_SESSIONS_OPEN_STORAGE_KEY);
    return value === null ? true : value === "1";
  } catch {
    return true;
  }
}

export function writeStoredChatSessionsOpen(open: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      CHAT_SESSIONS_OPEN_STORAGE_KEY,
      open ? "1" : "0",
    );
    window.dispatchEvent(
      new CustomEvent(CHAT_SESSIONS_OPEN_EVENT, {
        detail: { open },
      }),
    );
  } catch {
    // localStorage may be unavailable
  }
}

function parseJsonRecord<T extends Record<string, unknown>>(
  raw: string | null,
): T {
  if (!raw) return {} as T;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as T)
      : ({} as T);
  } catch {
    return {} as T;
  }
}

export function readStoredSessionUnreadMap(): SessionUnreadMap {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(SESSION_UNREAD_STORAGE_KEY);
    const parsed = parseJsonRecord<Record<string, unknown>>(raw);
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, boolean] => typeof entry[1] === "boolean",
      ),
    );
  } catch {
    return {};
  }
}

export function writeStoredSessionUnreadMap(unreadMap: SessionUnreadMap): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      SESSION_UNREAD_STORAGE_KEY,
      JSON.stringify(unreadMap),
    );
    window.dispatchEvent(
      new CustomEvent(SESSION_UNREAD_EVENT, {
        detail: { unreadMap },
      }),
    );
  } catch {
    // localStorage may be unavailable
  }
}

export function readStoredSessionSeenMap(): SessionSeenMap {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(SESSION_SEEN_STORAGE_KEY);
    const parsed = parseJsonRecord<Record<string, unknown>>(raw);
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, number] =>
          typeof entry[1] === "number" && Number.isFinite(entry[1]),
      ),
    );
  } catch {
    return {};
  }
}

export function writeStoredSessionSeenMap(seenMap: SessionSeenMap): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      SESSION_SEEN_STORAGE_KEY,
      JSON.stringify(seenMap),
    );
  } catch {
    // localStorage may be unavailable
  }
}
