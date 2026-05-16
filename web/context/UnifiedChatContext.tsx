"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import {
  LANGUAGE_EVENT,
  LANGUAGE_STORAGE_KEY,
  normalizeLanguage,
  readStoredSessionSeenMap,
  readStoredSessionUnreadMap,
  readStoredLanguage,
  writeStoredSessionSeenMap,
  writeStoredSessionUnreadMap,
  writeStoredActiveSessionId,
} from "@/context/app-shell-storage";
import type { StreamEvent, ChatMessage, LLMSelection } from "@/lib/unified-ws";
import { UnifiedWSClient } from "@/lib/unified-ws";
import { getSession, type SessionMessage } from "@/lib/session-api";
import { normalizeMarkdownForDisplay } from "@/lib/markdown-display";
import { normalizeMessageContent } from "@/lib/message-content";
import { shouldAppendEventContent } from "@/lib/stream";
import {
  normalizeSourceReferences,
  type SourceReferencePayload,
} from "@/lib/source-references";

type SessionRuntimeStatus =
  | "idle"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "rejected";

interface OutgoingAttachment {
  type: string;
  url?: string;
  base64?: string;
  filename?: string;
  mime_type?: string;
}

type HistoryReferencePayload = string[];

type MemoryReferencePayload = Array<
  "summary" | "profile" | "mastery" | "event_store"
>;

export interface SendMessageOptions {
  displayUserMessage?: boolean;
  persistUserMessage?: boolean;
  requestSnapshotOverride?: MessageRequestSnapshot;
  sourceReferences?: SourceReferencePayload[];
  projectId?: string;
  projectTitle?: string;
}

export interface ChatState {
  sessionId: string | null;
  enabledTools: string[];
  knowledgeBases: string[];
  llmSelection: LLMSelection | null;
  messages: MessageItem[];
  isStreaming: boolean;
  currentStage: string;
  language: string;
}

interface SessionStatusSnapshot {
  sessionId: string;
  status: SessionRuntimeStatus;
  activeTurnId: string | null;
  updatedAt: number;
}

export interface MessageAttachment {
  type: string;
  filename?: string;
  base64?: string;
  url?: string;
  mime_type?: string;
  /** Stable per-attachment id; matches the URL segment served by /api/attachments. */
  id?: string;
  /** Plain-text rendering of office docs, populated by the backend extractor.
   *  Used by the preview drawer to show "what the LLM saw" for binary docs. */
  extracted_text?: string;
}

export interface MessageRequestSnapshot {
  content: string;
  enabledTools: string[];
  knowledgeBases: string[];
  language: string;
  attachments?: MessageAttachment[];
  config?: Record<string, unknown>;
  historyReferences?: HistoryReferencePayload;
  sourceReferences?: SourceReferencePayload[];
  projectId?: string;
  projectTitle?: string;
  skills?: string[];
  memoryReferences?: MemoryReferencePayload;
  llmSelection?: LLMSelection | null;
}

export interface MessageItem {
  role: "user" | "assistant" | "system";
  content: string;
  events?: StreamEvent[];
  attachments?: MessageAttachment[];
  requestSnapshot?: MessageRequestSnapshot;
}

interface SessionEntry extends ChatState {
  key: string;
  status: SessionRuntimeStatus;
  activeTurnId: string | null;
  lastSeq: number;
  updatedAt: number;
}

interface ProviderState {
  selectedKey: string | null;
  sessions: Record<string, SessionEntry>;
  sidebarRefreshToken: number;
}

type Action =
  | { type: "SET_TOOLS"; tools: string[] }
  | { type: "SET_KB"; kbs: string[] }
  | { type: "SET_LLM_SELECTION"; selection: LLMSelection | null }
  | { type: "SET_LANGUAGE"; lang: string }
  | {
      type: "ADD_USER_MSG";
      key: string;
      content: string;
      attachments?: MessageAttachment[];
      requestSnapshot?: MessageRequestSnapshot;
    }
  | { type: "POP_LAST_ASSISTANT"; key: string }
  | { type: "RESTORE_ASSISTANT"; key: string; message: MessageItem }
  | { type: "STREAM_START"; key: string }
  | { type: "STREAM_EVENT"; key: string; event: StreamEvent }
  | {
      type: "STREAM_END";
      key: string;
      status?: SessionRuntimeStatus;
      turnId?: string | null;
    }
  | {
      type: "BIND_SERVER_SESSION";
      key: string;
      sessionId: string;
      turnId?: string | null;
    }
  | {
      type: "LOAD_SESSION";
      key: string;
      sessionId: string;
      messages: MessageItem[];
      activeTurnId?: string | null;
      status?: SessionRuntimeStatus;
      tools?: string[];
      knowledgeBases?: string[];
      llmSelection?: LLMSelection | null;
      language?: string;
    }
  | { type: "NEW_SESSION"; key: string };

function createSessionEntry(
  key: string,
  sessionId: string | null = null,
): SessionEntry {
  return {
    key,
    sessionId,
    enabledTools: [],
    knowledgeBases: [],
    llmSelection: null,
    messages: [],
    isStreaming: false,
    currentStage: "",
    language: typeof window === "undefined" ? "en" : readStoredLanguage(),
    status: "idle",
    activeTurnId: null,
    lastSeq: 0,
    updatedAt: Date.now(),
  };
}

function ensureSelectedSession(state: ProviderState): SessionEntry {
  if (state.selectedKey && state.sessions[state.selectedKey]) {
    return state.sessions[state.selectedKey];
  }
  return createSessionEntry("draft");
}

function updateSelectedSession(
  state: ProviderState,
  updater: (session: SessionEntry) => SessionEntry,
): ProviderState {
  const current = ensureSelectedSession(state);
  const key = state.selectedKey || current.key;
  const nextSession = updater(current);
  return {
    ...state,
    selectedKey: key,
    sessions: {
      ...state.sessions,
      [key]: nextSession,
    },
  };
}

function reducer(state: ProviderState, action: Action): ProviderState {
  switch (action.type) {
    case "SET_TOOLS":
      return updateSelectedSession(state, (session) => ({
        ...session,
        enabledTools: action.tools,
      }));
    case "SET_KB":
      return updateSelectedSession(state, (session) => ({
        ...session,
        knowledgeBases: action.kbs,
      }));
    case "SET_LLM_SELECTION":
      return updateSelectedSession(state, (session) => ({
        ...session,
        llmSelection: action.selection,
      }));
    case "SET_LANGUAGE":
      return updateSelectedSession(state, (session) => ({
        ...session,
        language: action.lang,
      }));
    case "ADD_USER_MSG": {
      const session =
        state.sessions[action.key] ?? createSessionEntry(action.key);
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: [
              ...session.messages,
              {
                role: "user",
                content: action.content,
                ...(action.attachments?.length
                  ? { attachments: action.attachments }
                  : {}),
                ...(action.requestSnapshot
                  ? { requestSnapshot: action.requestSnapshot }
                  : {}),
              },
            ],
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "POP_LAST_ASSISTANT": {
      const session = state.sessions[action.key];
      if (!session || session.messages.length === 0) return state;
      const last = session.messages[session.messages.length - 1];
      if (last.role !== "assistant") return state;
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: session.messages.slice(0, -1),
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "RESTORE_ASSISTANT": {
      // Revert an optimistic POP_LAST_ASSISTANT when the server rejects a
      // regenerate request (e.g. ``regenerate_busy``), so the user doesn't
      // silently lose their last reply.
      const session = state.sessions[action.key];
      if (!session) return state;
      const messages = [...session.messages];
      // Drop any placeholder STREAM_START assistant bubble before restoring.
      while (
        messages.length > 0 &&
        messages[messages.length - 1].role === "assistant" &&
        (messages[messages.length - 1].content ?? "") === "" &&
        (messages[messages.length - 1].events?.length ?? 0) === 0
      ) {
        messages.pop();
      }
      messages.push(action.message);
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages,
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "STREAM_START":
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...(state.sessions[action.key] ?? createSessionEntry(action.key)),
            isStreaming: true,
            status: "running",
            messages: [
              ...(state.sessions[action.key]?.messages ?? []),
              {
                role: "assistant",
                content: "",
                events: [],
              },
            ],
            updatedAt: Date.now(),
          },
        },
      };
    case "STREAM_EVENT": {
      const session =
        state.sessions[action.key] ?? createSessionEntry(action.key);
      const msgs = [...session.messages];
      let last = msgs[msgs.length - 1];
      if (last?.role !== "assistant") {
        msgs.push({
          role: "assistant",
          content: "",
          events: [],
        });
        last = msgs[msgs.length - 1];
      }
      const events = [...(last?.events || []), action.event];
      let content = last?.content || "";
      if (shouldAppendEventContent(action.event))
        content += action.event.content;
      msgs[msgs.length - 1] = {
        ...(last || { role: "assistant", content: "" }),
        content,
        events,
      };
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: msgs,
            currentStage:
              action.event.type === "stage_start"
                ? action.event.stage
                : action.event.type === "stage_end"
                  ? ""
                  : session.currentStage,
            activeTurnId: action.event.turn_id || session.activeTurnId,
            lastSeq: Math.max(session.lastSeq, action.event.seq || 0),
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "STREAM_END":
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...(state.sessions[action.key] ?? createSessionEntry(action.key)),
            isStreaming: false,
            currentStage: "",
            status: action.status ?? "completed",
            activeTurnId:
              action.status === "running"
                ? action.turnId ||
                  state.sessions[action.key]?.activeTurnId ||
                  null
                : null,
            updatedAt: Date.now(),
          },
        },
        sidebarRefreshToken: state.sidebarRefreshToken + 1,
      };
    case "BIND_SERVER_SESSION": {
      const current =
        state.sessions[action.key] ?? createSessionEntry(action.key);
      const targetKey = action.sessionId;
      const existing = state.sessions[targetKey];
      const merged: SessionEntry = {
        ...(existing ?? current),
        ...current,
        key: targetKey,
        sessionId: action.sessionId,
        activeTurnId: action.turnId || current.activeTurnId,
        status: current.isStreaming ? "running" : current.status,
        updatedAt: Date.now(),
      };
      const nextSessions = { ...state.sessions };
      delete nextSessions[action.key];
      nextSessions[targetKey] = merged;
      return {
        ...state,
        selectedKey:
          state.selectedKey === action.key ? targetKey : state.selectedKey,
        sessions: nextSessions,
        sidebarRefreshToken: state.sidebarRefreshToken + 1,
      };
    }
    case "LOAD_SESSION": {
      const existing =
        state.sessions[action.key] ??
        createSessionEntry(action.key, action.sessionId);
      return {
        ...state,
        selectedKey: action.key,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...existing,
            key: action.key,
            sessionId: action.sessionId,
            enabledTools: action.tools ?? existing.enabledTools,
            knowledgeBases: action.knowledgeBases ?? existing.knowledgeBases,
            llmSelection:
              action.llmSelection !== undefined
                ? action.llmSelection
                : existing.llmSelection,
            messages: action.messages,
            isStreaming: (action.status || "idle") === "running",
            currentStage: "",
            activeTurnId: action.activeTurnId || null,
            status: action.status || "idle",
            language: action.language ?? existing.language,
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "NEW_SESSION": {
      const MAX_CACHED_SESSIONS = 20;
      let nextSessions = {
        ...state.sessions,
        [action.key]: createSessionEntry(action.key),
      };
      const keys = Object.keys(nextSessions);
      if (keys.length > MAX_CACHED_SESSIONS) {
        const evictable = keys
          .filter(
            (k) => k !== action.key && nextSessions[k].status !== "running",
          )
          .sort(
            (a, b) => nextSessions[a].updatedAt - nextSessions[b].updatedAt,
          );
        const toRemove = evictable.slice(0, keys.length - MAX_CACHED_SESSIONS);
        for (const k of toRemove) delete nextSessions[k];
      }
      return { ...state, selectedKey: action.key, sessions: nextSessions };
    }
    default:
      return state;
  }
}

const initialState: ProviderState = {
  selectedKey: null,
  sessions: {},
  sidebarRefreshToken: 0,
};

interface ChatContextValue {
  state: ChatState;
  setTools: (tools: string[]) => void;
  setKBs: (kbs: string[]) => void;
  setLLMSelection: (selection: LLMSelection | null) => void;
  setLanguage: (lang: string) => void;
  sendMessage: (
    content: string,
    attachments?: OutgoingAttachment[],
    config?: Record<string, unknown>,
    historyReferences?: HistoryReferencePayload,
    options?: SendMessageOptions,
    skills?: string[],
    memoryReferences?: MemoryReferencePayload,
  ) => void;
  cancelStreamingTurn: () => void;
  regenerateLastMessage: () => void;
  newSession: () => void;
  loadSession: (sessionId: string) => Promise<void>;
  selectedSessionId: string | null;
  sessionStatuses: Record<string, SessionStatusSnapshot>;
  sessionUnreadReplies: Record<string, boolean>;
  sidebarRefreshToken: number;
}

const ChatCtx = createContext<ChatContextValue | null>(null);

function hydrateMessageAttachments(
  attachments: SessionMessage["attachments"],
): MessageAttachment[] {
  return Array.isArray(attachments)
    ? attachments.map((item) => ({
        type: item.type,
        filename: item.filename,
        base64: item.base64,
        url: item.url,
        mime_type: item.mime_type,
        id: item.id,
        extracted_text: item.extracted_text,
      }))
    : [];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && item.length > 0,
      )
    : [];
}

function asLLMSelection(value: unknown): LLMSelection | null {
  const record = asRecord(value);
  const profileId =
    typeof record?.profile_id === "string" ? record.profile_id.trim() : "";
  const modelId =
    typeof record?.model_id === "string" ? record.model_id.trim() : "";
  return profileId && modelId
    ? { profile_id: profileId, model_id: modelId }
    : null;
}

function asMemoryReferences(value: unknown): MemoryReferencePayload {
  return asStringArray(value).filter(
    (
      item,
    ): item is "summary" | "profile" | "mastery" | "event_store" =>
      item === "summary" ||
      item === "profile" ||
      item === "mastery" ||
      item === "event_store",
  );
}

function shallowEqualBooleanRecord(
  left: Record<string, boolean>,
  right: Record<string, boolean>,
): boolean {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) return false;
  for (const key of leftKeys) {
    if (left[key] !== right[key]) return false;
  }
  return true;
}

function hydrateRequestSnapshot(
  message: SessionMessage,
  content: string,
  attachments: MessageAttachment[],
): MessageRequestSnapshot | undefined {
  const metadata = asRecord(message.metadata);
  const stored = asRecord(
    metadata?.request_snapshot ?? metadata?.requestSnapshot,
  );
  if (!stored) return undefined;

  const snapshot: MessageRequestSnapshot = {
    content: typeof stored.content === "string" ? stored.content : content,
    enabledTools: asStringArray(stored.enabledTools),
    knowledgeBases: asStringArray(stored.knowledgeBases),
    language: typeof stored.language === "string" ? stored.language : "en",
    ...(attachments.length ? { attachments } : {}),
  };

  const config = asRecord(stored.config);
  const historyReferences = asStringArray(stored.historyReferences);
  const skills = asStringArray(stored.skills);
  const memoryReferences = asMemoryReferences(stored.memoryReferences);
  const sourceReferences = normalizeSourceReferences(stored.sourceReferences);
  const llmSelection = asLLMSelection(stored.llmSelection);
  const projectId =
    typeof stored.projectId === "string" ? stored.projectId.trim() : "";
  const projectTitle =
    typeof stored.projectTitle === "string"
      ? stored.projectTitle.trim()
      : "";

  if (config && Object.keys(config).length) snapshot.config = config;
  if (historyReferences.length) snapshot.historyReferences = historyReferences;
  if (sourceReferences.length) snapshot.sourceReferences = sourceReferences;
  if (projectId) snapshot.projectId = projectId;
  if (projectTitle) snapshot.projectTitle = projectTitle;
  if (skills.length) snapshot.skills = skills;
  if (memoryReferences.length) snapshot.memoryReferences = memoryReferences;
  if (llmSelection) snapshot.llmSelection = llmSelection;
  return snapshot;
}

export function UnifiedChatProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [sessionUnreadReplies, setSessionUnreadReplies] = useState<
    Record<string, boolean>
  >({});
  const stateRef = useRef(initialState);
  const runnersRef = useRef<
    Map<
      string,
      {
        key: string;
        client: UnifiedWSClient;
      }
    >
  >(new Map());
  const draftCounterRef = useRef(0);
  const retryTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  const subscribedTurnsRef = useRef<Map<string, string>>(new Map());
  // Tracks in-flight regenerate requests so we can restore the popped
  // assistant message if the server rejects the request (e.g. ``regenerate_busy``
  // or ``nothing_to_regenerate``). Keyed by session entry key.
  const pendingRegenerateRef = useRef<Map<string, MessageItem>>(new Map());

  useLayoutEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(
    () => () => {
      runnersRef.current.forEach(({ client }) => client.disconnect());
      runnersRef.current.clear();
      subscribedTurnsRef.current.clear();
      retryTimersRef.current.forEach((id) => clearTimeout(id));
      retryTimersRef.current.clear();
    },
    [],
  );

  const makeDraftKey = useCallback(() => {
    draftCounterRef.current += 1;
    return `draft_${Date.now()}_${draftCounterRef.current}`;
  }, []);

  const hydrateMessages = useCallback(
    (messages: SessionMessage[]): MessageItem[] => {
      return messages
        .filter((message) => message.role !== "system")
        .map((message) => {
          const raw = normalizeMessageContent(message.content as unknown);
          const attachments = hydrateMessageAttachments(message.attachments);
          const requestSnapshot = hydrateRequestSnapshot(
            message,
            raw,
            attachments,
          );
          return {
            role: message.role,
            content:
              message.role === "assistant"
                ? normalizeMarkdownForDisplay(raw)
                : raw,
            events: Array.isArray(message.events) ? message.events : [],
            attachments,
            ...(requestSnapshot ? { requestSnapshot } : {}),
          };
        });
    },
    [],
  );

  const moveRunner = useCallback((oldKey: string, newKey: string) => {
    if (oldKey === newKey) return;
    const runner = runnersRef.current.get(oldKey);
    if (!runner) return;
    runnersRef.current.delete(oldKey);
    runner.key = newKey;
    runnersRef.current.set(newKey, runner);
  }, []);

  const handleRunnerEvent = useCallback(
    (runnerKey: string, event: StreamEvent) => {
      const runner = runnersRef.current.get(runnerKey);
      const effectiveKey = runner?.key || runnerKey;
      if (event.type === "session") {
        const sessionId =
          (event.metadata as { session_id?: string } | undefined)?.session_id ||
          event.session_id ||
          "";
        const turnId =
          (event.metadata as { turn_id?: string } | undefined)?.turn_id ||
          event.turn_id ||
          null;
        if (sessionId) {
          dispatch({
            type: "BIND_SERVER_SESSION",
            key: effectiveKey,
            sessionId,
            turnId,
          });
          moveRunner(effectiveKey, sessionId);
        }
        return;
      }
      if (event.type === "done") {
        const status = String(
          (event.metadata as { status?: string } | undefined)?.status ||
            "completed",
        );
        dispatch({
          type: "STREAM_END",
          key: effectiveKey,
          status: (status as SessionRuntimeStatus) || "completed",
          turnId: event.turn_id || null,
        });
        pendingRegenerateRef.current.delete(effectiveKey);
        subscribedTurnsRef.current.delete(effectiveKey);
        const runner = runnersRef.current.get(effectiveKey);
        runner?.client.disconnect();
        runnersRef.current.delete(effectiveKey);
        return;
      }
      dispatch({ type: "STREAM_EVENT", key: effectiveKey, event });
      if (
        event.type === "error" &&
        Boolean(
          (event.metadata as { turn_terminal?: boolean } | undefined)
            ?.turn_terminal,
        )
      ) {
        const reason = String(
          (event.metadata as { reason?: string } | undefined)?.reason || "",
        );
        // Pre-flight regenerate rejections never mutate server state, so we
        // roll back the optimistic POP_LAST_ASSISTANT/STREAM_START placeholder
        // to keep the transcript in sync with the server.
        if (
          reason === "regenerate_busy" ||
          reason === "nothing_to_regenerate"
        ) {
          const stash = pendingRegenerateRef.current.get(effectiveKey);
          if (stash) {
            dispatch({
              type: "RESTORE_ASSISTANT",
              key: effectiveKey,
              message: stash,
            });
          }
        }
        pendingRegenerateRef.current.delete(effectiveKey);
        subscribedTurnsRef.current.delete(effectiveKey);
        const status = String(
          (event.metadata as { status?: string } | undefined)?.status ||
            "failed",
        );
        dispatch({
          type: "STREAM_END",
          key: effectiveKey,
          status: status as SessionRuntimeStatus,
          turnId: event.turn_id || null,
        });
      }
    },
    [moveRunner],
  );

  const ensureRunner = useCallback(
    (key: string) => {
      const existing = runnersRef.current.get(key);
      if (existing) {
        const session = stateRef.current.sessions[key];
        if (session) {
          existing.client.setResumeState(session.activeTurnId, session.lastSeq);
        }
        if (!existing.client.connected) existing.client.connect();
        return existing;
      }
      const record = {
        key,
        client: new UnifiedWSClient(
          (event) => handleRunnerEvent(record.key, event),
          () => {
            const session = stateRef.current.sessions[record.key];
            if (session?.isStreaming) {
              dispatch({
                type: "STREAM_END",
                key: record.key,
                status: "failed",
              });
            }
          },
        ),
      };
      runnersRef.current.set(key, record);
      record.client.connect();
      return record;
    },
    [handleRunnerEvent],
  );

  const sendThroughRunner = useCallback(
    function dispatchToRunner(key: string, msg: ChatMessage, attempt = 0) {
      const runner = ensureRunner(key);
      if (!runner.client.connected) {
        if (attempt >= 10) {
          console.error("WebSocket failed to connect after retries");
          dispatch({ type: "STREAM_END", key, status: "failed" });
          return;
        }
        const timerId = setTimeout(() => {
          retryTimersRef.current.delete(timerId);
          dispatchToRunner(key, msg, attempt + 1);
        }, 200);
        retryTimersRef.current.add(timerId);
        return;
      }
      runner.client.send(msg);
    },
    [ensureRunner],
  );

  const loadSession = useCallback(
    async (sessionId: string) => {
      const session = await getSession(sessionId);
      const activeTurn = Array.isArray(session.active_turns)
        ? session.active_turns[0]
        : undefined;
      dispatch({
        type: "LOAD_SESSION",
        key: session.session_id || session.id,
        sessionId: session.session_id || session.id,
        messages: hydrateMessages(session.messages ?? []),
        activeTurnId: activeTurn?.turn_id || activeTurn?.id || null,
        status:
          (session.status as SessionRuntimeStatus | undefined) ||
          (activeTurn ? "running" : "idle"),
        tools: Array.isArray(session.preferences?.tools)
          ? session.preferences.tools
          : [],
        knowledgeBases: Array.isArray(session.preferences?.knowledge_bases)
          ? session.preferences.knowledge_bases
          : [],
        llmSelection: asLLMSelection(session.preferences?.llm_selection),
        // The Settings language is global UI state. Historical sessions may
        // have stale persisted preferences, so new turns follow the current
        // app language rather than the language saved when the session began.
        language: readStoredLanguage(),
      });
      if (activeTurn?.turn_id || activeTurn?.id) {
        const key = session.session_id || session.id;
        const turnId = activeTurn.turn_id || activeTurn.id;
        if (
          turnId &&
          (session.status === "running" || activeTurn) &&
          subscribedTurnsRef.current.get(key) !== turnId
        ) {
          subscribedTurnsRef.current.set(key, turnId);
          sendThroughRunner(key, {
            type: "subscribe_turn",
            turn_id: turnId,
            after_seq: 0,
          });
        }
      }
    },
    [hydrateMessages, sendThroughRunner],
  );

  const selectedSessionIdForStorage =
    state.selectedKey && state.sessions[state.selectedKey]
      ? state.sessions[state.selectedKey].sessionId
      : null;

  useEffect(() => {
    if (typeof window === "undefined") return;
    writeStoredActiveSessionId(selectedSessionIdForStorage ?? null);
  }, [selectedSessionIdForStorage]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const syncLanguage = (language: string | null | undefined) => {
      dispatch({ type: "SET_LANGUAGE", lang: normalizeLanguage(language) });
    };
    const onLanguage = (event: Event) => {
      const detail = (event as CustomEvent<{ language?: string }>).detail;
      syncLanguage(detail?.language);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === LANGUAGE_STORAGE_KEY) syncLanguage(event.newValue);
    };

    window.addEventListener(LANGUAGE_EVENT, onLanguage);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(LANGUAGE_EVENT, onLanguage);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  // URL is now the source of truth for session loading.
  // Chat pages load sessions based on URL params; no sessionStorage restore needed.
  // Initialize a draft session so the provider always has a selected key.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!state.selectedKey) {
      dispatch({ type: "NEW_SESSION", key: makeDraftKey() });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Idle timeout: if a streaming session receives no events for 60s, auto-fail it.
  useEffect(() => {
    const IDLE_TIMEOUT_MS = 60_000;
    const CHECK_INTERVAL_MS = 10_000;

    const timer = setInterval(() => {
      const current = stateRef.current;
      for (const [key, session] of Object.entries(current.sessions)) {
        if (!session.isStreaming) continue;
        if (Date.now() - session.updatedAt <= IDLE_TIMEOUT_MS) continue;

        dispatch({
          type: "STREAM_EVENT",
          key,
          event: {
            type: "error",
            source: "client",
            stage: "",
            content:
              "Connection timed out — no response received for 60 seconds.",
            metadata: { turn_terminal: true, status: "failed" },
            timestamp: Date.now() / 1000,
          },
        });
        dispatch({ type: "STREAM_END", key, status: "failed" });

        const runner = runnersRef.current.get(key);
        if (runner) {
          runner.client.disconnect();
          runnersRef.current.delete(key);
        }
        subscribedTurnsRef.current.delete(key);
      }
    }, CHECK_INTERVAL_MS);

    return () => clearInterval(timer);
  }, []);

  const sendMessage = useCallback(
    (
      content: string,
      attachments?: OutgoingAttachment[],
      config?: Record<string, unknown>,
      historyReferences?: HistoryReferencePayload,
      options?: SendMessageOptions,
      skills?: string[],
      memoryReferences?: MemoryReferencePayload,
    ) => {
      const msgAttachments = attachments?.map((a) => ({
        type: a.type,
        filename: a.filename,
        base64: a.base64,
        url: a.url,
        mime_type: a.mime_type,
      }));
      const currentState = stateRef.current;
      let key = currentState.selectedKey;
      if (!key) {
        key = makeDraftKey();
        dispatch({ type: "NEW_SESSION", key });
      }
      const session = currentState.sessions[key] ?? createSessionEntry(key);
      const replaySnapshot = options?.requestSnapshotOverride;
      const effectiveTools =
        replaySnapshot?.enabledTools ?? session.enabledTools;
      const effectiveKnowledgeBases =
        replaySnapshot?.knowledgeBases ?? session.knowledgeBases;
      const effectiveLLMSelection =
        replaySnapshot && "llmSelection" in replaySnapshot
          ? (replaySnapshot.llmSelection ?? null)
          : session.llmSelection;
      const effectiveLanguage =
        replaySnapshot?.language ?? readStoredLanguage();
      const shouldSendKnowledgeBases = effectiveTools.includes("rag");
      const effectiveSkills = replaySnapshot?.skills ?? skills;
      const effectiveMemoryReferences =
        replaySnapshot?.memoryReferences ?? memoryReferences;
      const effectiveSourceReferences =
        replaySnapshot?.sourceReferences ?? options?.sourceReferences;
      const effectiveProjectId = replaySnapshot?.projectId ?? options?.projectId;
      const effectiveProjectTitle =
        replaySnapshot?.projectTitle ?? options?.projectTitle;
      const requestSnapshot: MessageRequestSnapshot = replaySnapshot ?? {
        content,
        enabledTools: [...effectiveTools],
        knowledgeBases: shouldSendKnowledgeBases
          ? [...effectiveKnowledgeBases]
          : [],
        language: effectiveLanguage,
        ...(msgAttachments?.length ? { attachments: msgAttachments } : {}),
        ...(config && Object.keys(config).length > 0 ? { config } : {}),
        ...(historyReferences?.length
          ? { historyReferences: [...historyReferences] }
          : {}),
        ...(effectiveSourceReferences?.length
          ? { sourceReferences: effectiveSourceReferences }
          : {}),
        ...(effectiveProjectId ? { projectId: effectiveProjectId } : {}),
        ...(effectiveProjectTitle
          ? { projectTitle: effectiveProjectTitle }
          : {}),
        ...(effectiveSkills?.length ? { skills: [...effectiveSkills] } : {}),
        ...(effectiveMemoryReferences?.length
          ? { memoryReferences: [...effectiveMemoryReferences] }
          : {}),
        ...(effectiveLLMSelection
          ? { llmSelection: effectiveLLMSelection }
          : {}),
      };
      if (options?.displayUserMessage !== false) {
        dispatch({
          type: "ADD_USER_MSG",
          key,
          content,
          attachments: msgAttachments,
          requestSnapshot,
        });
      }
      dispatch({ type: "STREAM_START", key });
      const effectiveConfig =
        options?.persistUserMessage === false
          ? { ...(config || {}), _persist_user_message: false }
          : config;
      sendThroughRunner(key, {
        type: "start_turn",
        content,
        tools: effectiveTools,
        knowledge_bases: shouldSendKnowledgeBases
          ? effectiveKnowledgeBases
          : [],
        session_id: session.sessionId,
        attachments,
        language: effectiveLanguage,
        ...(historyReferences?.length
          ? { history_references: historyReferences }
          : {}),
        ...(effectiveSourceReferences?.length
          ? { source_references: effectiveSourceReferences }
          : {}),
        ...(effectiveProjectId ? { project_id: effectiveProjectId } : {}),
        ...(effectiveProjectTitle
          ? { project_title: effectiveProjectTitle }
          : {}),
        ...(effectiveSkills?.length ? { skills: effectiveSkills } : {}),
        ...(effectiveMemoryReferences?.length
          ? { memory_references: effectiveMemoryReferences }
          : {}),
        ...(effectiveLLMSelection
          ? { llm_selection: effectiveLLMSelection }
          : {}),
        ...(effectiveConfig && Object.keys(effectiveConfig).length > 0
          ? { config: effectiveConfig }
          : {}),
      });
    },
    [makeDraftKey, sendThroughRunner],
  );

  const cancelStreamingTurn = useCallback(() => {
    const currentState = stateRef.current;
    const key = currentState.selectedKey;
    if (!key) return;
    const session = currentState.sessions[key];
    const turnId = session?.activeTurnId;
    if (!session || !turnId) return;
    const runner = runnersRef.current.get(key);
    if (runner?.client.connected) {
      runner.client.send({ type: "cancel_turn", turn_id: turnId });
      runner.client.disconnect();
      runnersRef.current.delete(key);
    }
    subscribedTurnsRef.current.delete(key);
    dispatch({ type: "STREAM_END", key, status: "cancelled" });
  }, []);

  const regenerateLastMessage = useCallback(() => {
    const currentState = stateRef.current;
    const key = currentState.selectedKey;
    if (!key) return;
    const session = currentState.sessions[key];
    if (!session || !session.sessionId) return;
    if (session.isStreaming) return;
    const lastUser = [...session.messages]
      .reverse()
      .find((m) => m.role === "user");
    if (!lastUser) return;
    // Snapshot the trailing assistant (if any) so we can put it back when the
    // server rejects the request. We intentionally keep events/attachments so
    // the restored bubble round-trips identically.
    const lastMessage = session.messages[session.messages.length - 1];
    if (lastMessage && lastMessage.role === "assistant") {
      pendingRegenerateRef.current.set(key, { ...lastMessage });
    } else {
      pendingRegenerateRef.current.delete(key);
    }
    dispatch({ type: "POP_LAST_ASSISTANT", key });
    dispatch({ type: "STREAM_START", key });
    sendThroughRunner(key, {
      type: "regenerate",
      session_id: session.sessionId,
      overrides: {
        language: readStoredLanguage(),
      },
    });
  }, [sendThroughRunner]);

  const derivedState = useMemo<ChatState>(() => {
    const current = ensureSelectedSession(state);
    return {
      sessionId: current.sessionId,
      enabledTools: current.enabledTools,
      knowledgeBases: current.knowledgeBases,
      llmSelection: current.llmSelection,
      messages: current.messages,
      isStreaming: current.isStreaming,
      currentStage: current.currentStage,
      language: current.language,
    };
  }, [state]);

  const sessionStatuses = useMemo<Record<string, SessionStatusSnapshot>>(() => {
    const entries: Record<string, SessionStatusSnapshot> = {};
    for (const session of Object.values(state.sessions)) {
      if (!session.sessionId || session.status !== "running") continue;
      entries[session.sessionId] = {
        sessionId: session.sessionId,
        status: session.status,
        activeTurnId: session.activeTurnId,
        updatedAt: session.updatedAt,
      };
    }
    return entries;
  }, [state.sessions]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const seenMap = readStoredSessionSeenMap();
    const storedUnreadMap = readStoredSessionUnreadMap();
    const nextSeenMap = { ...seenMap };
    const nextUnreadMap: Record<string, boolean> = {};
    let seenChanged = false;
    let unreadChanged = false;

    for (const session of Object.values(state.sessions)) {
      if (!session.sessionId) continue;

      if (session.sessionId === derivedState.sessionId) {
        if ((storedUnreadMap[session.sessionId] ?? false) !== false) {
          unreadChanged = true;
        }
        if ((nextSeenMap[session.sessionId] ?? 0) < session.updatedAt) {
          nextSeenMap[session.sessionId] = session.updatedAt;
          seenChanged = true;
        }
        nextUnreadMap[session.sessionId] = false;
        continue;
      }

      const lastMessage = session.messages[session.messages.length - 1];
      const hasFreshAssistantReply =
        lastMessage?.role === "assistant" &&
        normalizeMessageContent(lastMessage.content).trim().length > 0 &&
        !session.isStreaming &&
        session.updatedAt > (nextSeenMap[session.sessionId] ?? 0);

      nextUnreadMap[session.sessionId] = hasFreshAssistantReply;
      if ((storedUnreadMap[session.sessionId] ?? false) !== hasFreshAssistantReply) {
        unreadChanged = true;
      }
    }

    for (const sessionId of Object.keys(storedUnreadMap)) {
      if (!(sessionId in nextUnreadMap)) {
        unreadChanged = true;
      }
    }

    if (seenChanged) {
      writeStoredSessionSeenMap(nextSeenMap);
    }
    if (unreadChanged) {
      writeStoredSessionUnreadMap(nextUnreadMap);
    }
    setSessionUnreadReplies((current) =>
      shallowEqualBooleanRecord(current, nextUnreadMap)
        ? current
        : nextUnreadMap,
    );
  }, [derivedState.sessionId, state.sessions]);

  const setTools = useCallback((tools: string[]) => {
    dispatch({ type: "SET_TOOLS", tools });
  }, []);

  const setKBs = useCallback((kbs: string[]) => {
    dispatch({ type: "SET_KB", kbs });
  }, []);

  const setLLMSelection = useCallback((selection: LLMSelection | null) => {
    dispatch({ type: "SET_LLM_SELECTION", selection });
  }, []);

  const setLanguage = useCallback((lang: string) => {
    dispatch({ type: "SET_LANGUAGE", lang });
  }, []);

  const newSession = useCallback(() => {
    dispatch({ type: "NEW_SESSION", key: makeDraftKey() });
  }, [makeDraftKey]);

  const value: ChatContextValue = {
    state: derivedState,
    setTools,
    setKBs,
    setLLMSelection,
    setLanguage,
    sendMessage,
    cancelStreamingTurn,
    regenerateLastMessage,
    newSession,
    loadSession,
    selectedSessionId: derivedState.sessionId,
    sessionStatuses,
    sessionUnreadReplies,
    sidebarRefreshToken: state.sidebarRefreshToken,
  };

  return <ChatCtx.Provider value={value}>{children}</ChatCtx.Provider>;
}

export function useUnifiedChat() {
  const ctx = useContext(ChatCtx);
  if (!ctx)
    throw new Error("useUnifiedChat must be inside UnifiedChatProvider");
  return ctx;
}
