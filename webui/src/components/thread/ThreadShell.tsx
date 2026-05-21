import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { StreamErrorNotice } from "@/components/thread/StreamErrorNotice";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import { useNanobotStream, type SendImage } from "@/hooks/useNanobotStream";
import { useSessionHistory } from "@/hooks/useSessions";
import { fetchLearningSupport } from "@/lib/api";
import type { ChatSummary, LearningSupportPayload, UIMessage } from "@/lib/types";
import { projectThreadMessages } from "@/lib/thread-display";
import { scrubSubagentUiMessages } from "@/lib/subagent-channel-display";
import { useClient } from "@/providers/ClientProvider";

function projectWebuiThreadMessages(messages: UIMessage[]): UIMessage[] {
  return scrubSubagentUiMessages(projectThreadMessages(messages));
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

interface PendingFirstMessage {
  content: string;
  images?: SendImage[];
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
  const [learningSupport, setLearningSupport] = useState<LearningSupportPayload | null>(null);
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
    void refreshLearningSupport();
  }, [refreshLearningSupport, historyVersion]);

  const displayMessages = useMemo(() => projectWebuiThreadMessages(messages), [messages]);
  const goalHeaderLabel = useMemo(() => toLearningGoalLabel(goalState), [goalState]);
  const showHeroComposer = messages.length === 0 && !loading;

  useEffect(() => {
    if (!chatId || loading) return;
    const cached = messageCacheRef.current.get(chatId);
    const appliedVersion = appliedHistoryVersionRef.current.get(chatId) ?? 0;
    const hasPendingCanonicalHydrate = pendingCanonicalHydrateRef.current.has(chatId);
    const hasNewCanonicalHistory = hasPendingCanonicalHydrate && historyVersion > appliedVersion;
    setMessages((prev) => {
      if (hasNewCanonicalHistory && historical.length > 0) {
        pendingCanonicalHydrateRef.current.delete(chatId);
        appliedHistoryVersionRef.current.set(chatId, historyVersion);
        const normalized = projectWebuiThreadMessages(historical);
        messageCacheRef.current.set(chatId, normalized);
        return normalized;
      }
      if (cached && cached.length > 0) return projectWebuiThreadMessages(cached);
      if (historical.length === 0 && prev.length > 0) return projectWebuiThreadMessages(prev);
      appliedHistoryVersionRef.current.set(chatId, historyVersion);
      const next = projectWebuiThreadMessages(historical);
      if (historical.length > 0) messageCacheRef.current.set(chatId, next);
      return next;
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
    send(pending.content, pending.images);
    setBooting(false);
  }, [chatId, send]);

  const slashCommands = useMemo(() => [], []);

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
    (content: string, images?: SendImage[]) => {
      setScrollToBottomSignal((value) => value + 1);
      send(content, images);
    },
    [send],
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
          goalState={goalState}
        />
      ) : (
        <ThreadComposer
          onSend={handleWelcomeSend}
          disabled={booting}
          isStreaming={isStreaming}
          placeholder={booting ? t("thread.composer.placeholderOpening") : HERO_PLACEHOLDERS}
          modelLabel={toModelBadgeLabel(modelName)}
          variant="hero"
          slashCommands={slashCommands}
          runStartedAt={runStartedAt}
          goalState={goalState}
        />
      )}
    </>
  );

  const emptyState = loading ? (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {t("thread.loadingConversation")}
    </div>
  ) : (
    <div className="flex w-full flex-col items-center text-center animate-in fade-in-0 slide-in-from-bottom-2 duration-500">
      <h1 className="text-balance text-[30px] font-normal leading-tight tracking-[-0.035em] text-foreground sm:text-[36px]">
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
      />
    </section>
  );
}
