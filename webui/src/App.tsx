import {
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type WheelEvent as ReactWheelEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import {
  BookOpen,
  Check,
  ChevronDown,
  FileText,
  Image,
  Loader2,
  Network,
  Pencil,
  Plus,
  Puzzle,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

import { DeleteConfirm } from "@/components/DeleteConfirm";
import { Sidebar } from "@/components/Sidebar";
import { SettingsView } from "@/components/settings/SettingsView";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { ThreadShell } from "@/components/thread/ThreadShell";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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
  clearMemoryDocument,
  createKnowledgeBase,
  fetchKnowledgeGraph,
  fetchMemorySummary,
  listKnowledgeBases,
  listKnowledgeFiles,
  listSkills,
  refreshMemoryDocument,
  reindexKnowledgeBase,
  updateMemoryDocument,
  uploadKnowledgeFiles,
} from "@/lib/api";
import { NanobotClient } from "@/lib/nanobot-client";
import type {
  ChatSummary,
  KnowledgeBaseSummary,
  KnowledgeGraphEdge as ApiKnowledgeGraphEdge,
  KnowledgeGraphNode as ApiKnowledgeGraphNode,
  KnowledgeGraphPayload,
  MemoryDocPayload,
  MemoryDocumentName,
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
type KnowledgeGardenMode = "graph" | "library";

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
  const [mode, setMode] = useState<KnowledgeGardenMode>("graph");
  const [knowledgeVersion, setKnowledgeVersion] = useState(0);
  const [graphPayload, setGraphPayload] = useState<KnowledgeGraphPayload | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);

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
      setSelectedId((current) =>
        current && withFiles.some((base) => base.id === current)
          ? current
          : withFiles.find((base) => (base.files?.length ?? 0) > 0 || base.source_count > 0)?.id || withFiles[0]?.id || "",
      );
      setKnowledgeVersion((current) => current + 1);
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

  useEffect(() => {
    if (mode !== "graph" || !selectedId) {
      setGraphPayload(null);
      setGraphLoading(false);
      return;
    }
    let cancelled = false;
    setGraphLoading(true);
    fetchKnowledgeGraph(token, selectedId)
      .then((payload) => {
        if (!cancelled) {
          setGraphPayload(payload.nodes.length > 0 ? payload : null);
        }
      })
      .catch(() => {
        if (!cancelled) setGraphPayload(null);
      })
      .finally(() => {
        if (!cancelled) setGraphLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [knowledgeVersion, mode, selectedId, token]);

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
    <PanelView title="知识花园" subtitle="像 Obsidian 一样查看资料、概念与学习线索之间的关系。" {...panelProps}>
      {error ? <InfoCard title="当前状态" body={error} /> : null}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/60 bg-card/80 p-3 shadow-[0_16px_50px_rgba(15,23,42,0.05)]">
        <div className="inline-flex rounded-full border border-border/60 bg-muted/40 p-1">
          <Button
            type="button"
            size="sm"
            variant={mode === "graph" ? "default" : "ghost"}
            onClick={() => setMode("graph")}
            className="h-8 rounded-full gap-2"
          >
            <Network className="h-4 w-4" />
            图谱
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === "library" ? "default" : "ghost"}
            onClick={() => setMode("library")}
            className="h-8 rounded-full gap-2"
          >
            <FileText className="h-4 w-4" />
            资料
          </Button>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void refreshKnowledge()}
          disabled={loading}
          className="h-8 rounded-full gap-2"
        >
          <RefreshCw className={cn("h-4 w-4", loading ? "animate-spin" : "")} />
          刷新
        </Button>
      </div>

      {mode === "graph" ? (
        <KnowledgeGraphView
          libraries={libraries}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={loading || graphLoading}
          graphPayload={graphPayload}
        />
      ) : null}

      {mode === "library" ? (
        <>
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
                  className="rounded-full gap-2"
                >
                  <Upload className="h-4 w-4" />
                  {busy === "upload" ? "上传中..." : "上传资料"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleReindex}
                  disabled={busy === "reindex"}
                  className="rounded-full gap-2"
                >
                  <RefreshCw className={cn("h-4 w-4", busy === "reindex" ? "animate-spin" : "")} />
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
        </>
      ) : null}
    </PanelView>
  );
}

type KnowledgeGraphVisualNode = {
  id: string;
  label: string;
  kind: ApiKnowledgeGraphNode["kind"];
  metadata?: Record<string, unknown>;
  x: number;
  y: number;
  size: number;
  libraryId?: string;
};

type KnowledgeGraphVisualEdge = {
  id: string;
  from: string;
  to: string;
  kind: ApiKnowledgeGraphEdge["kind"];
  metadata?: Record<string, unknown>;
};

const CONCEPT_HINTS = [
  "machine",
  "learning",
  "dataset",
  "feature",
  "label",
  "model",
  "training",
  "prediction",
  "regression",
  "classification",
  "evaluation",
  "lightrag",
  "agent",
  "state",
  "science",
  "math",
  "ai",
  "ml",
];

function titleCaseToken(value: string): string {
  if (!value) return value;
  if (value.length <= 3) return value.toUpperCase();
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

function graphNodeLabel(value: string, kind: KnowledgeGraphVisualNode["kind"]): string {
  const label = kind === "file" ? value.replace(/\.[^.]+$/, "") : value;
  return label.length > 34 ? `${label.slice(0, 33)}…` : label;
}

function conceptHintsForFile(fileName: string): string[] {
  const normalized = fileName
    .replace(/\.[^.]+$/, "")
    .split(/[^a-zA-Z0-9\u4e00-\u9fa5]+/)
    .filter(Boolean);
  const english = normalized
    .map((token) => token.toLowerCase())
    .filter((token) => CONCEPT_HINTS.includes(token));
  const chinese = normalized.filter((token) => /[\u4e00-\u9fa5]/.test(token)).slice(0, 2);
  return Array.from(new Set([...english.map(titleCaseToken), ...chinese])).slice(0, 3);
}

function buildKnowledgeGraph(libraries: KnowledgeBaseSummary[]): {
  nodes: KnowledgeGraphVisualNode[];
  edges: KnowledgeGraphVisualEdge[];
} {
  const nodes: KnowledgeGraphVisualNode[] = [];
  const edges: KnowledgeGraphVisualEdge[] = [];
  const conceptIndex = new Map<string, string>();
  const centerX = 580;
  const centerY = 320;
  const libraryRadius = 210;
  const fileRadius = 150;

  libraries.forEach((library, libraryIndex) => {
    const angle = (Math.PI * 2 * libraryIndex) / Math.max(libraries.length, 1) - Math.PI / 2;
    const libraryX = centerX + Math.cos(angle) * libraryRadius;
    const libraryY = centerY + Math.sin(angle) * libraryRadius;
    const libraryNodeId = `library:${library.id}`;
    nodes.push({
      id: libraryNodeId,
      label: library.name || library.id,
      kind: "library",
      metadata: {
        library_id: library.id,
        status: library.status,
        provider: library.provider,
      },
      x: libraryX,
      y: libraryY,
      size: graphNodeSize("library"),
      libraryId: library.id,
    });

    const files = (library.files ?? []).slice(0, 7);
    files.forEach((file, fileIndex) => {
      const fileAngle =
        angle + (files.length === 1 ? 0 : (fileIndex - (files.length - 1) / 2) * 0.46);
      const fileNodeId = `file:${library.id}:${file.path}`;
      const fileX = libraryX + Math.cos(fileAngle) * fileRadius;
      const fileY = libraryY + Math.sin(fileAngle) * fileRadius;
      nodes.push({
        id: fileNodeId,
        label: file.name,
        kind: "file",
        metadata: {
          library_id: library.id,
          path: file.path,
          size: file.size,
          modified: file.modified,
          mime_type: file.mime_type,
        },
        x: fileX,
        y: fileY,
        size: graphNodeSize("file"),
        libraryId: library.id,
      });
      edges.push({
        id: `edge:contains:${libraryNodeId}:${fileNodeId}`,
        from: libraryNodeId,
        to: fileNodeId,
        kind: "contains",
        metadata: { library_id: library.id },
      });

      conceptHintsForFile(file.name).forEach((concept, conceptIndexForFile) => {
        const conceptKey = concept.toLowerCase();
        let conceptNodeId = conceptIndex.get(conceptKey);
        if (!conceptNodeId) {
          conceptNodeId = `concept:${conceptKey}`;
          conceptIndex.set(conceptKey, conceptNodeId);
          const conceptAngle =
            fileAngle + 0.72 + conceptIndexForFile * 0.36 + conceptIndex.size * 0.17;
          nodes.push({
            id: conceptNodeId,
            label: concept,
            kind: "concept",
            metadata: { source: "frontend-fallback" },
            x: centerX + Math.cos(conceptAngle) * 345,
            y: centerY + Math.sin(conceptAngle) * 235,
            size: graphNodeSize("concept"),
          });
        }
        edges.push({
          id: `edge:mentions:${fileNodeId}:${conceptNodeId}`,
          from: fileNodeId,
          to: conceptNodeId,
          kind: "mentions",
          metadata: { library_id: library.id, source: "frontend-fallback" },
        });
      });
    });
  });

  return { nodes, edges };
}

function graphNodeSize(kind: ApiKnowledgeGraphNode["kind"]): number {
  if (kind === "library") return 18;
  if (kind === "file") return 7;
  return 5;
}

function graphNodeColor(kind: ApiKnowledgeGraphNode["kind"]): string {
  if (kind === "library") return "#2563eb";
  if (kind === "file") return "#0ea5e9";
  if (kind === "lesson") return "#4f46e5";
  if (kind === "exercise") return "#f59e0b";
  if (kind === "evidence") return "#10b981";
  return "#f97316";
}

function graphEdgeColor(kind: ApiKnowledgeGraphEdge["kind"]): string {
  if (kind === "contains") return "rgba(37, 99, 235, 0.24)";
  if (kind === "supports") return "rgba(16, 185, 129, 0.28)";
  if (kind === "practices") return "rgba(245, 158, 11, 0.28)";
  return "rgba(100, 116, 139, 0.22)";
}

function metadataString(metadata: Record<string, unknown> | undefined, key: string): string | undefined {
  const value = metadata?.[key];
  return typeof value === "string" && value.trim() ? value : undefined;
}

function graphLibraryIdForNode(node: ApiKnowledgeGraphNode): string | undefined {
  return metadataString(node.metadata, "library_id") ?? (node.kind === "library" ? node.id.replace(/^library:/, "") : undefined);
}

function layoutKnowledgeGraphPayload(payload: KnowledgeGraphPayload): {
  nodes: KnowledgeGraphVisualNode[];
  edges: KnowledgeGraphVisualEdge[];
} {
  const centerX = 580;
  const centerY = 320;
  const libraryRadius = 180;
  const fileRadius = 155;
  const relatedRadius = 92;
  const placed = new Set<string>();
  const visualById = new Map<string, KnowledgeGraphVisualNode>();

  payload.nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(payload.nodes.length, 1) - Math.PI / 2;
    visualById.set(node.id, {
      id: node.id,
      label: node.label,
      kind: node.kind,
      metadata: node.metadata,
      x: centerX + Math.cos(angle) * 360,
      y: centerY + Math.sin(angle) * 245,
      size: graphNodeSize(node.kind),
      libraryId: graphLibraryIdForNode(node),
    });
  });

  const outgoing = new Map<string, ApiKnowledgeGraphEdge[]>();
  payload.edges.forEach((edge) => {
    const edges = outgoing.get(edge.source) ?? [];
    edges.push(edge);
    outgoing.set(edge.source, edges);
  });

  const place = (id: string, x: number, y: number) => {
    const node = visualById.get(id);
    if (!node) return;
    node.x = Math.max(42, Math.min(1118, x));
    node.y = Math.max(52, Math.min(588, y));
    placed.add(id);
  };

  const libraryNodes = payload.nodes.filter((node) => node.kind === "library");
  libraryNodes.forEach((library, libraryIndex) => {
    const libraryAngle =
      libraryNodes.length === 1
        ? -Math.PI / 2
        : (Math.PI * 2 * libraryIndex) / libraryNodes.length - Math.PI / 2;
    const libraryX =
      libraryNodes.length === 1 ? centerX : centerX + Math.cos(libraryAngle) * libraryRadius;
    const libraryY =
      libraryNodes.length === 1 ? centerY : centerY + Math.sin(libraryAngle) * libraryRadius;
    place(library.id, libraryX, libraryY);

    const files = (outgoing.get(library.id) ?? [])
      .filter((edge) => edge.kind === "contains")
      .map((edge) => edge.target)
      .filter((target) => visualById.get(target)?.kind === "file");
    files.forEach((fileId, fileIndex) => {
      const fileAngle =
        libraryAngle + (files.length === 1 ? 0 : (fileIndex - (files.length - 1) / 2) * 0.55);
      const fileNode = visualById.get(fileId);
      if (!fileNode) return;
      const fileX = libraryX + Math.cos(fileAngle) * fileRadius;
      const fileY = libraryY + Math.sin(fileAngle) * fileRadius;
      fileNode.libraryId = graphLibraryIdForNode(library);
      place(fileId, fileX, fileY);

      const related = (outgoing.get(fileId) ?? []).map((edge) => edge.target);
      related.forEach((relatedId, relatedIndex) => {
        const relatedNode = visualById.get(relatedId);
        if (!relatedNode) return;
        const relatedAngle =
          fileAngle + 0.78 + (related.length === 1 ? 0 : (relatedIndex - (related.length - 1) / 2) * 0.42);
        relatedNode.libraryId = fileNode.libraryId;
        place(
          relatedId,
          fileX + Math.cos(relatedAngle) * relatedRadius,
          fileY + Math.sin(relatedAngle) * relatedRadius,
        );
      });
    });
  });

  const unplaced = Array.from(visualById.values()).filter((node) => !placed.has(node.id));
  unplaced.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(unplaced.length, 1) - Math.PI / 2;
    place(node.id, centerX + Math.cos(angle) * 395, centerY + Math.sin(angle) * 255);
  });

  return {
    nodes: Array.from(visualById.values()),
    edges: payload.edges.map((edge) => ({
      id: edge.id,
      from: edge.source,
      to: edge.target,
      kind: edge.kind,
      metadata: edge.metadata,
    })),
  };
}

function KnowledgeGraphView({
  libraries,
  selectedId,
  onSelect,
  loading,
  graphPayload,
}: {
  libraries: KnowledgeBaseSummary[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading: boolean;
  graphPayload: KnowledgeGraphPayload | null;
}) {
  const fallbackGraph = useMemo(() => buildKnowledgeGraph(libraries), [libraries]);
  const apiGraph = useMemo(
    () => (graphPayload ? layoutKnowledgeGraphPayload(graphPayload) : null),
    [graphPayload],
  );
  const { nodes, edges } = apiGraph ?? fallbackGraph;
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const selectedLibrary = libraries.find((library) => library.id === selectedId) ?? libraries[0] ?? null;
  const libraryCount = nodes.filter((node) => node.kind === "library").length || libraries.length;
  const fileCount =
    nodes.filter((node) => node.kind === "file").length ||
    libraries.reduce((total, item) => total + (item.files?.length ?? 0), 0);
  const relatedCount = nodes.filter((node) => !["library", "file"].includes(node.kind)).length;
  const [viewTransform, setViewTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [dragStart, setDragStart] = useState<{
    pointerX: number;
    pointerY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const activeNodeId = hoveredNodeId ?? focusedNodeId;
  const connectedNodeIds = useMemo(() => {
    if (!activeNodeId) return new Set<string>();
    const next = new Set<string>([activeNodeId]);
    edges.forEach((edge) => {
      if (edge.from === activeNodeId) next.add(edge.to);
      if (edge.to === activeNodeId) next.add(edge.from);
    });
    return next;
  }, [activeNodeId, edges]);

  const resetGraphView = () => {
    setViewTransform({ x: 0, y: 0, scale: 1 });
    setFocusedNodeId(null);
  };

  const handleGraphWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const direction = event.deltaY > 0 ? -1 : 1;
    setViewTransform((current) => ({
      ...current,
      scale: Math.min(2.4, Math.max(0.55, current.scale + direction * 0.12)),
    }));
  };

  const handleGraphPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    setDragStart({
      pointerX: event.clientX,
      pointerY: event.clientY,
      originX: viewTransform.x,
      originY: viewTransform.y,
    });
  };

  const handleGraphPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!dragStart) return;
    setViewTransform((current) => ({
      ...current,
      x: dragStart.originX + event.clientX - dragStart.pointerX,
      y: dragStart.originY + event.clientY - dragStart.pointerY,
    }));
  };

  const handleGraphPointerUp = () => {
    setDragStart(null);
  };

  if (loading) {
    return (
      <InfoCard
        title="知识图谱"
        body={<EmptyHint text="正在读取知识花园，图谱马上长出来。" />}
      />
    );
  }

  if (!libraries.length) {
    return (
      <InfoCard
        title="知识图谱"
        body="还没有资料库。先上传课程、笔记或教材，知识花园会自动生成第一张关系图。"
      />
    );
  }

  return (
    <div className="relative min-h-[620px] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
      <div className="absolute inset-x-0 top-0 z-10 flex h-10 items-center justify-center border-b border-slate-200/80 bg-white/88 text-[12px] text-slate-500 backdrop-blur">
        <div className="absolute left-4 flex items-center gap-2">
          <button
            type="button"
            onClick={resetGraphView}
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600 shadow-sm hover:bg-slate-50"
          >
            复位
          </button>
          <span className="text-[11px] text-slate-400">拖拽移动 · 滚轮缩放 · 点击聚焦</span>
        </div>
        <span className="font-medium tracking-[0.02em] text-slate-700">关系图谱</span>
        <div className="absolute right-4 flex items-center gap-3 text-[11px] text-slate-500">
          <span>{libraryCount} 库</span>
          <span>{fileCount} 文件</span>
          <span>{relatedCount} 线索</span>
          <span>{Math.round(viewTransform.scale * 100)}%</span>
        </div>
      </div>

      <svg
        viewBox="0 0 1160 640"
        role="img"
        aria-label="知识花园图谱"
        className={cn("h-[clamp(620px,72vh,820px)] w-full touch-none", dragStart ? "cursor-grabbing" : "cursor-grab")}
        onWheel={handleGraphWheel}
        onPointerDown={handleGraphPointerDown}
        onPointerMove={handleGraphPointerMove}
        onPointerUp={handleGraphPointerUp}
        onPointerLeave={handleGraphPointerUp}
      >
        <rect width="1160" height="640" fill="#ffffff" />
        <path d="M0 84H1160M0 320H1160M0 556H1160M160 0V640M580 0V640M1000 0V640" stroke="rgba(148,163,184,0.13)" strokeWidth="1" />
        <g transform={`translate(${viewTransform.x} ${viewTransform.y}) scale(${viewTransform.scale})`}>
          {edges.map((edge, index) => {
            const from = nodeById.get(edge.from);
            const to = nodeById.get(edge.to);
            if (!from || !to) return null;
            const active = !activeNodeId || (connectedNodeIds.has(edge.from) && connectedNodeIds.has(edge.to));
            return (
              <line
                key={edge.id || `${edge.from}-${edge.to}-${index}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={graphEdgeColor(edge.kind)}
                strokeWidth={active ? (edge.kind === "contains" ? 1.55 : 1.1) : 0.55}
                opacity={active ? 1 : 0.16}
              />
            );
          })}
          {nodes.map((node) => {
            const selected = node.libraryId === selectedId || node.id === `library:${selectedId}`;
            const graphActive = !activeNodeId || connectedNodeIds.has(node.id);
            const focused = activeNodeId === node.id;
            const fill = graphNodeColor(node.kind);
            const labelY = node.y + node.size + (node.kind === "library" ? 16 : 12);
            return (
              <g
                key={node.id}
                role={node.kind === "library" ? "button" : undefined}
                tabIndex={node.kind === "library" ? 0 : undefined}
                onPointerDown={(event) => event.stopPropagation()}
                onMouseEnter={() => setHoveredNodeId(node.id)}
                onMouseLeave={() => setHoveredNodeId(null)}
                onClick={() => {
                  setFocusedNodeId((current) => (current === node.id ? null : node.id));
                  if (node.libraryId) onSelect(node.libraryId);
                }}
                className="cursor-pointer"
              >
                {selected || focused ? (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.size + (focused ? 12 : 8)}
                    fill={fill}
                    opacity={focused ? 0.15 : 0.1}
                  />
                ) : null}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.size + (focused ? 2.5 : selected ? 1.5 : 0)}
                  fill={fill}
                  opacity={graphActive ? (node.kind === "library" ? 0.98 : 0.9) : 0.25}
                  stroke="#ffffff"
                  strokeWidth={focused ? 2.4 : node.kind === "library" ? 1.8 : 1}
                />
                <text
                  x={node.x}
                  y={labelY}
                  textAnchor="middle"
                  pointerEvents="none"
                  style={{
                    fill: focused ? "#0f172a" : graphActive ? "#475569" : "#cbd5e1",
                    fontSize: node.kind === "library" ? 12 : 10.5,
                    fontWeight: focused || node.kind === "library" ? 650 : 480,
                  }}
                >
                  {graphNodeLabel(node.label, node.kind)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="absolute bottom-4 left-4 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span className="rounded-full border border-slate-200 bg-white/90 px-2.5 py-1 shadow-sm">蓝色：资料库 / 文件</span>
        <span className="rounded-full border border-slate-200 bg-white/90 px-2.5 py-1 shadow-sm">橙绿：概念 / 练习 / 证据</span>
        <span className="rounded-full border border-slate-200 bg-white/90 px-2.5 py-1 shadow-sm">
          {graphPayload ? "后端 graph API" : "前端 fallback"}
        </span>
      </div>

      {selectedLibrary ? (
        <div className="absolute bottom-4 right-4 w-[min(300px,calc(100%-2rem))] rounded-lg border border-slate-200 bg-white/92 p-3 text-slate-700 shadow-[0_14px_34px_rgba(15,23,42,0.10)] backdrop-blur">
          <div className="flex items-center justify-between gap-3">
            <div className="truncate text-[13px] font-semibold">{selectedLibrary.name}</div>
            <div className="shrink-0 text-[11px] text-slate-500">{selectedLibrary.status}</div>
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            {selectedLibrary.files?.length ?? 0} 个文件 · {selectedLibrary.provider ?? "LightRAG"}
          </div>
          <div className="mt-2 space-y-1">
            {(selectedLibrary.files ?? []).slice(0, 4).map((file) => (
              <div key={file.path} className="truncate text-[11px] text-slate-600">
                {file.name}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
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
  const [drafts, setDrafts] = useState<Record<MemoryDocumentName, string>>({
    summary: "",
    profile: "",
  });
  const [busy, setBusy] = useState<MemoryBusyKey | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [memoryEnabled, setMemoryEnabled] = useState(true);

  const applyMemoryDocuments = useCallback((snapshot: MemoryDocPayload) => {
    setPayload((current) =>
      current
        ? {
            ...current,
            summary: snapshot.summary,
            profile: snapshot.profile,
            summary_updated_at: snapshot.summary_updated_at,
            profile_updated_at: snapshot.profile_updated_at,
          }
        : current,
    );
    setDrafts({
      summary: snapshot.summary,
      profile: snapshot.profile,
    });
  }, []);

  const loadMemory = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchMemorySummary(token);
      setPayload(result);
      setDrafts({
        summary: result.summary,
        profile: result.profile,
      });
    } catch (err) {
      console.warn("Failed to load memory summary", err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadMemory();
  }, [loadMemory]);

  const saveDocument = async (file: MemoryDocumentName) => {
    if (busy) return;
    setBusy(file);
    try {
      const snapshot = await updateMemoryDocument(token, file, drafts[file]);
      applyMemoryDocuments(snapshot);
      setNotice(`${memoryDocumentLabel(file)}已保存。`);
    } catch (err) {
      console.warn("Failed to save memory document", err);
    } finally {
      setBusy(null);
    }
  };

  const clearDocument = async (file: MemoryDocumentName) => {
    if (busy) return;
    setBusy(`clear-${file}`);
    try {
      const snapshot = await clearMemoryDocument(token, file);
      applyMemoryDocuments(snapshot);
      setNotice(`${memoryDocumentLabel(file)}已清空。`);
    } catch (err) {
      console.warn("Failed to clear memory document", err);
    } finally {
      setBusy(null);
    }
  };

  const refreshSummary = async () => {
    if (busy) return;
    setBusy("refresh");
    try {
      const snapshot = await refreshMemoryDocument(token);
      applyMemoryDocuments(snapshot);
      setNotice(snapshot.changed ? "已整理最新学习摘要。" : "没有发现新的学习回顾。");
    } catch (err) {
      console.warn("Failed to refresh memory document", err);
    } finally {
      setBusy(null);
    }
  };

  const summaryDirty = payload ? drafts.summary !== payload.summary : false;
  const profileDirty = payload ? drafts.profile !== payload.profile : false;

  return (
    <PanelView
      title="记忆"
      subtitle="设置 CoLearn 如何保留、整理和使用你的学习资料。"
      {...panelProps}
    >
      <div className="mx-auto flex w-full max-w-[720px] flex-col gap-8">
        {notice ? (
          <div
            role="status"
            className="rounded-lg border border-emerald-500/20 bg-emerald-500/8 px-3 py-2.5 text-[13px] text-emerald-700 dark:text-emerald-300"
          >
            {notice}
          </div>
        ) : null}

        <section className="space-y-2">
          <MemorySectionTitle>学习摘要</MemorySectionTitle>
          <MemorySectionHint>
            跨会话保留的稳定学习背景和结论。<span>了解更多</span>
          </MemorySectionHint>
          <MemoryDocumentEditor
            file="summary"
            value={drafts.summary}
            dirty={summaryDirty}
            busy={busy}
            disabled={loading && !payload}
            onChange={(value) => setDrafts((current) => ({ ...current, summary: value }))}
            onSave={() => void saveDocument("summary")}
          />
        </section>

        <section className="space-y-2">
          <MemorySectionTitle>个人画像</MemorySectionTitle>
          <MemorySectionHint>
            记录学习目标、偏好和已经确认的协作方式。<span>了解更多</span>
          </MemorySectionHint>
          <MemoryDocumentEditor
            file="profile"
            value={drafts.profile}
            dirty={profileDirty}
            busy={busy}
            disabled={loading && !payload}
            onChange={(value) => setDrafts((current) => ({ ...current, profile: value }))}
            onSave={() => void saveDocument("profile")}
          />
        </section>

        <section className="space-y-2">
          <MemorySectionTitle>记忆（实验性）</MemorySectionTitle>
          <MemorySectionHint>
            设置 CoLearn 如何收集、保留和整合记忆。<span>了解更多</span>
          </MemorySectionHint>
          <MemoryGroup>
            <MemorySettingRow
              title="启用记忆"
              description="从聊天中生成新记录，并将其带入新聊天"
            >
              <MemorySwitch active={memoryEnabled} onClick={() => setMemoryEnabled((value) => !value)} />
            </MemorySettingRow>
            <MemorySettingRow
              title="整理摘要"
              description="从最近一次学习回顾更新学习摘要"
            >
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => void refreshSummary()}
                disabled={!!busy}
                className="h-8 rounded-full px-3 text-[12px] font-medium"
              >
                {busy === "refresh" ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                ) : (
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                )}
                整理
              </Button>
            </MemorySettingRow>
            <MemorySettingRow
              title="重置记忆"
              description="删除已保存的学习摘要或个人画像"
            >
              <div className="flex flex-wrap justify-end gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => void clearDocument("summary")}
                  disabled={!!busy || !drafts.summary}
                  className="h-8 rounded-full px-3 text-[12px] font-medium text-destructive hover:text-destructive"
                >
                  {busy === "clear-summary" ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                  ) : (
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                  )}
                  摘要
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => void clearDocument("profile")}
                  disabled={!!busy || !drafts.profile}
                  className="h-8 rounded-full px-3 text-[12px] font-medium text-destructive hover:text-destructive"
                >
                  {busy === "clear-profile" ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                  ) : (
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                  )}
                  画像
                </Button>
              </div>
            </MemorySettingRow>
          </MemoryGroup>
        </section>
      </div>
    </PanelView>
  );
}

type MemoryBusyKey = MemoryDocumentName | "refresh" | `clear-${MemoryDocumentName}`;

const MEMORY_DOCUMENT_COPY: Record<
  MemoryDocumentName,
  { placeholder: string }
> = {
  summary: {
    placeholder: "记录稳定的学习结论、偏好和上下文。",
  },
  profile: {
    placeholder: "记录已经确认的长期偏好、目标和背景。",
  },
};

function memoryDocumentLabel(file: MemoryDocumentName): string {
  return file === "summary" ? "学习摘要" : "个人画像";
}

function MemorySectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="px-1 font-sans text-[14px] font-semibold tracking-normal text-foreground/92">
      {children}
    </h2>
  );
}

function MemorySectionHint({ children }: { children: ReactNode }) {
  return (
    <p className="px-1 font-sans text-[13px] leading-5 text-muted-foreground">
      {children}
    </p>
  );
}

function MemoryGroup({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-border/60 bg-card/88 font-sans shadow-[0_16px_48px_rgba(15,23,42,0.055)]",
        className,
      )}
    >
      <div className="divide-y divide-border/50">{children}</div>
    </div>
  );
}

function MemoryDocumentEditor({
  file,
  value,
  dirty,
  busy,
  disabled,
  onChange,
  onSave,
}: {
  file: MemoryDocumentName;
  value: string;
  dirty: boolean;
  busy: MemoryBusyKey | null;
  disabled: boolean;
  onChange: (value: string) => void;
  onSave: () => void;
}) {
  const copy = MEMORY_DOCUMENT_COPY[file];
  const saving = busy === file;
  const isBusy = !!busy;
  return (
    <div className="space-y-2">
      <Textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={copy.placeholder}
        disabled={disabled}
        className="min-h-[184px] resize-y rounded-lg border-border/70 bg-card/90 px-3 py-3 text-[13px] leading-6 shadow-inner focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-0"
      />
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={onSave}
          disabled={isBusy || disabled || !dirty}
          className="h-8 rounded-full px-3 text-[12px] font-medium"
        >
          {saving ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
          ) : (
            <Save className="mr-1.5 h-3.5 w-3.5" aria-hidden />
          )}
          保存
        </Button>
      </div>
    </div>
  );
}

function MemorySettingRow({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-[78px] flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="min-w-0 flex-1">
        <div className="text-[14px] font-medium leading-5 text-foreground">{title}</div>
        <div className="mt-1 max-w-[34rem] text-[12px] leading-5 text-muted-foreground">
          {description}
        </div>
      </div>
      <div className="flex shrink-0 items-center self-end sm:ml-6 sm:self-center">{children}</div>
    </div>
  );
}

function MemorySwitch({
  active,
  onClick,
}: {
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      onClick={onClick}
      className={cn(
        "relative h-6 w-10 rounded-full transition-colors",
        active ? "bg-foreground/70" : "bg-muted-foreground/35",
      )}
    >
      <span
        className={cn(
          "absolute top-1 h-4 w-4 rounded-full bg-background shadow-sm transition-transform",
          active ? "translate-x-5" : "translate-x-1",
        )}
      />
    </button>
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
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "recommended" | "system" | "personal">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const filterOptions = [
    { value: "all", label: "全部" },
    { value: "recommended", label: "推荐" },
    { value: "system", label: "系统" },
    { value: "personal", label: "个人" },
  ] as const;
  const activeFilterLabel =
    filterOptions.find((option) => option.value === filter)?.label ?? "全部";

  const enrichedSkills = useMemo(
    () =>
      skills.map((skill, index) => {
        const tags = skill.tags.map((tag) => tag.toLowerCase());
        const category = tags.some((tag) => ["system", "builtin", "系统"].includes(tag))
          ? "system"
          : "personal";
        const recommended =
          tags.some((tag) => ["recommended", "recommend", "推荐"].includes(tag)) || index < 2;
        return { ...skill, category, recommended };
      }),
    [skills],
  );

  const filteredSkills = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return enrichedSkills.filter((skill) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "recommended" && skill.recommended) ||
        (filter === "system" && skill.category === "system") ||
        (filter === "personal" && skill.category === "personal");
      const matchesQuery =
        !normalizedQuery ||
        skill.name.toLowerCase().includes(normalizedQuery) ||
        skill.description.toLowerCase().includes(normalizedQuery) ||
        skill.tags.some((tag) => tag.toLowerCase().includes(normalizedQuery));
      return matchesFilter && matchesQuery;
    });
  }, [enrichedSkills, filter, query]);

  const sections = [
    {
      key: "recommended",
      title: "推荐",
      skills: filteredSkills.filter((skill) => skill.recommended),
    },
    {
      key: "system",
      title: "系统",
      skills: filteredSkills.filter((skill) => !skill.recommended && skill.category === "system"),
    },
    {
      key: "personal",
      title: "个人",
      skills: filteredSkills.filter((skill) => !skill.recommended && skill.category === "personal"),
    },
  ].filter((section) => section.skills.length);

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
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索技能"
              className="h-10 rounded-full border-border/70 bg-muted/45 pl-9 text-sm shadow-inner"
            />
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="secondary"
                className="h-10 min-w-[84px] justify-between rounded-full border border-border/60 bg-muted/55 px-4 text-sm font-medium shadow-none hover:bg-muted"
              >
                {activeFilterLabel}
                <ChevronDown className="ml-2 h-4 w-4 text-muted-foreground" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[116px] rounded-lg p-1">
              {filterOptions.map((option) => (
                <DropdownMenuItem
                  key={option.value}
                  onClick={() => setFilter(option.value)}
                  className="flex cursor-pointer items-center justify-between rounded-md text-sm"
                >
                  {option.label}
                  {filter === option.value ? (
                    <Check className="ml-3 h-4 w-4 text-muted-foreground" aria-hidden />
                  ) : null}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {loading ? (
          <SkillLibraryNotice text="正在加载技能..." />
        ) : error ? (
          <SkillLibraryNotice text={error} />
        ) : skills.length && sections.length ? (
          <div className="flex flex-col gap-8">
            {sections.map((section) => (
              <section key={section.key} className="flex flex-col gap-3">
                <div className="border-b border-border/45 pb-3 text-base font-semibold text-foreground">
                  {section.title}
                </div>
                <div className="grid gap-x-8 gap-y-3 md:grid-cols-2">
                  {section.skills.map((skill) => (
                    <SkillCard key={skill.name} skill={skill} installed />
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : skills.length ? (
          <SkillLibraryNotice text="没有匹配的技能。" />
        ) : (
          <SkillLibraryNotice text="当前还没有技能卡。后面接入学习助手和工作流技能后，这里会变成真实能力面。" />
        )}
      </div>
    </PanelView>
  );
}

function SkillCard({
  skill,
  installed,
}: {
  skill: SkillSummary & { category: string; recommended: boolean };
  installed: boolean;
}) {
  const Icon = getSkillIcon(skill);
  const description = skill.description || "这张技能卡已经接入运行时，可以在学习会话里被调用。";

  return (
    <article className="group flex min-h-[74px] items-center gap-3 rounded-lg border border-transparent px-3 py-3 transition hover:border-border/60 hover:bg-muted/40">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground shadow-sm">
        <Icon className={cn("h-5 w-5", getSkillIconTone(skill.name))} aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-semibold leading-5 text-foreground">
          {toTitle(skill.name)}
          <span className="sr-only">{skill.name}</span>
        </div>
        <div className="mt-0.5 line-clamp-1 text-[13px] leading-5 text-muted-foreground">
          {description}
        </div>
      </div>
      <button
        type="button"
        aria-label={installed ? `${skill.name} 已安装` : `添加 ${skill.name}`}
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition",
          installed
            ? "text-muted-foreground/75"
            : "bg-muted text-foreground hover:bg-foreground hover:text-background",
        )}
      >
        {installed ? <Check className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}
      </button>
    </article>
  );
}

function SkillLibraryNotice({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-border/50 bg-card/70 px-4 py-5 text-sm text-muted-foreground">
      {text}
    </div>
  );
}

function toTitle(value: string) {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getSkillIcon(skill: SkillSummary) {
  const name = skill.name.toLowerCase();
  const haystack = `${skill.name} ${skill.description} ${skill.tags.join(" ")}`.toLowerCase();
  if (haystack.includes("image") || haystack.includes("图片") || haystack.includes("图像")) return Image;
  if (haystack.includes("doc") || haystack.includes("markdown") || haystack.includes("pdf")) return BookOpen;
  if (haystack.includes("create") || haystack.includes("creator") || haystack.includes("edit")) return Pencil;
  if (name.includes("plugin") || name.includes("install")) return Puzzle;
  return Sparkles;
}

function getSkillIconTone(name: string) {
  const tones = [
    "text-rose-500",
    "text-sky-500",
    "text-amber-500",
    "text-emerald-500",
    "text-violet-500",
  ];
  return tones[name.length % tones.length];
}
