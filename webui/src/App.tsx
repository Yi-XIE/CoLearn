import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { DeleteConfirm } from "@/components/DeleteConfirm";
import { Sidebar } from "@/components/Sidebar";
import { SettingsView } from "@/components/settings/SettingsView";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { ThreadShell } from "@/components/thread/ThreadShell";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useSessions } from "@/hooks/useSessions";
import { useTheme } from "@/hooks/useTheme";
import {
  clearSavedSecret,
  deriveWsUrl,
  fetchBootstrap,
  loadSavedSecret,
  saveSecret,
} from "@/lib/bootstrap";
import {
  createKnowledgeBase,
  fetchMemorySummary,
  listKnowledgeBases,
  listKnowledgeFiles,
  listSkills,
  reindexKnowledgeBase,
  uploadKnowledgeFiles,
} from "@/lib/api";
import { NanobotClient } from "@/lib/nanobot-client";
import type {
  ChatSummary,
  KnowledgeBaseSummary,
  MemorySummaryPayload,
  SkillSummary,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { ClientProvider, useClient } from "@/providers/ClientProvider";

type BootState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "auth"; failed?: boolean }
  | {
      status: "ready";
      client: NanobotClient;
      token: string;
      modelName: string | null;
    };

const SIDEBAR_STORAGE_KEY = "nanobot-webui.sidebar";
const RESTART_STARTED_KEY = "nanobot-webui.restartStartedAt";
const SIDEBAR_WIDTH = 272;
const BRAND_NAME = "CoLearn";
const SETTINGS_TITLE = "设置";

type ShellView = "chat" | "knowledge" | "memory" | "skills" | "settings";

function AuthForm({
  failed,
  onSecret,
}: {
  failed: boolean;
  onSecret: (secret: string) => void;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const secret = value.trim();
    if (!secret) return;
    setSubmitting(true);
    onSecret(secret);
  };

  return (
    <div className="flex h-full w-full items-center justify-center px-6">
      <form onSubmit={handleSubmit} className="flex w-full max-w-sm flex-col gap-4">
        <div className="flex flex-col items-center gap-1 text-center">
          <p className="text-lg font-semibold">{t("app.auth.title")}</p>
          <p className="text-sm text-muted-foreground">{t("app.auth.hint")}</p>
        </div>
        {failed ? (
          <p className="text-center text-sm text-destructive">
            {t("app.auth.invalid")}
          </p>
        ) : null}
        <Input
          type="password"
          placeholder={t("app.auth.placeholder")}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={submitting}
          autoFocus
        />
        <Button type="submit" className="w-full" disabled={!value.trim() || submitting}>
          {t("app.auth.submit")}
        </Button>
      </form>
    </div>
  );
}

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

export default function App() {
  const { t } = useTranslation();
  const [state, setState] = useState<BootState>({ status: "loading" });

  const bootstrapWithSecret = useCallback((secret: string) => {
    let cancelled = false;
    (async () => {
      setState({ status: "loading" });
      try {
        const boot = await fetchBootstrap("", secret);
        if (cancelled) return;
        if (secret) saveSecret(secret);
        const url = deriveWsUrl(boot.ws_path, boot.token);
        const client = new NanobotClient({
          url,
          onReauth: async () => {
            try {
              const refreshed = await fetchBootstrap("", secret);
              return deriveWsUrl(refreshed.ws_path, refreshed.token);
            } catch {
              return null;
            }
          },
        });
        client.connect();
        setState({
          status: "ready",
          client,
          token: boot.token,
          modelName: boot.model_name ?? null,
        });
      } catch (e) {
        if (cancelled) return;
        const msg = (e as Error).message;
        if (msg.includes("HTTP 401") || msg.includes("HTTP 403")) {
          setState({ status: "auth", failed: true });
        } else {
          setState({ status: "error", message: msg });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const saved = loadSavedSecret();
    return bootstrapWithSecret(saved);
  }, [bootstrapWithSecret]);

  if (state.status === "loading") {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <div className="flex flex-col items-center gap-3 animate-in fade-in-0 duration-300">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-foreground/40" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-foreground/60" />
            </span>
            {t("app.loading.connecting")}
          </div>
        </div>
      </div>
    );
  }

  if (state.status === "auth") {
    return <AuthForm failed={!!state.failed} onSecret={(s) => bootstrapWithSecret(s)} />;
  }

  if (state.status === "error") {
    return (
      <div className="flex h-full w-full items-center justify-center px-4 text-center">
        <div className="flex max-w-md flex-col items-center gap-3">
          <p className="text-lg font-semibold">{t("app.error.title")}</p>
          <p className="text-sm text-muted-foreground">{state.message}</p>
          <p className="text-xs text-muted-foreground">{t("app.error.gatewayHint")}</p>
        </div>
      </div>
    );
  }

  const handleModelNameChange = (modelName: string | null) => {
    setState((current) =>
      current.status === "ready" ? { ...current, modelName } : current,
    );
  };

  const handleLogout = () => {
    if (state.status === "ready") state.client.close();
    clearSavedSecret();
    setState({ status: "auth" });
  };

  return (
    <ClientProvider client={state.client} token={state.token} modelName={state.modelName}>
      <Shell onModelNameChange={handleModelNameChange} onLogout={handleLogout} />
    </ClientProvider>
  );
}

function Shell({
  onModelNameChange,
  onLogout,
}: {
  onModelNameChange: (modelName: string | null) => void;
  onLogout: () => void;
}) {
  const { t } = useTranslation();
  const { client, token } = useClient();
  const { theme, toggle } = useTheme();
  const { sessions, loading, refresh, createChat, deleteChat } = useSessions();
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [view, setView] = useState<ShellView>("chat");
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState<boolean>(readSidebarOpen);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<{ key: string; label: string } | null>(null);
  const restartSawDisconnectRef = useRef(false);
  const [restartToast, setRestartToast] = useState<string | null>(null);
  const [isRestarting, setIsRestarting] = useState(false);

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, desktopSidebarOpen ? "1" : "0");
    } catch {
      // ignore storage errors
    }
  }, [desktopSidebarOpen]);

  const activeSession = useMemo<ChatSummary | null>(() => {
    if (!activeKey) return null;
    return sessions.find((s) => s.key === activeKey) ?? null;
  }, [sessions, activeKey]);

  const closeDesktopSidebar = useCallback(() => setDesktopSidebarOpen(false), []);
  const closeMobileSidebar = useCallback(() => setMobileSidebarOpen(false), []);

  const toggleSidebar = useCallback(() => {
    const isDesktop =
      typeof window !== "undefined" &&
      window.matchMedia("(min-width: 1024px)").matches;
    if (isDesktop) {
      setDesktopSidebarOpen((v) => !v);
    } else {
      setMobileSidebarOpen((v) => !v);
    }
  }, []);

  const onCreateChat = useCallback(async () => {
    try {
      const chatId = await createChat();
      setActiveKey(`websocket:${chatId}`);
      setView("chat");
      setMobileSidebarOpen(false);
      return chatId;
    } catch (e) {
      console.error("Failed to create chat", e);
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

  const onRestart = useCallback(() => {
    const chatId = activeSession?.chatId ?? client.defaultChatId;
    if (!chatId) return;
    restartSawDisconnectRef.current = false;
    setIsRestarting(true);
    try {
      window.localStorage.setItem(RESTART_STARTED_KEY, String(Date.now()));
    } catch {
      // ignore storage errors
    }
    client.sendMessage(chatId, "/restart");
  }, [activeSession?.chatId, client]);

  useEffect(() => {
    return client.onRuntimeModelUpdate((modelName) => onModelNameChange(modelName));
  }, [client, onModelNameChange]);

  useEffect(() => {
    return client.onStatus((status) => {
      let startedAt = 0;
      try {
        startedAt = Number(window.localStorage.getItem(RESTART_STARTED_KEY) ?? "0");
      } catch {
        startedAt = 0;
      }
      if (!startedAt) return;
      if (status !== "open") {
        restartSawDisconnectRef.current = true;
        return;
      }
      const elapsedMs = Date.now() - startedAt;
      if (!restartSawDisconnectRef.current && elapsedMs < 1500) return;
      try {
        window.localStorage.removeItem(RESTART_STARTED_KEY);
      } catch {
        // ignore storage errors
      }
      setIsRestarting(false);
      setRestartToast(t("app.restart.completed", { seconds: (elapsedMs / 1000).toFixed(1) }));
      window.setTimeout(() => setRestartToast(null), 3500);
    });
  }, [client, t]);

  const onConfirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    const key = pendingDelete.key;
    const deletingActive = activeKey === key;
    const currentIndex = sessions.findIndex((s) => s.key === key);
    const fallbackKey = deletingActive
      ? sessions[currentIndex + 1]?.key ?? sessions[currentIndex - 1]?.key ?? null
      : activeKey;
    setPendingDelete(null);
    if (deletingActive) setActiveKey(fallbackKey);
    try {
      await deleteChat(key);
    } catch (e) {
      if (deletingActive) setActiveKey(key);
      console.error("Failed to delete session", e);
    }
  }, [activeKey, deleteChat, pendingDelete, sessions]);

  const headerTitle = activeSession
    ? activeSession.title ||
      activeSession.preview ||
      t("chat.fallbackTitle", { id: activeSession.chatId.slice(0, 6) })
    : BRAND_NAME;

  useEffect(() => {
    if (view === "settings") {
      document.title = `${SETTINGS_TITLE} - ${BRAND_NAME}`;
      return;
    }
    if (view === "knowledge") {
      document.title = `知识花园 - ${BRAND_NAME}`;
      return;
    }
    if (view === "memory") {
      document.title = `记忆 - ${BRAND_NAME}`;
      return;
    }
    if (view === "skills") {
      document.title = `技能 - ${BRAND_NAME}`;
      return;
    }
    document.title = activeSession ? `${headerTitle} - ${BRAND_NAME}` : BRAND_NAME;
  }, [activeSession, headerTitle, view, t]);

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
              onRestart={onRestart}
              isRestarting={isRestarting}
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

      {restartToast ? (
        <div
          role="status"
          className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-full border border-border/70 bg-popover px-4 py-2 text-sm font-medium text-popover-foreground shadow-lg"
        >
          {restartToast}
        </div>
      ) : null}
    </div>
  );
}

function PanelView({
  title,
  subtitle,
  children,
  onToggleSidebar,
  theme,
  onToggleTheme,
  hideSidebarToggleOnDesktop,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  onToggleSidebar: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideSidebarToggleOnDesktop?: boolean;
}) {
  return (
    <section className="absolute inset-0 flex min-h-0 flex-1 flex-col overflow-hidden">
      <ThreadHeader
        title={title}
        subtitle={subtitle}
        onToggleSidebar={onToggleSidebar}
        theme={theme}
        onToggleTheme={onToggleTheme}
        hideSidebarToggleOnDesktop={hideSidebarToggleOnDesktop}
        titleStyle="page"
      />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto flex max-w-5xl flex-col gap-4">{children}</div>
      </div>
    </section>
  );
}

function InfoCard({
  title,
  body,
  actions,
}: {
  title: string;
  body: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border/50 bg-card/85 p-5 shadow-[0_16px_50px_rgba(15,23,42,0.06)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-semibold text-foreground">{title}</div>
          <div className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{body}</div>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return <div className="text-sm text-muted-foreground">{text}</div>;
}

function KnowledgeGardenPanel({
  token,
  ...panelProps
}: {
  token: string;
  onToggleSidebar: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideSidebarToggleOnDesktop?: boolean;
}) {
  const [libraries, setLibraries] = useState<KnowledgeBaseSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [createFiles, setCreateFiles] = useState<File[]>([]);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);

  const refreshKnowledge = useCallback(async () => {
    setLoading(true);
    try {
      const bases = await listKnowledgeBases(token);
      const withFiles = await Promise.all(
        bases.map(async (base) => ({
          ...base,
          files: await listKnowledgeFiles(token, base.id).catch(() => []),
        })),
      );
      setLibraries(withFiles);
      setSelectedId((current) => current || withFiles[0]?.id || "");
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refreshKnowledge();
  }, [refreshKnowledge]);

  const selected = libraries.find((item) => item.id === selectedId) ?? null;

  const handleCreate = async () => {
    const name = draftName.trim();
    if (!name) return;
    setBusy("create");
    try {
      await createKnowledgeBase(token, { name, files: createFiles });
      setDraftName("");
      setCreateFiles([]);
      await refreshKnowledge();
      setSelectedId(name);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const handleUpload = async () => {
    if (!selected || uploadFiles.length === 0) return;
    setBusy("upload");
    try {
      await uploadKnowledgeFiles(token, { name: selected.id, files: uploadFiles });
      setUploadFiles([]);
      await refreshKnowledge();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const handleReindex = async () => {
    if (!selected) return;
    setBusy("reindex");
    try {
      await reindexKnowledgeBase(token, selected.id);
      await refreshKnowledge();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <PanelView title="知识花园" subtitle="资料库、索引状态与检索入口都会在这里汇总。" {...panelProps}>
      {error ? <InfoCard title="当前状态" body={error} /> : null}
      <InfoCard
        title="新建资料库"
        body={
          <div className="space-y-3">
            <Input
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              placeholder="输入资料库名称"
              className="max-w-sm"
            />
            <input
              type="file"
              multiple
              onChange={(event) => setCreateFiles(Array.from(event.target.files ?? []))}
            />
            <div className="text-xs text-muted-foreground">
              支持上传 Markdown、文本、PDF、Office 文档，先建立最小可用闭环。
            </div>
          </div>
        }
        actions={
          <Button
            size="sm"
            onClick={handleCreate}
            disabled={busy === "create" || !draftName.trim()}
            className="rounded-full"
          >
            {busy === "create" ? "创建中..." : "创建"}
          </Button>
        }
      />

      <InfoCard
        title="资料库概览"
        body={
          loading ? (
            <EmptyHint text="正在读取知识花园..." />
          ) : libraries.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2">
              {libraries.map((library) => {
                const active = library.id === selectedId;
                return (
                  <button
                    key={library.id}
                    type="button"
                    onClick={() => setSelectedId(library.id)}
                    className={cn(
                      "rounded-2xl border px-4 py-3 text-left transition-colors",
                      active
                        ? "border-foreground/20 bg-muted/70"
                        : "border-border/50 hover:bg-muted/40",
                    )}
                  >
                    <div className="text-sm font-semibold text-foreground">{library.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {library.source_count} 份资料 · {library.status} · {library.provider ?? "LightRAG"}
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyHint text="还没有资料库。创建一个新的知识花园后，这里会显示索引和文件清单。" />
          )
        }
      />

      <InfoCard
        title="当前资料库"
        body={
          selected ? (
            <div className="space-y-4">
              <div className="text-sm text-foreground">
                <span className="font-medium">{selected.name}</span>
                <span className="ml-3 text-muted-foreground">
                  共 {selected.files?.length ?? 0} 个文件，状态 {selected.status}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  type="file"
                  multiple
                  onChange={(event) => setUploadFiles(Array.from(event.target.files ?? []))}
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleUpload}
                  disabled={busy === "upload" || uploadFiles.length === 0}
                  className="rounded-full"
                >
                  {busy === "upload" ? "上传中..." : "上传资料"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleReindex}
                  disabled={busy === "reindex"}
                  className="rounded-full"
                >
                  {busy === "reindex" ? "索引中..." : "重建索引"}
                </Button>
              </div>
              {selected.files && selected.files.length > 0 ? (
                <div className="space-y-2">
                  {selected.files.map((file) => (
                    <div
                      key={file.path}
                      className="flex items-center justify-between rounded-xl border border-border/40 px-3 py-2 text-sm"
                    >
                      <span className="truncate pr-4">{file.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {Math.max(1, Math.round(file.size / 1024))} KB
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyHint text="当前资料库还没有文件。" />
              )}
            </div>
          ) : (
            <EmptyHint text="先在上面选择一个资料库，这里会显示文件、上传和索引操作。" />
          )
        }
      />
    </PanelView>
  );
}

function MemoryPanel({
  token,
  ...panelProps
}: {
  token: string;
  onToggleSidebar: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideSidebarToggleOnDesktop?: boolean;
}) {
  const [payload, setPayload] = useState<MemorySummaryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchMemorySummary(token)
      .then((result) => {
        if (!cancelled) {
          setPayload(result);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <PanelView title="记忆" subtitle="学习连续性、关键事实和近期回写都会在这里沉淀。" {...panelProps}>
      <InfoCard
        title="当前连续性"
        body={
          loading ? (
            <EmptyHint text="正在整理记忆..." />
          ) : payload ? (
            payload.current_continuity || "当前还没有新的连续性提示。"
          ) : (
            error ?? "记忆暂时不可用。"
          )
        }
      />
      <InfoCard
        title="长期记忆"
        body={
          payload?.long_term_facts?.length ? (
            <div className="space-y-2">
              {payload.long_term_facts.map((item, index) => (
                <div key={`${item.label}-${index}`} className="rounded-xl border border-border/40 px-3 py-2">
                  <div className="text-sm text-foreground">{item.label}</div>
                  <div className="text-xs text-muted-foreground">{item.detail}</div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyHint text="还没有沉淀下来的长期事实。" />
          )
        }
      />
      <InfoCard
        title="阻塞点"
        body={
          payload?.blockers?.length ? (
            <div className="space-y-2">
              {payload.blockers.map((item, index) => (
                <div key={`${item.label}-${index}`} className="rounded-xl border border-border/40 px-3 py-2">
                  <div className="text-sm text-foreground">{item.label}</div>
                  <div className="text-xs text-muted-foreground">{item.detail}</div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyHint text="当前没有新的关键阻塞点。" />
          )
        }
      />
      <InfoCard
        title="近期回写"
        body={
          payload?.recent_events?.length ? (
            <div className="space-y-2">
              {payload.recent_events.map((item) => (
                <div key={item.event_id} className="rounded-xl border border-border/40 px-3 py-2">
                  <div className="text-sm text-foreground">{item.summary || item.kind}</div>
                  <div className="text-xs text-muted-foreground">{item.kind}</div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyHint text="最近还没有新的学习回写事件。" />
          )
        }
      />
    </PanelView>
  );
}

function SkillsPanel({
  token,
  ...panelProps
}: {
  token: string;
  onToggleSidebar: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideSidebarToggleOnDesktop?: boolean;
}) {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listSkills(token)
      .then((result) => {
        if (!cancelled) {
          setSkills(result);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <PanelView title="技能" subtitle="把可复用能力、学习助手和工作流动作收进一个地方。" {...panelProps}>
      <InfoCard
        title="可用技能"
        body={
          loading ? (
            <EmptyHint text="正在加载技能..." />
          ) : error ? (
            error
          ) : skills.length ? (
            <div className="grid gap-3 md:grid-cols-2">
              {skills.map((skill) => (
                <div key={skill.name} className="rounded-2xl border border-border/40 px-4 py-3">
                  <div className="text-sm font-semibold text-foreground">{skill.name}</div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    {skill.description || "这张技能卡已经接入运行时，可以在学习会话里被调用。"}
                  </div>
                  {skill.tags.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {skill.tags.map((tag) => (
                        <span
                          key={`${skill.name}-${tag}`}
                          className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <EmptyHint text="当前还没有技能卡。后面接入学习助手和工作流技能后，这里会变成真实能力面。" />
          )
        }
      />
    </PanelView>
  );
}
