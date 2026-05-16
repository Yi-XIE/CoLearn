"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Code2,
  Database,
  Download,
  FileSearch,
  Globe,
  Lightbulb,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import ChatComposer from "@/components/chat/home/ChatComposer";
import { ChatMessageList } from "@/components/chat/home/ChatMessages";
import FilePreviewDrawer from "@/components/chat/preview/FilePreviewDrawer";
import {
  useUnifiedChat,
  type MessageAttachment,
} from "@/context/UnifiedChatContext";
import { useAppShell } from "@/context/AppShellContext";
import type { FilePreviewSource } from "@/components/chat/preview/previewerFor";
import type { LLMSelection } from "@/lib/unified-ws";
import {
  extractBase64FromDataUrl,
  readFileAsDataUrl,
} from "@/lib/file-attachments";
import {
  classifyFile,
  isSvgFilename,
  MAX_ATTACHMENT_BYTES,
  MAX_TOTAL_ATTACHMENT_BYTES,
} from "@/lib/doc-attachments";
import { useChatAutoScroll } from "@/hooks/useChatAutoScroll";
import { useMeasuredHeight } from "@/hooks/useMeasuredHeight";
import { listLLMOptions, type LLMOption } from "@/lib/llm-options";
import { downloadChatMarkdown } from "@/lib/chat-export";
import { shouldEnterLearningMode } from "@/lib/learning-intent";
import {
  createProject,
  hasCompleteLearningAnchor,
  listProjects,
  saveProjectAnchor,
  type LearningState,
  type LearningProject,
} from "@/lib/projects-api";
import { projectToRef, type MemoryReferenceFile } from "@/lib/learning-context";
import { getSession } from "@/lib/session-api";

const MemoryPicker = dynamic(() => import("@/components/chat/MemoryPicker"), {
  ssr: false,
});

type ToolName =
  | "brainstorm"
  | "rag"
  | "web_search"
  | "code_execution"
  | "reason"
  | "paper_search";

interface ToolDef {
  name: ToolName;
  label: string;
  icon: LucideIcon;
}

const ALL_TOOLS: ToolDef[] = [
  { name: "brainstorm", label: "Brainstorm", icon: Lightbulb },
  { name: "rag", label: "Knowledge", icon: Database },
  { name: "web_search", label: "Web Search", icon: Globe },
  { name: "code_execution", label: "Code", icon: Code2 },
  { name: "reason", label: "Reason", icon: Sparkles },
  { name: "paper_search", label: "Arxiv Search", icon: FileSearch },
];

const ANCHOR_METHOD_OPTIONS = [
  "feynman",
  "active recall",
  "worked examples",
  "step by step",
];

const ANCHOR_PRIOR_KNOWLEDGE_OPTIONS = [
  "Starting from scratch",
  "Knows basics",
  "Can solve simple cases",
  "Needs help on edge cases",
];

const ANCHOR_TARGET_DEPTH_OPTIONS = [
  "Build intuition",
  "Explain in my own words",
  "Compare and apply concepts",
  "Handle harder variants independently",
];

type AnchorStepKey = "preferredMethod" | "priorKnowledge" | "targetDepth";

interface PendingAttachment {
  type: string;
  filename: string;
  base64?: string;
  previewUrl?: string;
  size?: number;
  mimeType?: string;
}

function AnchorStepChoices({
  label,
  options,
  value,
  customValue,
  placeholder,
  skipLabel,
  onPick,
  onCustomChange,
  onCustomSubmit,
  onSkip,
}: {
  label: string;
  options: string[];
  value: string;
  customValue: string;
  placeholder: string;
  skipLabel: string;
  onPick: (value: string) => void;
  onCustomChange: (value: string) => void;
  onCustomSubmit: () => void;
  onSkip: () => void;
}) {
  return (
    <div>
      <div className="mb-3 text-sm font-medium text-[var(--foreground)]">
        {label}
      </div>
      <div className="grid gap-2">
        {options.map((option) => {
          const selected = value === option;
          return (
            <button
              key={option}
              type="button"
              onClick={() => onPick(option)}
              className={`rounded-xl border px-3 py-3 text-left text-[13px] transition-colors ${
                selected
                  ? "border-[var(--foreground)]/18 bg-[var(--foreground)]/10 text-[var(--foreground)]"
                  : "border-[var(--border)] bg-[color:color-mix(in_srgb,var(--background)_74%,white_3%)] text-[var(--foreground)]/90 hover:border-[var(--border)]/80 hover:bg-[var(--foreground)]/4"
              }`}
            >
              {option}
            </button>
          );
        })}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
        <input
          value={customValue}
          onChange={(event) => onCustomChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              onCustomSubmit();
            }
          }}
          placeholder={placeholder}
          className="h-11 rounded-xl border border-[var(--border)] bg-[color:color-mix(in_srgb,var(--background)_76%,white_3%)] px-3 text-[13px] text-[var(--foreground)] outline-none transition-colors placeholder:text-[var(--muted-foreground)] focus:border-[var(--primary)]"
        />
        <button
          type="button"
          onClick={onSkip}
          className="h-11 rounded-xl border border-[var(--border)] px-4 text-[13px] font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--foreground)]/5"
        >
          {skipLabel}
        </button>
      </div>
    </div>
  );
}

function toAttachmentPayload(attachments: PendingAttachment[]) {
  return attachments.map((attachment) => ({
    type: attachment.type,
    filename: attachment.filename,
    base64: attachment.base64,
    mime_type: attachment.mimeType,
  }));
}

export default function ChatPage() {
  const params = useParams<{ sessionId?: string[] }>();
  const router = useRouter();
  const { t } = useTranslation();
  const sessionIdParam = params.sessionId?.[0] ?? null;

  const { activeProjectId, setActiveProjectId, language } = useAppShell();
  const {
    state,
    setTools,
    setLLMSelection,
    sendMessage,
    cancelStreamingTurn,
    regenerateLastMessage,
    newSession,
    loadSession,
  } = useUnifiedChat();

  const [llmOptions, setLLMOptions] = useState<LLMOption[]>([]);
  const [activeLLMDefault, setActiveLLMDefault] =
    useState<LLMSelection | null>(null);
  const [llmOptionsLoading, setLLMOptionsLoading] = useState(true);
  const [llmOptionsError, setLLMOptionsError] = useState(false);
  const [projects, setProjects] = useState<LearningProject[]>([]);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [previewSource, setPreviewSource] =
    useState<FilePreviewSource | null>(null);
  const [showMemoryPicker, setShowMemoryPicker] = useState(false);
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [currentSessionTitle, setCurrentSessionTitle] = useState("");
  const [selectedMemoryFiles, setSelectedMemoryFiles] = useState<
    MemoryReferenceFile[]
  >([]);
  const [anchorTopic, setAnchorTopic] = useState("");
  const [anchorPriorKnowledge, setAnchorPriorKnowledge] = useState("");
  const [anchorTargetDepth, setAnchorTargetDepth] = useState("");
  const [anchorPreferredMethod, setAnchorPreferredMethod] = useState("");
  const [anchorSaving, setAnchorSaving] = useState(false);
  const [anchorError, setAnchorError] = useState<string | null>(null);
  const [showAnchorGate, setShowAnchorGate] = useState(false);
  const [anchorPendingMessage, setAnchorPendingMessage] = useState("");
  const [anchorStep, setAnchorStep] = useState<AnchorStepKey>("preferredMethod");
  const [anchorCustomDraft, setAnchorCustomDraft] = useState("");
  const attachmentErrorTimer = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const dragCounter = useRef(0);
  const toolMenuRef = useRef<HTMLDivElement>(null);
  const toolBtnRef = useRef<HTMLButtonElement>(null);
  const projectMenuRef = useRef<HTMLDivElement>(null);
  const projectBtnRef = useRef<HTMLButtonElement>(null);
  const initialLoadRef = useRef(false);

  const { ref: composerRef, height: composerHeight } =
    useMeasuredHeight<HTMLDivElement>();

  const currentProject = useMemo(() => {
    const active =
      projects.find((item) => item.project_id === activeProjectId) ?? projects[0];
    return projectToRef(active);
  }, [activeProjectId, projects]);

  const activeProject = useMemo(
    () =>
      projects.find((item) => item.project_id === activeProjectId) ??
      projects[0] ??
      null,
    [activeProjectId, projects],
  );

  const activeProjectHasCompleteAnchor = hasCompleteLearningAnchor(
    activeProject?.anchor,
  );
  const anchorOverlayVisible = !activeProjectHasCompleteAnchor && showAnchorGate;
  const anchorTopicLabel = useMemo(() => {
    const explicit = anchorTopic.trim();
    if (explicit) return explicit;
    const fromMessage = anchorPendingMessage.trim();
    if (!fromMessage) return t("This learning topic");
    return fromMessage.length > 72
      ? `${fromMessage.slice(0, 72).trim()}...`
      : fromMessage;
  }, [anchorPendingMessage, anchorTopic, t]);
  const selectedTools = useMemo(
    () => new Set(state.enabledTools),
    [state.enabledTools],
  );
  const visibleTools = ALL_TOOLS;
  const hasMessages = state.messages.length > 0;
  const lastMessage = state.messages[state.messages.length - 1];

  const {
    containerRef: messagesContainerRef,
    endRef: messagesEndRef,
    shouldAutoScrollRef,
    handleScroll: handleMessagesScroll,
  } = useChatAutoScroll({
    hasMessages,
    isStreaming: state.isStreaming,
    composerHeight,
    messageCount: state.messages.length,
    lastMessageContent: lastMessage?.content,
    lastEventCount: lastMessage?.events?.length,
  });

  const memoryReferencesPayload = useMemo(
    () => [...selectedMemoryFiles],
    [selectedMemoryFiles],
  );

  const copyAssistantMessage = useCallback(async (content: string) => {
    if (!content.trim()) return;
    try {
      await navigator.clipboard.writeText(content);
    } catch (error) {
      console.error("Failed to copy assistant message:", error);
    }
  }, []);

  const refreshLLMOptions = useCallback(async () => {
    setLLMOptionsLoading(true);
    try {
      const payload = await listLLMOptions();
      setLLMOptions(payload.options);
      setActiveLLMDefault(payload.active);
      setLLMOptionsError(false);
    } catch {
      setLLMOptionsError(true);
      setLLMOptions([]);
      setActiveLLMDefault(null);
    } finally {
      setLLMOptionsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshLLMOptions();
  }, [refreshLLMOptions]);

  useEffect(() => {
    if (state.llmSelection || !activeLLMDefault) return;
    setLLMSelection(activeLLMDefault);
  }, [activeLLMDefault, setLLMSelection, state.llmSelection]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") {
        void refreshLLMOptions();
      }
    };
    window.addEventListener("focus", refreshLLMOptions);
    window.addEventListener("pageshow", refreshLLMOptions);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", refreshLLMOptions);
      window.removeEventListener("pageshow", refreshLLMOptions);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [refreshLLMOptions]);

  const refreshProjects = useCallback(async () => {
    try {
      const items = await listProjects({ force: true });
      if (items.length > 0) {
        setProjects(items);
        if (
          !activeProjectId ||
          !items.some((item) => item.project_id === activeProjectId)
        ) {
          setActiveProjectId(items[0].project_id);
        }
        return;
      }
      const created = await createProject({
        title: "Current CoLearn project",
        goal:
          "Build understanding with CoLearn through explanation, practice, and review.",
      });
      setProjects([created]);
      setActiveProjectId(created.project_id);
    } catch (error) {
      console.error("Failed to load projects", error);
      setProjects([]);
    }
  }, [activeProjectId, setActiveProjectId]);

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    if (!activeProject?.anchor) return;
    setAnchorTopic(activeProject.anchor.topic || "");
    setAnchorPriorKnowledge(activeProject.anchor.prior_knowledge || "");
    setAnchorTargetDepth(activeProject.anchor.target_depth || "");
    setAnchorPreferredMethod(activeProject.anchor.preferred_method || "");
  }, [activeProject?.anchor]);

  useEffect(() => {
    if (initialLoadRef.current) return;
    initialLoadRef.current = true;
    if (sessionIdParam) {
      void loadSession(sessionIdParam).catch(() => {
        router.replace("/chat", { scroll: false });
      });
    } else {
      newSession();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const prevSessionIdParam = useRef(sessionIdParam);
  useEffect(() => {
    if (sessionIdParam === prevSessionIdParam.current) return;
    prevSessionIdParam.current = sessionIdParam;
    if (sessionIdParam) {
      if (sessionIdParam === state.sessionId) return;
      void loadSession(sessionIdParam).catch(() => {
        router.replace("/chat", { scroll: false });
      });
    } else {
      newSession();
    }
  }, [loadSession, newSession, router, sessionIdParam, state.sessionId]);

  useEffect(() => {
    if (state.sessionId && !sessionIdParam) {
      router.replace(`/chat/${state.sessionId}`, { scroll: false });
    }
  }, [router, sessionIdParam, state.sessionId]);

  useEffect(() => {
    let cancelled = false;
    const activeSessionId = state.sessionId || sessionIdParam;

    if (!activeSessionId) {
      setCurrentSessionTitle("");
      return () => {
        cancelled = true;
      };
    }

    void getSession(activeSessionId)
      .then((session) => {
        if (cancelled) return;

        setCurrentSessionTitle((session.title || "").trim());

        if (hasCompleteLearningAnchor(session.anchor)) {
          setAnchorTopic(session.anchor.topic || "");
          setAnchorPriorKnowledge(session.anchor.prior_knowledge || "");
          setAnchorTargetDepth(session.anchor.target_depth || "");
          setAnchorPreferredMethod(session.anchor.preferred_method || "");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCurrentSessionTitle("");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [sessionIdParam, state.sessionId]);

  useEffect(() => {
    const handleSessionRenamed = (event: Event) => {
      const customEvent = event as CustomEvent<{
        sessionId?: string;
        title?: string;
      }>;
      const activeSessionId = state.sessionId || sessionIdParam;
      if (!activeSessionId) return;
      if (customEvent.detail?.sessionId !== activeSessionId) return;
      setCurrentSessionTitle((customEvent.detail.title || "").trim());
    };

    window.addEventListener(
      "colearn:session-renamed",
      handleSessionRenamed as EventListener,
    );
    return () => {
      window.removeEventListener(
        "colearn:session-renamed",
        handleSessionRenamed as EventListener,
      );
    };
  }, [sessionIdParam, state.sessionId]);

  const showAttachmentError = useCallback((message: string) => {
    setAttachmentError(message);
    if (attachmentErrorTimer.current) {
      clearTimeout(attachmentErrorTimer.current);
    }
    attachmentErrorTimer.current = setTimeout(() => {
      setAttachmentError(null);
      attachmentErrorTimer.current = null;
    }, 4000);
  }, []);

  const fileToAttachment = useCallback(
    (file: File): Promise<PendingAttachment> =>
      new Promise((resolve, reject) => {
        readFileAsDataUrl(file)
          .then((raw) => {
            const svg = isSvgFilename(file.name) || file.type === "image/svg+xml";
            const isImage = !svg && file.type.startsWith("image/");
            const base64 = extractBase64FromDataUrl(raw);
            resolve({
              type: isImage ? "image" : "file",
              filename: file.name,
              base64,
              previewUrl: isImage || svg ? raw : undefined,
              size: file.size,
              mimeType: file.type || undefined,
            });
          })
          .catch(reject);
      }),
    [],
  );

  const filterAndReportFiles = useCallback(
    (files: File[]): File[] => {
      let runningTotal = attachments.reduce(
        (sum, item) => sum + (item.size ?? 0),
        0,
      );
      const accepted: File[] = [];
      const rejected: {
        name: string;
        reason: "unsupported" | "too_large" | "quota";
      }[] = [];

      for (const file of files) {
        const kind = classifyFile(file);
        if (!kind) {
          rejected.push({ name: file.name, reason: "unsupported" });
          continue;
        }
        if (file.size > MAX_ATTACHMENT_BYTES) {
          rejected.push({ name: file.name, reason: "too_large" });
          continue;
        }
        if (runningTotal + file.size > MAX_TOTAL_ATTACHMENT_BYTES) {
          rejected.push({ name: file.name, reason: "quota" });
          break;
        }
        runningTotal += file.size;
        accepted.push(file);
      }

      if (rejected.length > 0) {
        const first = rejected[0];
        if (first.reason === "too_large") {
          showAttachmentError(t("File too large: {{name}}", { name: first.name }));
        } else if (first.reason === "quota") {
          showAttachmentError(t("Too many files, skipped some"));
        } else {
          showAttachmentError(
            t("Unsupported file type: {{name}}", { name: first.name }),
          );
        }
      }

      return accepted;
    },
    [attachments, showAttachmentError, t],
  );

  const handlePaste = useCallback(
    async (event: React.ClipboardEvent) => {
      const items = Array.from(event.clipboardData.items);
      const files = items
        .filter((item) => item.kind === "file")
        .map((item) => item.getAsFile())
        .filter((file): file is File => file !== null);
      const accepted = filterAndReportFiles(files);
      if (!accepted.length) return;
      event.preventDefault();
      const next = await Promise.all(
        accepted.map((file) => fileToAttachment(file)),
      );
      setAttachments((prev) => [...prev, ...next]);
    },
    [fileToAttachment, filterAndReportFiles],
  );

  const handleDragEnter = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    dragCounter.current += 1;
    if (event.dataTransfer.types.includes("Files")) setDragging(true);
  }, []);

  const handleDragLeave = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current === 0) setDragging(false);
  }, []);

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    async (event: React.DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      setDragging(false);
      dragCounter.current = 0;
      const accepted = filterAndReportFiles(
        Array.from(event.dataTransfer.files),
      );
      if (!accepted.length) return;
      const next = await Promise.all(
        accepted.map((file) => fileToAttachment(file)),
      );
      setAttachments((prev) => [...prev, ...next]);
    },
    [fileToAttachment, filterAndReportFiles],
  );

  const handleAddFiles = useCallback(
    async (files: File[]) => {
      const accepted = filterAndReportFiles(files);
      if (!accepted.length) return;
      const next = await Promise.all(
        accepted.map((file) => fileToAttachment(file)),
      );
      setAttachments((prev) => [...prev, ...next]);
    },
    [fileToAttachment, filterAndReportFiles],
  );

  const handlePreviewPendingAttachment = useCallback(
    (index: number) => {
      const attachment = attachments[index];
      if (!attachment) return;
      setPreviewSource({
        filename: attachment.filename,
        mimeType: attachment.mimeType,
        type: attachment.type,
        base64: attachment.base64,
        size: attachment.size,
      });
    },
    [attachments],
  );

  const handlePreviewMessageAttachment = useCallback(
    (attachment: MessageAttachment) => {
      setPreviewSource({
        filename: attachment.filename || "",
        mimeType: attachment.mime_type,
        type: attachment.type,
        url: attachment.url,
        base64: attachment.base64,
        extractedText: attachment.extracted_text,
        id: attachment.id,
      });
    },
    [],
  );

  const handleClosePreview = useCallback(() => {
    setPreviewSource(null);
  }, []);

  const handleRemoveAttachment = useCallback((index: number) => {
    setAttachments((prev) =>
      prev.filter((_, itemIndex) => itemIndex !== index),
    );
  }, []);

  const handleSelectMemoryPicker = useCallback(() => {
    setShowMemoryPicker(true);
  }, []);

  const handleToggleMemoryFile = useCallback((file: MemoryReferenceFile) => {
    setSelectedMemoryFiles((prev) =>
      prev.includes(file)
        ? prev.filter((item) => item !== file)
        : [...prev, file],
    );
  }, []);

  const handleCloseMemoryPicker = useCallback(() => {
    setShowMemoryPicker(false);
  }, []);

  const handleApplyMemoryFiles = useCallback((files: MemoryReferenceFile[]) => {
    setSelectedMemoryFiles(files);
  }, []);

  const dispatchLearningTurn = useCallback(
    (content: string) => {
      const extraAttachments = toAttachmentPayload(attachments);
      const memoryPayload = [...memoryReferencesPayload];
      const messageContent =
        content ||
        (memoryPayload.length
          ? t("Please use the selected memory context to help with this request.")
          : "") ||
        (attachments.some((attachment) => attachment.type === "image")
          ? t("Please analyze the attached image(s).")
          : "");

      sendMessage(
        messageContent,
        extraAttachments,
        undefined,
        undefined,
        {
          projectId: currentProject.projectId,
          projectTitle: currentProject.title,
        },
        undefined,
        memoryPayload,
      );
      shouldAutoScrollRef.current = true;
      setAttachments([]);
      setSelectedMemoryFiles([]);
    },
    [
      attachments,
      currentProject.projectId,
      currentProject.title,
      memoryReferencesPayload,
      sendMessage,
      shouldAutoScrollRef,
      t,
    ],
  );

  const completeAnchorFlow = useCallback(async () => {
    if (!activeProject?.project_id) return;
    const topic = anchorTopicLabel.trim();
    const method = anchorPreferredMethod.trim();
    const prior = anchorPriorKnowledge.trim();
    const depth = anchorTargetDepth.trim();
    if (!topic || !method || !prior || !depth) return;

    setAnchorSaving(true);
    setAnchorError(null);
    try {
      await saveProjectAnchor(activeProject.project_id, {
        topic,
        prior_knowledge: prior,
        target_depth: depth,
        preferred_method: method,
      });
      if (anchorPendingMessage.trim()) {
        dispatchLearningTurn(anchorPendingMessage.trim());
      }
      setShowAnchorGate(false);
      setAnchorPendingMessage("");
      setAnchorCustomDraft("");
      setAnchorStep("preferredMethod");
      await refreshProjects();
    } catch (error) {
      console.error("Failed to save anchor", error);
      setAnchorError(t("Failed to save the learning anchor."));
    } finally {
      setAnchorSaving(false);
    }
  }, [
    activeProject?.project_id,
    anchorPendingMessage,
    anchorPreferredMethod,
    anchorPriorKnowledge,
    anchorTargetDepth,
    anchorTopicLabel,
    dispatchLearningTurn,
    refreshProjects,
    t,
  ]);

  const handleToggleTool = useCallback(
    (tool: ToolName) => {
      if (selectedTools.has(tool)) {
        setTools(state.enabledTools.filter((item) => item !== tool));
      } else {
        setTools([...state.enabledTools, tool]);
      }
    },
    [selectedTools, setTools, state.enabledTools],
  );

  const handleSend = useCallback(
    async (content: string) => {
      const isLearningIntent = shouldEnterLearningMode(content);
      if (!activeProjectHasCompleteAnchor && isLearningIntent) {
        const hasIntent =
          Boolean(content.trim()) ||
          attachments.length > 0 ||
          selectedMemoryFiles.length > 0;
        if (hasIntent) {
          const inferredTopic = content.trim();
          if (inferredTopic) {
            setAnchorPendingMessage(inferredTopic);
            setAnchorTopic(inferredTopic);
          }
          setShowAnchorGate(true);
          setAnchorStep("preferredMethod");
          setAnchorCustomDraft("");
          setAnchorError(
            t("Complete the learning anchor before starting a learning turn."),
          );
          return;
        }
      }
      if (
        (!content && !attachments.length && !selectedMemoryFiles.length) ||
        state.isStreaming
      ) {
        return;
      }

      dispatchLearningTurn(content);
    },
    [
      activeProjectHasCompleteAnchor,
      attachments.length,
      dispatchLearningTurn,
      selectedMemoryFiles.length,
      state.isStreaming,
      t,
    ],
  );

  useEffect(() => {
    if (activeProjectHasCompleteAnchor) {
      setShowAnchorGate(false);
      setAnchorPendingMessage("");
      setAnchorCustomDraft("");
      setAnchorStep("preferredMethod");
      setAnchorError(null);
    }
  }, [activeProjectHasCompleteAnchor]);

  const handleRegenerateMessage = useCallback(() => {
    regenerateLastMessage();
  }, [regenerateLastMessage]);

  const handleDownloadMarkdown = useCallback(() => {
    if (!state.messages.length) return;
    const title =
      state.messages
        .find((msg) => msg.role === "user")
        ?.content.trim()
        .slice(0, 80) || "Chat Session";
    downloadChatMarkdown(state.messages, { title });
  }, [state.messages]);

  const pageTitle = currentSessionTitle || t("Untitled");
  return (
    <div
      data-preview-open={previewSource ? "true" : "false"}
      className="chat-preview-shell flex h-full flex-col overflow-hidden bg-[var(--background)]"
    >
      <div className="mx-auto flex w-full max-w-[960px] items-center justify-between px-6 pt-3 pb-0">
        <div className="flex min-w-0 flex-col">
          <span className="text-[15px] font-semibold tracking-[-0.01em] text-[var(--foreground)]">
            {pageTitle}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownloadMarkdown}
            disabled={!state.messages.length}
            title={t("Download chat history as Markdown")}
            aria-label={t("Download chat history as Markdown")}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border)]/50 text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-[var(--border)]/50 disabled:hover:text-[var(--muted-foreground)]"
          >
            <Download size={15} strokeWidth={1.8} />
          </button>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-[960px] min-h-0 flex-1 flex-col overflow-hidden px-6">
        {!hasMessages ? (
          <div className="flex min-h-0 flex-1 animate-fade-in flex-col items-center justify-center">
            <div className="text-center">
              <h1 className="font-serif text-[36px] font-medium tracking-[-0.01em] text-[var(--foreground)]">
                {t("What would you like to learn?")}
              </h1>
              <p className="mt-4 text-[15px] text-[var(--muted-foreground)]">
                {t("Ask anything - I'm here to help you understand.")}
              </p>
            </div>
          </div>
        ) : (
          <div
            ref={messagesContainerRef}
            data-chat-scroll-root="true"
            onScroll={handleMessagesScroll}
            className={`mx-auto w-full min-h-0 flex-1 space-y-7 overflow-y-auto pr-4 [scrollbar-gutter:stable] ${
              hasMessages ? "pt-0" : "pt-2 pb-6"
            }`}
            style={
              hasMessages
                ? (() => {
                    const maskImage =
                      "linear-gradient(to bottom, transparent 0px, #000 32px, #000 calc(100% - 40px), transparent 100%)";
                    return {
                      paddingBottom: "4px",
                      WebkitMaskImage: maskImage,
                      maskImage,
                    };
                  })()
                : undefined
            }
          >
            <ChatMessageList
              messages={state.messages}
              isStreaming={state.isStreaming}
              onCopyAssistantMessage={copyAssistantMessage}
              onRegenerateMessage={handleRegenerateMessage}
              onPreviewAttachment={handlePreviewMessageAttachment}
            />
            <div ref={messagesEndRef} className="h-px w-full shrink-0" />
          </div>
        )}

        <div className="relative w-full shrink-0">
          <ChatComposer
            composerRef={composerRef}
            toolMenuRef={toolMenuRef}
            toolBtnRef={toolBtnRef}
            projectMenuRef={projectMenuRef}
            projectBtnRef={projectBtnRef}
            dragCounter={dragCounter}
            dragging={dragging}
            toolMenuOpen={toolMenuOpen}
            projectMenuOpen={projectMenuOpen}
            hasMessages={hasMessages}
            attachments={attachments}
            attachmentError={attachmentError}
            visibleTools={visibleTools}
            selectedTools={selectedTools}
            llmOptions={llmOptions}
            activeLLMDefault={activeLLMDefault}
            llmSelection={state.llmSelection}
            llmOptionsLoading={llmOptionsLoading}
            llmOptionsError={llmOptionsError}
            currentProject={currentProject}
            selectedMemoryFiles={selectedMemoryFiles}
            isStreaming={state.isStreaming}
            onSetToolMenuOpen={setToolMenuOpen}
            onSetProjectMenuOpen={setProjectMenuOpen}
            onSelectLLM={setLLMSelection}
            onSelectMemoryPicker={handleSelectMemoryPicker}
            onToggleTool={handleToggleTool}
            onToggleMemoryFile={handleToggleMemoryFile}
            onSend={handleSend}
            onRemoveAttachment={handleRemoveAttachment}
            onPreviewAttachment={handlePreviewPendingAttachment}
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onPaste={handlePaste}
            onAddFiles={handleAddFiles}
            onCancelStreaming={cancelStreamingTurn}
          />

          {anchorOverlayVisible && activeProject ? (
            <section className="pointer-events-auto absolute inset-x-0 bottom-5 z-30 mx-auto w-full max-w-[960px] overflow-hidden rounded-2xl border border-[var(--border)]/80 bg-[color:color-mix(in_srgb,var(--card)_96%,black_4%)] text-[var(--foreground)] shadow-[0_18px_48px_rgba(0,0,0,0.36)] backdrop-blur-sm">
              <div className="px-4 pb-4 pt-4">
                <AnchorStepChoices
                  label={
                    anchorStep === "preferredMethod"
                      ? t("Preferred method")
                      : anchorStep === "priorKnowledge"
                        ? t("Prior knowledge")
                        : t("Target depth")
                  }
                  options={
                    anchorStep === "preferredMethod"
                      ? ANCHOR_METHOD_OPTIONS.map((option) => t(option))
                      : anchorStep === "priorKnowledge"
                        ? ANCHOR_PRIOR_KNOWLEDGE_OPTIONS.map((option) =>
                            t(option),
                          )
                        : ANCHOR_TARGET_DEPTH_OPTIONS.map((option) => t(option))
                  }
                  value={
                    anchorStep === "preferredMethod"
                      ? anchorPreferredMethod
                      : anchorStep === "priorKnowledge"
                        ? anchorPriorKnowledge
                        : anchorTargetDepth
                  }
                  customValue={anchorCustomDraft}
                  placeholder={t("Something else")}
                  skipLabel={t("Skip")}
                  onPick={(value) => {
                    if (anchorStep === "preferredMethod") {
                      setAnchorPreferredMethod(value);
                      setAnchorStep("priorKnowledge");
                      setAnchorCustomDraft("");
                      return;
                    }
                    if (anchorStep === "priorKnowledge") {
                      setAnchorPriorKnowledge(value);
                      setAnchorStep("targetDepth");
                      setAnchorCustomDraft("");
                      return;
                    }
                    setAnchorTargetDepth(value);
                    setAnchorCustomDraft("");
                    void completeAnchorFlow();
                  }}
                  onCustomChange={setAnchorCustomDraft}
                  onCustomSubmit={() => {
                    const nextValue = anchorCustomDraft.trim();
                    if (!nextValue) return;
                    if (anchorStep === "preferredMethod") {
                      setAnchorPreferredMethod(nextValue);
                      setAnchorStep("priorKnowledge");
                    } else if (anchorStep === "priorKnowledge") {
                      setAnchorPriorKnowledge(nextValue);
                      setAnchorStep("targetDepth");
                    } else {
                      setAnchorTargetDepth(nextValue);
                      void completeAnchorFlow();
                    }
                    setAnchorCustomDraft("");
                  }}
                  onSkip={() => {
                    setAnchorCustomDraft("");
                    if (anchorStep === "preferredMethod") {
                      setAnchorStep("priorKnowledge");
                    } else if (anchorStep === "priorKnowledge") {
                      setAnchorStep("targetDepth");
                    } else {
                      void completeAnchorFlow();
                    }
                  }}
                />
                {anchorError ? (
                  <div className="mt-3 text-sm text-amber-600 dark:text-amber-300">
                    {anchorError}
                  </div>
                ) : null}
                {anchorSaving ? (
                  <div className="mt-3 text-xs text-[var(--muted-foreground)]">
                    {t("Saving learning anchor...")}
                  </div>
                ) : null}
              </div>
            </section>
          ) : null}
        </div>
      </div>

      <MemoryPicker
        open={showMemoryPicker}
        initialFiles={selectedMemoryFiles}
        onClose={handleCloseMemoryPicker}
        onApply={handleApplyMemoryFiles}
      />
      <FilePreviewDrawer
        open={previewSource !== null}
        source={previewSource}
        onClose={handleClosePreview}
      />
    </div>
  );
}
