import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { StreamErrorNotice } from "@/components/thread/StreamErrorNotice";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import { useNanobotStream, type SendImage } from "@/hooks/useNanobotStream";
import { useSessionHistory } from "@/hooks/useSessions";
import { fetchLearningSupport, setSessionMode as persistSessionMode } from "@/lib/api";
import type { ChatSummary, GoalStateWsPayload, LearningSupportPayload, UIMessage } from "@/lib/types";
import { projectThreadMessages } from "@/lib/thread-display";
import { scrubSubagentUiMessages } from "@/lib/subagent-channel-display";
import { useClient } from "@/providers/ClientProvider";

function projectWebuiThreadMessages(messages: UIMessage[]): UIMessage[] {
  return scrubSubagentUiMessages(projectThreadMessages(messages));
}

function comparableThreadMessages(messages: UIMessage[]): UIMessage[] {
  return messages.filter((message) => message.kind !== "trace");
}

function sameComparableMessage(left: UIMessage | undefined, right: UIMessage | undefined): boolean {
  if (!left || !right) return false;
  return (
    left.role === right.role
    && left.content === right.content
    && (left.reasoning ?? "") === (right.reasoning ?? "")
    && (left.images?.length ?? 0) === (right.images?.length ?? 0)
    && (left.media?.length ?? 0) === (right.media?.length ?? 0)
  );
}

function canonicalHistoryIsBehind(canonical: UIMessage[], local: UIMessage[]): boolean {
  const canonicalComparable = comparableThreadMessages(canonical);
  const localComparable = comparableThreadMessages(local);
  if (canonicalComparable.length >= localComparable.length) return false;
  return canonicalComparable.every((message, index) =>
    sameComparableMessage(message, localComparable[index]));
}

interface ThreadShellProps {
  session: ChatSummary | null;
  title: string;
  onToggleSidebar: () => void;
  onGoHome?: () => void;
  onNewChat?: () => void;
  onCreateChat?: () => Promise<string | null>;
  onTurnEnd?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  hideSidebarToggleOnDesktop?: boolean;
}

function toModelBadgeLabel(modelName: string | null): string | null {
  if (!modelName) return null;
  const trimmed = modelName.trim();
  if (!trimmed) return null;
  const leaf = trimmed.split("/").pop() ?? trimmed;
  return leaf || trimmed;
}

function toLearningGoalLabel(
  goalState: { active?: boolean; ui_summary?: string | null; objective?: string | null } | undefined,
): string | null {
  if (!goalState?.active) return null;
  const summary = goalState.ui_summary?.trim();
  if (summary) return `Learning goal: ${summary}`;
  const objective = goalState.objective?.trim();
  if (objective) return `Learning goal: ${objective}`;
  return "Learning goal in progress";
}

function latestUserLearningIntent(messages: UIMessage[]): string | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.role !== "user") continue;
    const content = message.content.replace(/\s+/g, " ").trim();
    if (!content) continue;
    return content.length > 44 ? `${content.slice(0, 44)}...` : content;
  }
  return null;
}

function looksLikeStaleProfileGoal(value: string | undefined | null): boolean {
  const text = value?.trim() ?? "";
  if (!text) return false;
  return text.length > 60 || /我是\s*Yi|colearn|AI产品经理|理想化产品/i.test(text);
}

function goalStateForLearningIntent(
  goalState: GoalStateWsPayload | undefined,
  learningIntent: string | null,
): GoalStateWsPayload | undefined {
  if (!learningIntent) return goalState;
  if (!goalState?.active) return goalState;
  if (
    looksLikeStaleProfileGoal(goalState.ui_summary)
    || looksLikeStaleProfileGoal(goalState.objective)
  ) {
    return {
      ...goalState,
      ui_summary: learningIntent,
      objective: learningIntent,
    };
  }
  return goalState;
}

interface PendingFirstMessage {
  content: string;
  images?: SendImage[];
}

function sendOptionsForMode(mode: "chat" | "learning") {
  return { sessionMode: mode };
}

const LEARNING_PROMPT_KEYWORDS = [
  "学",
  "学习",
  "讲讲",
  "讲解",
  "带我学",
  "课程",
  "知识点",
  "复习",
  "练习",
  "learn",
  "study",
  "lesson",
];

function looksLikeLearningPrompt(content: string): boolean {
  const text = content.trim().toLowerCase();
  return text.length >= 4 && LEARNING_PROMPT_KEYWORDS.some((keyword) => text.includes(keyword));
}

const HERO_PLACEHOLDERS = [
  "\u5148\u544a\u8bc9\u6211\u4f60\u60f3\u4ece\u54ea\u91cc\u5f00\u59cb",
  "\u628a\u4f60\u7684\u5b66\u4e60\u76ee\u6807\u53d1\u7ed9\u6211",
  "\u8f93\u5165\u4e00\u53e5\u8bdd\uff0c\u6211\u6765\u5e2e\u4f60\u5c55\u5f00",
  "\u8bf4\u8bf4\u4f60\u73b0\u5728\u6700\u60f3\u5f04\u61c2\u4ec0\u4e48",
  "\u5148\u5199\u4e0b\u4f60\u60f3\u5b66\u7684\u65b9\u5411",
  "\u544a\u8bc9\u6211\u4eca\u5929\u60f3\u63a8\u8fdb\u4ec0\u4e48",
];

export function ThreadShell({
  session,
  title,
  onToggleSidebar,
  onCreateChat,
  onTurnEnd,
  theme = "light",
  onToggleTheme = () => {},
  hideSidebarToggleOnDesktop = false,
}: ThreadShellProps) {
  const { t } = useTranslation();
  const chatId = session?.chatId ?? null;
  const historyKey = session?.key ?? null;
  const {
    messages: historical,
    loading,
    hasPendingToolCalls,
    refresh: refreshHistory,
    version: historyVersion,
  } = useSessionHistory(historyKey);
  const { client, modelName, token } = useClient();
  const [booting, setBooting] = useState(false);
  const [sessionMode, setSessionMode] = useState<"chat" | "learning">("chat");
  const [learningSupport, setLearningSupport] = useState<LearningSupportPayload | null>(null);
  const [learningPromptVisible, setLearningPromptVisible] = useState(false);
  const [scrollToBottomSignal, setScrollToBottomSignal] = useState(0);
  const pendingFirstRef = useRef<PendingFirstMessage | null>(null);
  const messageCacheRef = useRef<Map<string, UIMessage[]>>(new Map());
  const prevChatIdForCacheRef = useRef<string | null>(null);
  const skipLayoutCacheRef = useRef(false);
  const appliedHistoryVersionRef = useRef<Map<string, number>>(new Map());
  const pendingCanonicalHydrateRef = useRef<Set<string>>(new Set());
  const sessionKeyByChatIdRef = useRef<Map<string, string>>(new Map());

  const initial = useMemo(() => {
    if (!chatId) return historical;
    return messageCacheRef.current.get(chatId) ?? historical;
  }, [chatId, historical]);

  const refreshLearningSupport = useCallback(async () => {
    if (!chatId) {
      setLearningSupport(null);
      return;
    }
    try {
      const support = await fetchLearningSupport(token, chatId);
      setLearningSupport(support);
    } catch {
      setLearningSupport(null);
    }
  }, [chatId, token]);

  const handleTurnEnd = useCallback(() => {
    onTurnEnd?.();
    void refreshLearningSupport();
  }, [onTurnEnd, refreshLearningSupport]);

  const {
    messages,
    isStreaming,
    runStartedAt,
    goalState,
    send,
    stop,
    setMessages,
    streamError,
    dismissStreamError,
  } = useNanobotStream(chatId, initial, hasPendingToolCalls, handleTurnEnd);

  useEffect(() => {
    if (chatId && historyKey) sessionKeyByChatIdRef.current.set(chatId, historyKey);
  }, [chatId, historyKey]);

  useEffect(() => {
    setSessionMode(session?.mode === "learning" ? "learning" : "chat");
    setLearningPromptVisible(false);
  }, [session?.chatId, session?.mode]);

  useEffect(() => {
    void refreshLearningSupport();
  }, [refreshLearningSupport, historyVersion]);

  const displayMessages = useMemo(() => projectWebuiThreadMessages(messages), [messages]);
  const learningIntent = useMemo(
    () => (sessionMode === "learning" ? latestUserLearningIntent(displayMessages) : null),
    [displayMessages, sessionMode],
  );
  const composerGoalState = useMemo(
    () => goalStateForLearningIntent(goalState, learningIntent),
    [goalState, learningIntent],
  );
  const goalHeaderLabel = useMemo(() => toLearningGoalLabel(composerGoalState), [composerGoalState]);
  const showHeroComposer = messages.length === 0 && !loading;
  const compactBlankState = theme === "dark" && !session && !loading;
  const emptyPenguinSrc = sessionMode === "learning"
    ? "/brand/colearn_penguin_study_transparent.png"
    : "/brand/colearn_penguin_question_transparent.png";

  useEffect(() => {
    if (!chatId || loading) return;
    const cached = messageCacheRef.current.get(chatId);
    const appliedVersion = appliedHistoryVersionRef.current.get(chatId) ?? 0;
    const hasPendingCanonicalHydrate = pendingCanonicalHydrateRef.current.has(chatId);
    const hasNewCanonicalHistory = hasPendingCanonicalHydrate && historyVersion > appliedVersion;
    const normalizedHistory = projectWebuiThreadMessages(historical);
    setMessages((prev) => {
      const normalizedPrev = projectWebuiThreadMessages(prev);
      const normalizedCached = cached ? projectWebuiThreadMessages(cached) : null;
      const localBaseline = normalizedCached && normalizedCached.length > normalizedPrev.length
        ? normalizedCached
        : normalizedPrev;
      if (hasNewCanonicalHistory && historical.length > 0) {
        if (canonicalHistoryIsBehind(normalizedHistory, localBaseline)) {
          return localBaseline;
        }
        pendingCanonicalHydrateRef.current.delete(chatId);
        appliedHistoryVersionRef.current.set(chatId, historyVersion);
        messageCacheRef.current.set(chatId, normalizedHistory);
        return normalizedHistory;
      }
      if (cached && cached.length > 0) return normalizedCached ?? normalizedPrev;
      if (historical.length === 0 && prev.length > 0) return normalizedPrev;
      appliedHistoryVersionRef.current.set(chatId, historyVersion);
      if (historical.length > 0) messageCacheRef.current.set(chatId, normalizedHistory);
      return normalizedHistory;
    });
  }, [chatId, historical, historyVersion, loading, setMessages]);

  useEffect(() => {
    if (!chatId) return;
    return client.onSessionUpdate((updatedChatId) => {
      if (updatedChatId !== chatId) return;
      pendingCanonicalHydrateRef.current.add(chatId);
      refreshHistory();
      void refreshLearningSupport();
    });
  }, [chatId, client, refreshHistory, refreshLearningSupport]);

  useEffect(() => {
    if (!chatId || loading) return;
    setScrollToBottomSignal((value) => value + 1);
  }, [chatId, loading, historical]);

  useEffect(() => {
    if (chatId) return;
    setMessages(projectWebuiThreadMessages(historical));
  }, [chatId, historical, setMessages]);

  useLayoutEffect(() => {
    if (chatId) {
      const prev = prevChatIdForCacheRef.current;
      if (prev && prev !== chatId) {
        messageCacheRef.current.set(prev, projectWebuiThreadMessages(messages));
        skipLayoutCacheRef.current = true;
      }
      prevChatIdForCacheRef.current = chatId;
      return;
    }
    if (prevChatIdForCacheRef.current) {
      messageCacheRef.current.set(
        prevChatIdForCacheRef.current,
        projectWebuiThreadMessages(messages),
      );
      skipLayoutCacheRef.current = true;
    }
    prevChatIdForCacheRef.current = null;
  }, [chatId, messages]);

  useEffect(() => {
    if (!chatId) return;
    if (skipLayoutCacheRef.current) {
      skipLayoutCacheRef.current = false;
      return;
    }
    if (loading) return;
    messageCacheRef.current.set(chatId, projectWebuiThreadMessages(messages));
  }, [chatId, loading, messages]);

  useEffect(() => {
    if (!chatId) return;
    const pending = pendingFirstRef.current;
    if (!pending) return;
    pendingFirstRef.current = null;
    setScrollToBottomSignal((value) => value + 1);
    send(pending.content, pending.images, sendOptionsForMode(sessionMode));
    setBooting(false);
  }, [chatId, send, sessionMode]);

  const slashCommands = useMemo(() => [], []);

  const handleSessionModeChange = useCallback(
    (mode: "chat" | "learning") => {
      setSessionMode(mode);
      setLearningPromptVisible(false);
      if (mode === "chat") setLearningSupport(null);
      if (!chatId) return;
      void persistSessionMode(token, chatId, mode)
        .then(() => {
          if (mode === "learning") void refreshLearningSupport();
        })
        .catch(() => {
          setSessionMode((current) => current);
        });
    },
    [chatId, refreshLearningSupport, token],
  );

  const handleSessionModeRequest = useCallback(
    (mode: "chat" | "learning") => {
      if (mode === "learning" && sessionMode === "chat") {
        setLearningPromptVisible(true);
        return;
      }
      handleSessionModeChange(mode);
    },
    [handleSessionModeChange, sessionMode],
  );

  const handleWelcomeSend = useCallback(
    async (content: string, images?: SendImage[]) => {
      if (booting) return;
      setBooting(true);
      pendingFirstRef.current = { content, images };
      const newId = await onCreateChat?.();
      if (!newId) {
        pendingFirstRef.current = null;
        setBooting(false);
      }
    },
    [booting, onCreateChat],
  );

  const handleThreadSend = useCallback(
    async (content: string, images?: SendImage[]) => {
      setScrollToBottomSignal((value) => value + 1);
      send(content, images, sendOptionsForMode(sessionMode));
      if (sessionMode === "chat" && looksLikeLearningPrompt(content)) {
        setLearningPromptVisible(true);
      }
      await Promise.resolve();
    },
    [send, sessionMode],
  );

  const composer = (
    <>
      {streamError ? (
        <StreamErrorNotice error={streamError} onDismiss={dismissStreamError} />
      ) : null}
      {session ? (
        <ThreadComposer
          onSend={handleThreadSend}
          disabled={!chatId}
          isStreaming={isStreaming}
          placeholder={showHeroComposer ? HERO_PLACEHOLDERS : t("thread.composer.placeholderThread")}
          modelLabel={toModelBadgeLabel(modelName)}
          variant={showHeroComposer ? "hero" : "thread"}
          slashCommands={slashCommands}
          onStop={stop}
          runStartedAt={runStartedAt}
          goalState={composerGoalState}
          sessionMode={sessionMode}
          onSessionModeChange={handleSessionModeRequest}
          learningPromptVisible={learningPromptVisible && sessionMode === "chat"}
          onLearningPromptAccept={() => handleSessionModeChange("learning")}
          onLearningPromptDismiss={() => setLearningPromptVisible(false)}
        />
      ) : (
        <ThreadComposer
          onSend={handleWelcomeSend}
          disabled={booting}
          isStreaming={isStreaming}
          placeholder={booting ? t("thread.composer.placeholderOpening") : HERO_PLACEHOLDERS}
          modelLabel={toModelBadgeLabel(modelName)}
          variant={compactBlankState ? "thread" : "hero"}
          slashCommands={slashCommands}
          runStartedAt={runStartedAt}
          goalState={composerGoalState}
          sessionMode={sessionMode}
          onSessionModeChange={handleSessionModeRequest}
          learningPromptVisible={learningPromptVisible && sessionMode === "chat"}
          onLearningPromptAccept={() => handleSessionModeChange("learning")}
          onLearningPromptDismiss={() => setLearningPromptVisible(false)}
        />
      )}
    </>
  );

  const emptyState = compactBlankState ? null : loading ? (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {t("thread.loadingConversation")}
    </div>
  ) : (
    <div className="flex w-full flex-col items-center text-center animate-in fade-in-0 slide-in-from-bottom-2 duration-500">
      <h1 className="flex items-center justify-center gap-2 text-balance text-[30px] font-normal leading-tight tracking-[0.04em] text-foreground sm:text-[36px]">
        <img
          src={emptyPenguinSrc}
          alt=""
          className="h-[1.45em] w-[1.45em] shrink-0 translate-y-[0.08em] object-contain"
          aria-hidden
          draggable={false}
        />
        {t("thread.empty.greeting")}
      </h1>
    </div>
  );

  return (
    <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
      <ThreadHeader
        title={title}
        subtitle={goalHeaderLabel}
        onToggleSidebar={onToggleSidebar}
        theme={theme}
        onToggleTheme={onToggleTheme}
        hideSidebarToggleOnDesktop={hideSidebarToggleOnDesktop}
        minimal={!session && !loading}
        titleStyle={session ? "chat" : "page"}
      />
      <ThreadViewport
        messages={displayMessages}
        isStreaming={isStreaming}
        emptyState={emptyState}
        composer={composer}
        scrollToBottomSignal={scrollToBottomSignal}
        conversationKey={historyKey}
        learningSupport={learningSupport}
        learningFocusLabel={learningIntent}
      />
    </section>
  );
}
