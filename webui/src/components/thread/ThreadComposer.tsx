import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { MarkdownText, preloadMarkdownText } from "@/components/MarkdownText";
import {
  Activity,
  ArrowRight,
  ArrowUp,
  BookOpen,
  Bot,
  BrainCircuit,
  Check,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Database,
  History,
  ImageIcon,
  Loader2,
  Plus,
  RotateCw,
  Sparkles,
  Square,
  SquarePen,
  Target,
  Undo2,
  Workflow,
  X,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  useAttachedImages,
  type AttachedImage,
  type AttachmentError,
  MAX_IMAGES_PER_MESSAGE,
} from "@/hooks/useAttachedImages";
import { useClipboardAndDrop } from "@/hooks/useClipboardAndDrop";
import type { SendImage, SendOptions } from "@/hooks/useNanobotStream";
import type { SlashCommand, GoalStateWsPayload } from "@/lib/types";
import { cn } from "@/lib/utils";

/** ``<input accept>``: aligned with the server's MIME whitelist. SVG is
 * deliberately excluded to avoid an embedded-script XSS surface. */
const ACCEPT_ATTR = "image/png,image/jpeg,image/webp,image/gif";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function isPromiseLike(value: unknown): value is PromiseLike<unknown> {
  return (
    value != null &&
    typeof (value as { then?: unknown }).then === "function"
  );
}

interface ThreadComposerProps {
  onSend: (content: string, images?: SendImage[], options?: SendOptions) => void | Promise<void>;
  disabled?: boolean;
  placeholder?: string | string[];
  isStreaming?: boolean;
  modelLabel?: string | null;
  variant?: "thread" | "hero";
  slashCommands?: SlashCommand[];
  imageMode?: boolean;
  onImageModeChange?: (enabled: boolean) => void;
  sessionMode?: "chat" | "learning";
  onSessionModeChange?: (mode: "chat" | "learning") => void;
  learningPromptVisible?: boolean;
  onLearningPromptAccept?: () => void;
  onLearningPromptDismiss?: () => void;
  onStop?: () => void;
  /** Unix seconds from server; turn elapsed timer above input while set. */
  runStartedAt?: number | null;
  /** Sustained objective for this chat (WebSocket ``goal_state``). */
  goalState?: GoalStateWsPayload;
  /** Overlay rendered inside the composer container (e.g. intake questionnaire). */
  intakeOverlay?: React.ReactNode;
}

const COMMAND_ICONS: Record<string, LucideIcon> = {
  activity: Activity,
  "book-open": BookOpen,
  "circle-help": CircleHelp,
  history: History,
  "rotate-cw": RotateCw,
  sparkles: Sparkles,
  square: Square,
  "square-pen": SquarePen,
  "undo-2": Undo2,
};

type ImageAspectRatio = "auto" | "1:1" | "3:4" | "9:16" | "4:3" | "16:9";

const IMAGE_ASPECT_RATIOS: ImageAspectRatio[] = ["auto", "1:1", "3:4", "9:16", "4:3", "16:9"];
const SLASH_PALETTE_GAP_PX = 8;
const SLASH_PALETTE_MAX_HEIGHT_PX = 288;
const SLASH_PALETTE_MIN_HEIGHT_PX = 144;
const SLASH_PALETTE_CHROME_PX = 64;
const HERO_TOPIC_SUGGESTIONS = [
  {
    label: "AI \u5230\u5e95\u662f\u4ec0\u4e48\uff1f",
    prompt: "\u7528\u6700\u7b80\u5355\u7684\u8bdd\u8bb2\u8bb2\uff0cAI \u5230\u5e95\u662f\u4ec0\u4e48\uff1f",
    icon: BrainCircuit,
  },
  {
    label: "\u5927\u8bed\u8a00\u6a21\u578b\u600e\u4e48\u4f1a\u8bf4\u8bdd\uff1f",
    prompt: "\u5927\u8bed\u8a00\u6a21\u578b\u662f\u600e\u4e48\u5b66\u4f1a\u8bf4\u8bdd\u7684\uff1f",
    icon: Workflow,
  },
  {
    label: "RAG \u600e\u4e48\u5e2e\u6211\u67e5\u8d44\u6599\uff1f",
    prompt: "RAG \u662f\u600e\u4e48\u5e2e AI \u67e5\u6211\u7684\u8d44\u6599\u7684\uff1f",
    icon: Database,
  },
  {
    label: "AI Agent \u600e\u4e48\u81ea\u5df1\u5e72\u6d3b\uff1f",
    prompt: "AI Agent \u662f\u600e\u4e48\u81ea\u5df1\u5b8c\u6210\u4efb\u52a1\u7684\uff1f",
    icon: Bot,
  },
] as const;


type SlashPalettePlacement = "above" | "below";

interface SlashPaletteLayout {
  placement: SlashPalettePlacement;
  maxHeight: number;
}

function slashCommandI18nKey(command: string): string {
  return command.replace(/^\//, "").replace(/-/g, "_");
}

function scrollNearestOverflowParent(target: EventTarget | null, deltaY: number) {
  if (!(target instanceof Element) || deltaY === 0) return;
  let el: HTMLElement | null = target.parentElement;
  while (el) {
    const style = window.getComputedStyle(el);
    const canScroll = /(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight;
    if (canScroll) {
      el.scrollTop += deltaY;
      return;
    }
    el = el.parentElement;
  }
}

function getVisibleBounds(el: HTMLElement): { top: number; bottom: number } {
  let top = 0;
  let bottom = window.innerHeight;
  let parent = el.parentElement;

  while (parent) {
    const style = window.getComputedStyle(parent);
    if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
      const rect = parent.getBoundingClientRect();
      top = Math.max(top, rect.top);
      bottom = Math.min(bottom, rect.bottom);
    }
    parent = parent.parentElement;
  }

  return { top, bottom };
}

function goalStateStripPreview(
  goal: GoalStateWsPayload | undefined,
  t: (key: string) => string,
): string | null {
  if (!goal?.active) return null;
  const summary = goal.ui_summary?.trim();
  if (summary) return summary;
  const obj = goal.objective?.trim();
  if (obj) return obj.length > 72 ? `${obj.slice(0, 72)}…` : obj;
  return t("thread.composer.goalStateFallback");
}

const GOAL_PANEL_VIEWPORT_TOP_PAD = 20;
const GOAL_PANEL_GAP_ABOVE_STRIP_PX = 10;
const GOAL_PANEL_MIN_HEIGHT_PX = 112;
const GOAL_PANEL_MAX_VIEWPORT_RATIO = 0.62;

function measureGoalPanelMaxCssHeight(stripTopY: number): number {
  const spaceAboveStrip =
    stripTopY - GOAL_PANEL_VIEWPORT_TOP_PAD - GOAL_PANEL_GAP_ABOVE_STRIP_PX;
  return Math.min(
    Math.max(spaceAboveStrip, GOAL_PANEL_MIN_HEIGHT_PX),
    Math.floor(window.innerHeight * GOAL_PANEL_MAX_VIEWPORT_RATIO),
  );
}

function buildGoalMarkdownBody(summary: string, objective: string): string {
  const s = summary.trim();
  const o = objective.trim();
  if (s && o) return `${s}\n\n---\n\n${o}`;
  return o || s;
}

function RunElapsedStrip({
  startedAt,
  goalState,
}: {
  startedAt: number | null;
  goalState?: GoalStateWsPayload;
}) {
  const { t } = useTranslation();
  const [goalPanelOpen, setGoalPanelOpen] = useState(false);
  const [, setTick] = useState(0);
  const stripWrapperRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const expandToggleRef = useRef<HTMLButtonElement>(null);
  const [panelMaxPx, setPanelMaxPx] = useState(280);

  useEffect(() => {
    if (startedAt == null) return;
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [startedAt]);

  const showTimer = startedAt != null;
  const stripLabel = goalStateStripPreview(goalState, t);
  const showGoal = !!stripLabel?.trim();
  if (!showTimer && !showGoal) return null;

  const objectiveFull = goalState?.objective?.trim() ?? "";
  const summaryFull = goalState?.ui_summary?.trim() ?? "";
  const canExpandGoal = !!(goalState?.active && (objectiveFull || summaryFull));

  const markdownBody =
    objectiveFull || summaryFull
      ? buildGoalMarkdownBody(summaryFull, objectiveFull)
      : "";

  useLayoutEffect(() => {
    if (!goalPanelOpen) return;

    function relayout(): void {
      const el = stripWrapperRef.current;
      if (!el) return;
      const top = el.getBoundingClientRect().top;
      setPanelMaxPx(measureGoalPanelMaxCssHeight(top));
    }

    relayout();

    preloadMarkdownText();
    const ro =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => relayout())
        : null;
    if (stripWrapperRef.current && ro) {
      ro.observe(stripWrapperRef.current);
    }
    window.addEventListener("resize", relayout);
    window.addEventListener("scroll", relayout, true);
    return () => {
      ro?.disconnect();
      window.removeEventListener("resize", relayout);
      window.removeEventListener("scroll", relayout, true);
    };
  }, [goalPanelOpen]);

  useEffect(() => {
    if (!goalPanelOpen) return;

    function onPointerDown(ev: MouseEvent): void {
      const target = ev.target as Node | null;
      if (!target) return;
      if (panelRef.current?.contains(target)) return;
      if (expandToggleRef.current?.contains(target)) return;
      setGoalPanelOpen(false);
    }

    function onKey(ev: KeyboardEvent): void {
      if (ev.key === "Escape") setGoalPanelOpen(false);
    }

    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [goalPanelOpen]);

  const elapsed =
    startedAt != null ? Math.max(0, Math.floor(Date.now() / 1000 - startedAt)) : 0;
  const m = Math.floor(elapsed / 60);
  const sec = elapsed % 60;
  const shortElapsed = m > 0 ? `${m}:${sec.toString().padStart(2, "0")}` : `${sec}s`;
  const timerTitle = showTimer
    ? t("thread.composer.runRuntimeTitle", { elapsed: shortElapsed })
    : null;

  const ariaParts = [timerTitle, showGoal ? stripLabel : null].filter(Boolean);
  const ariaLabel = ariaParts.join(" · ");

  return (
    <div ref={stripWrapperRef} className="relative z-30">
      <div
        className="flex min-h-[36px] items-center gap-2 px-3 py-2"
        role="status"
        aria-label={ariaLabel}
      >
        {showTimer ? (
          <Activity className="h-4 w-4 shrink-0 text-primary/80" aria-hidden />
        ) : (
          <Target className="h-4 w-4 shrink-0 text-primary/75" aria-hidden />
        )}
        <span className="flex min-w-0 flex-1 items-center gap-1.5 text-sm font-medium text-foreground/75">
          {timerTitle ? <span className="shrink-0">{timerTitle}</span> : null}
          {timerTitle && showGoal ? (
            <span className="shrink-0 text-muted-foreground/45" aria-hidden>
              ·
            </span>
          ) : null}
          {showGoal ? (
            <span className="truncate">
              {stripLabel}
            </span>
          ) : null}
        </span>
        {canExpandGoal ? (
          <button
            ref={expandToggleRef}
            type="button"
            className={cn(
              "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
              "text-muted-foreground transition-colors hover:bg-muted/55 hover:text-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            )}
            aria-expanded={goalPanelOpen}
            aria-label={t("thread.composer.goalStateExpandAria")}
            title={t("thread.composer.goalStateExpandAria")}
            onClick={() => setGoalPanelOpen((o) => !o)}
          >
            {goalPanelOpen ? (
              <ChevronDown className="h-4 w-4" aria-hidden />
            ) : (
              <ChevronUp className="h-4 w-4" aria-hidden />
            )}
          </button>
        ) : null}
      </div>
      {goalPanelOpen && canExpandGoal && markdownBody ? (
        <div
          ref={panelRef}
          id="nanobot-goal-panel-root"
          className="border-t border-border/40 px-3 pb-3 pt-2"
          style={{ maxHeight: `${Math.round(panelMaxPx)}px`, overflowY: "auto" }}
        >
          <MarkdownText className="max-w-none text-sm leading-relaxed text-foreground/90">
            {markdownBody}
          </MarkdownText>
        </div>
      ) : null}
    </div>
  );
}

function LearningPromptStrip({
  onAccept,
  onDismiss,
}: {
  onAccept?: () => void;
  onDismiss?: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div
      className="flex min-h-[42px] items-center gap-2 border-b border-black/[0.04] px-3 py-2 dark:border-white/[0.06]"
      role="status"
      aria-live="polite"
    >
      <Sparkles className="h-4 w-4 shrink-0 text-foreground/75" aria-hidden />
      <span className="min-w-0 flex-1 truncate text-sm text-foreground/75">
        {t("thread.learningPrompt.title")} CoLearn将和你一起学习
      </span>
      <button
        type="button"
        aria-label={t("thread.learningPrompt.dismiss")}
        onClick={onDismiss}
        className={cn(
          "shrink-0 rounded-[10px] px-2.5 py-1.5 text-sm text-muted-foreground",
          "transition-colors hover:bg-muted/65 hover:text-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        )}
      >
        {t("thread.learningPrompt.dismiss")}
      </button>
      <button
        type="button"
        aria-label={t("thread.learningPrompt.accept")}
        onClick={onAccept}
        className={cn(
          "shrink-0 rounded-[10px] bg-[#013FF8] px-3 py-1.5 text-sm font-medium text-white",
          "transition-colors hover:bg-[#0137d8]",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        )}
      >
        {t("thread.learningPrompt.accept")}
      </button>
    </div>
  );
}

export function ThreadComposer({
  onSend,
  disabled,
  placeholder,
  isStreaming = false,
  modelLabel = null,
  variant = "thread",
  slashCommands = [],
  imageMode: controlledImageMode,
  onImageModeChange,
  sessionMode = "chat",
  onSessionModeChange,
  learningPromptVisible = false,
  onLearningPromptAccept,
  onLearningPromptDismiss,
  onStop,
  runStartedAt = null,
  goalState,
  intakeOverlay,
}: ThreadComposerProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const [inlineError, setInlineError] = useState<string | null>(null);
  const [slashMenuDismissed, setSlashMenuDismissed] = useState(false);
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const [uncontrolledImageMode, setUncontrolledImageMode] = useState(false);
  const [imageAspectRatio, setImageAspectRatio] = useState<ImageAspectRatio>("auto");
  const [aspectMenuOpen, setAspectMenuOpen] = useState(false);
  const [heroPlaceholderIndex, setHeroPlaceholderIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const aspectControlRef = useRef<HTMLDivElement>(null);
  const chipRefs = useRef(new Map<string, HTMLButtonElement>());
  const isHero = variant === "hero";
  const imageMode = controlledImageMode ?? uncontrolledImageMode;
  const learningMode = sessionMode === "learning";
  const setImageMode = useCallback(
    (enabled: boolean) => {
      if (controlledImageMode === undefined) {
        setUncontrolledImageMode(enabled);
      }
      onImageModeChange?.(enabled);
    },
    [controlledImageMode, onImageModeChange],
  );
  const toggleLearningMode = useCallback(() => {
    onSessionModeChange?.(learningMode ? "chat" : "learning");
    textareaRef.current?.focus();
  }, [learningMode, onSessionModeChange]);
  const placeholderItems = Array.isArray(placeholder) ? placeholder.filter(Boolean) : [];

  useEffect(() => {
    if (!isHero || placeholderItems.length <= 1 || value.trim() || isStreaming || imageMode) return;
    const id = window.setInterval(() => {
      setHeroPlaceholderIndex((index) => (index + 1) % placeholderItems.length);
    }, 2800);
    return () => window.clearInterval(id);
  }, [imageMode, isHero, isStreaming, placeholderItems, value]);

  useEffect(() => {
    setHeroPlaceholderIndex(0);
  }, [placeholderItems]);

  const resolvedPlaceholder = imageMode
      ? t("thread.composer.imageMode.placeholder")
      : placeholderItems[heroPlaceholderIndex] ?? (typeof placeholder === "string" ? placeholder : t("thread.composer.placeholderThread"));

  const { images, enqueue, remove, clear, encoding, full } =
    useAttachedImages();

  const formatRejection = useCallback(
    (reason: AttachmentError): string => {
      const key = `thread.composer.imageRejected.${reason}`;
      return t(key, { max: MAX_IMAGES_PER_MESSAGE });
    },
    [t],
  );

  const addFiles = useCallback(
    (files: File[]) => {
      if (files.length === 0) return;
      const { rejected } = enqueue(files);
      if (rejected.length > 0) {
        setInlineError(formatRejection(rejected[0].reason));
      } else {
        setInlineError(null);
      }
    },
    [enqueue, formatRejection],
  );

  const {
    isDragging,
    onPaste,
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,
  } = useClipboardAndDrop(addFiles);

  useEffect(() => {
    if (disabled) return;
    const el = textareaRef.current;
    if (!el) return;
    const id = requestAnimationFrame(() => el.focus());
    return () => cancelAnimationFrame(id);
  }, [disabled]);

  const readyImages = useMemo(
    () => images.filter((img): img is AttachedImage & { dataUrl: string } =>
      img.status === "ready" && typeof img.dataUrl === "string",
    ),
    [images],
  );
  const hasErrors = images.some((img) => img.status === "error");

  const canSend =
    !disabled
    && !encoding
    && !hasErrors
    && (value.trim().length > 0 || readyImages.length > 0);

  const slashQuery = useMemo(() => {
    if (disabled || slashMenuDismissed || !value.startsWith("/")) return null;
    const commandToken = value.slice(1);
    if (/\s/.test(commandToken)) return null;
    return commandToken.toLowerCase();
  }, [disabled, slashMenuDismissed, value]);

  const filteredSlashCommands = useMemo(() => {
    if (slashQuery === null) return [];
    return slashCommands
      .filter((command) => {
        const haystack = [
          command.command,
          command.title,
          command.description,
          command.argHint ?? "",
          t(`thread.composer.slash.commands.${slashCommandI18nKey(command.command)}.title`, {
            defaultValue: "",
          }),
          t(`thread.composer.slash.commands.${slashCommandI18nKey(command.command)}.description`, {
            defaultValue: "",
          }),
        ].join(" ").toLowerCase();
        return haystack.includes(slashQuery);
      })
      .slice(0, 8);
  }, [slashCommands, slashQuery, t]);

  const showSlashMenu = filteredSlashCommands.length > 0;
  const [slashPaletteLayout, setSlashPaletteLayout] = useState<SlashPaletteLayout>({
    placement: "above",
    maxHeight: SLASH_PALETTE_MAX_HEIGHT_PX,
  });

  useEffect(() => {
    setSelectedCommandIndex(0);
  }, [slashQuery]);

  useEffect(() => {
    if (selectedCommandIndex >= filteredSlashCommands.length) {
      setSelectedCommandIndex(0);
    }
  }, [filteredSlashCommands.length, selectedCommandIndex]);

  useEffect(() => {
    if (!showSlashMenu) return;

    const dismissOnPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && formRef.current?.contains(target)) return;
      setSlashMenuDismissed(true);
    };

    document.addEventListener("pointerdown", dismissOnPointerDown, true);
    return () => {
      document.removeEventListener("pointerdown", dismissOnPointerDown, true);
    };
  }, [showSlashMenu]);

  useLayoutEffect(() => {
    if (!showSlashMenu) return;

    const updateLayout = () => {
      const form = formRef.current;
      if (!form) return;
      const rect = form.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) return;

      const bounds = getVisibleBounds(form);
      const spaceAbove = Math.max(0, rect.top - bounds.top - SLASH_PALETTE_GAP_PX);
      const spaceBelow = Math.max(0, bounds.bottom - rect.bottom - SLASH_PALETTE_GAP_PX);
      const placement: SlashPalettePlacement =
        spaceAbove >= SLASH_PALETTE_MIN_HEIGHT_PX || spaceAbove >= spaceBelow
          ? "above"
          : "below";
      const available = placement === "above" ? spaceAbove : spaceBelow;
      const maxHeight = Math.min(SLASH_PALETTE_MAX_HEIGHT_PX, available);

      setSlashPaletteLayout((current) =>
        current.placement === placement && current.maxHeight === maxHeight
          ? current
          : { placement, maxHeight },
      );
    };

    updateLayout();
    window.addEventListener("resize", updateLayout);
    document.addEventListener("scroll", updateLayout, true);
    return () => {
      window.removeEventListener("resize", updateLayout);
      document.removeEventListener("scroll", updateLayout, true);
    };
  }, [filteredSlashCommands.length, showSlashMenu]);

  useEffect(() => {
    if (!aspectMenuOpen) return;

    const closeOnPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && aspectControlRef.current?.contains(target)) return;
      setAspectMenuOpen(false);
    };
    const closeOnKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setAspectMenuOpen(false);
        textareaRef.current?.focus();
      }
    };
    const closeOnScroll = () => setAspectMenuOpen(false);
    const closeOnWheel = (event: WheelEvent) => {
      setAspectMenuOpen(false);
      scrollNearestOverflowParent(event.target, event.deltaY);
    };

    document.addEventListener("pointerdown", closeOnPointerDown, true);
    document.addEventListener("keydown", closeOnKeyDown);
    document.addEventListener("scroll", closeOnScroll, true);
    document.addEventListener("wheel", closeOnWheel, { capture: true, passive: true });
    return () => {
      document.removeEventListener("pointerdown", closeOnPointerDown, true);
      document.removeEventListener("keydown", closeOnKeyDown);
      document.removeEventListener("scroll", closeOnScroll, true);
      document.removeEventListener("wheel", closeOnWheel, true);
    };
  }, [aspectMenuOpen]);

  const resizeTextarea = useCallback(() => {
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
      el.focus();
    });
  }, []);

  const chooseSlashCommand = useCallback(
    (command: SlashCommand) => {
      setValue(command.argHint ? `${command.command} ` : command.command);
      setSlashMenuDismissed(true);
      setInlineError(null);
      resizeTextarea();
    },
    [resizeTextarea],
  );

  const submit = useCallback(() => {
    if (!canSend) return;
    const trimmed = value.trim();
    // Share the same normalized ``data:`` URL with both the wire payload and
    // the optimistic bubble preview: data URLs are self-contained (no blob
    // lifetime, safe under React StrictMode double-mount) and keep the
    // bubble in sync with whatever the backend actually sees.
    const payload: SendImage[] | undefined =
      readyImages.length > 0
        ? readyImages.map((img) => ({
            media: {
              data_url: img.dataUrl,
              name: img.file.name,
            },
            preview: { url: img.dataUrl, name: img.file.name },
          }))
        : undefined;
    const options: SendOptions | undefined = imageMode
      ? {
          imageGeneration: {
            enabled: true,
            aspect_ratio: imageAspectRatio === "auto" ? null : imageAspectRatio,
          },
        }
      : undefined;
    const clearComposer = () => {
      setValue("");
      setInlineError(null);
      // Bubble owns the data URL copy; safe to revoke every staged blob
      // preview here without affecting the rendered message.
      clear();
      setSlashMenuDismissed(false);
      resizeTextarea();
    };

    try {
      const result = onSend(trimmed, payload, options);
      if (isPromiseLike(result)) {
        void result.then(clearComposer).catch((error) => {
          console.error("Failed to send message", error);
        });
        return;
      }
      clearComposer();
    } catch (error) {
      console.error("Failed to send message", error);
    }
  }, [canSend, clear, imageAspectRatio, imageMode, onSend, readyImages, resizeTextarea, value]);

  const insertHeroTopic = useCallback((topic: string) => {
    setValue(topic);
    setSlashMenuDismissed(false);
    setInlineError(null);
    requestAnimationFrame(() => {
      resizeTextarea();
      textareaRef.current?.focus();
    });
  }, [resizeTextarea]);

  const onKeyDown = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashMenu) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedCommandIndex((idx) => (idx + 1) % filteredSlashCommands.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedCommandIndex(
          (idx) => (idx - 1 + filteredSlashCommands.length) % filteredSlashCommands.length,
        );
        return;
      }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        e.preventDefault();
        chooseSlashCommand(filteredSlashCommands[selectedCommandIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setSlashMenuDismissed(true);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const onInput: React.FormEventHandler<HTMLTextAreaElement> = (e) => {
    const el = e.currentTarget;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
  };

  const onFilePick: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    addFiles(files);
  };

  const removeChip = useCallback(
    (id: string) => {
      const { nextFocusId } = remove(id);
      setInlineError(null);
      requestAnimationFrame(() => {
        const el = nextFocusId ? chipRefs.current.get(nextFocusId) : null;
        if (el) {
          el.focus();
        } else {
          textareaRef.current?.focus();
        }
      });
    },
    [remove],
  );

  const onChipKey = useCallback(
    (id: string) => (e: ReactKeyboardEvent<HTMLButtonElement>) => {
      if (
        e.key === "Delete" ||
        e.key === "Backspace" ||
        e.key === "Enter" ||
        e.key === " "
      ) {
        e.preventDefault();
        removeChip(id);
      }
    },
    [removeChip],
  );

  const attachButtonDisabled = disabled || full;
  const showStopButton = isStreaming && !!onStop;

  return (
    <form
      ref={formRef}
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={cn("relative w-full", isHero ? "px-0" : "px-1 pb-1.5 pt-1 sm:px-0")}
      >
        {showSlashMenu ? (
          <SlashCommandPalette
          commands={filteredSlashCommands}
          selectedIndex={selectedCommandIndex}
          layout={slashPaletteLayout}
          isHero={isHero}
          onHover={setSelectedCommandIndex}
          onChoose={chooseSlashCommand}
        />
      ) : null}
      <div
        className={cn(
          "relative mx-auto flex w-full flex-col overflow-visible transition-all duration-200",
          isHero
            ? "max-w-[58rem] rounded-[28px] border border-black/[0.14] bg-card shadow-[0_20px_55px_rgba(15,23,42,0.08)] dark:border-white/[0.16] dark:shadow-[0_24px_55px_rgba(0,0,0,0.34)]"
            : "max-w-[49.5rem] rounded-[22px] border border-black/[0.14] bg-card shadow-[0_12px_30px_rgba(15,23,42,0.07)] dark:border-white/[0.16] dark:shadow-[0_16px_34px_rgba(0,0,0,0.28)]",
          "focus-within:ring-1 focus-within:ring-foreground/8",
          disabled && "opacity-60",
          isDragging && "ring-2 ring-primary/40 motion-reduce:ring-0 motion-reduce:border-primary",
          (learningMode || goalState?.active)
            && "goal-shell-glow ring-1 ring-[#013FF8]/35 motion-reduce:ring-[#013FF8]/25 dark:ring-[#013FF8]/45",
        )}
      >
        {intakeOverlay || null}
        {!intakeOverlay && learningPromptVisible ? (
          <LearningPromptStrip
            onAccept={onLearningPromptAccept}
            onDismiss={onLearningPromptDismiss}
          />
        ) : null}
        {!intakeOverlay && images.length > 0 ? (
          <div
            className="flex flex-wrap gap-2 px-3 pt-3"
            aria-label={t("thread.composer.attachImage")}
          >
            {images.map((img) => (
              <AttachmentChip
                key={img.id}
                image={img}
                labelRemove={t("thread.composer.remove")}
                labelEncoding={t("thread.composer.encoding")}
                normalizedHint={(orig, current) =>
                  t("thread.composer.normalizedSizeHint", {
                    orig: formatBytes(orig),
                    current: formatBytes(current),
                  })
                }
                formatError={formatRejection}
                onRemove={() => removeChip(img.id)}
                onKeyDown={onChipKey(img.id)}
                registerRef={(el) => {
                  if (el) chipRefs.current.set(img.id, el);
                  else chipRefs.current.delete(img.id);
                }}
              />
            ))}
          </div>
        ) : null}
        {!intakeOverlay && (runStartedAt != null || goalState?.active) ? (
          <RunElapsedStrip startedAt={runStartedAt} goalState={goalState} />
        ) : null}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setSlashMenuDismissed(false);
          }}
          onInput={onInput}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          rows={1}
          placeholder={resolvedPlaceholder}
          disabled={disabled}
          aria-label={t("thread.composer.inputAria")}
          className={cn(
            "w-full resize-none bg-transparent",
            isHero
              ? "min-h-[78px] px-5 pb-2 pt-5 text-sm leading-6"
              : "min-h-[50px] px-4 pb-1.5 pt-3 text-sm leading-5",
            "placeholder:text-muted-foreground/70",
            "focus:outline-none focus-visible:outline-none",
            "disabled:cursor-not-allowed",
            intakeOverlay && "hidden",
          )}
        />
        {inlineError ? (
          <div
            role="alert"
            className={cn(
              "mx-3 mb-1 rounded-md border border-destructive/40 bg-destructive/8 px-2.5 py-1",
              "text-sm font-medium text-destructive",
            )}
          >
            {inlineError}
          </div>
        ) : null}
        <div
          className={cn(
            "flex items-center justify-between gap-2",
            isHero ? "px-4 pb-4" : "px-3 pb-2",
            intakeOverlay && "hidden",
          )}
        >
          <div className="flex min-w-0 items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT_ATTR}
              multiple
              hidden
              onChange={onFilePick}
            />
            <Button
              type="button"
              size="icon"
              variant="ghost"
              disabled={attachButtonDisabled}
              aria-label={t("thread.composer.attachImage")}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "rounded-full text-muted-foreground hover:text-foreground",
                isHero ? "h-9 w-9 bg-card hover:bg-card" : "h-9 w-9 bg-card hover:bg-card",
              )}
            >
              <Plus className={cn(isHero ? "h-5 w-5" : "h-5 w-5")} />
            </Button>
            <div ref={aspectControlRef} className="relative flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                disabled={disabled}
                aria-pressed={learningMode}
                aria-label={t("thread.composer.learningMode.toggle")}
                title={t("thread.composer.learningMode.toggle")}
                onClick={toggleLearningMode}
                className={cn(
                  "rounded-full px-2.5 font-medium",
                  "h-9 text-sm",
                  learningMode
                    ? "bg-[#013FF8]/10 text-[#013FF8] hover:bg-[#013FF8]/14 dark:bg-[#013FF8]/16 dark:text-[#7DA0FF] dark:hover:bg-[#013FF8]/22"
                    : "bg-card text-muted-foreground hover:bg-card hover:text-foreground",
                )}
              >
                <BookOpen className={cn("mr-1.5", isHero ? "h-4 w-4" : "h-3.5 w-3.5")} />
                {learningMode
                  ? t("thread.composer.learningMode.learning")
                  : t("thread.composer.learningMode.chat")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                disabled={disabled}
                aria-pressed={imageMode}
                aria-label={t("thread.composer.imageMode.toggle")}
                onClick={() => {
                  setImageMode(!imageMode);
                  setAspectMenuOpen(false);
                  textareaRef.current?.focus();
                }}
                className={cn(
                  "rounded-full px-2.5 font-medium",
                  "h-9 text-sm",
                  imageMode
                    ? "border-primary/30 bg-primary/10 text-primary hover:bg-primary/12"
                    : "bg-card text-muted-foreground hover:bg-card hover:text-foreground",
                )}
              >
                <ImageIcon className={cn("mr-1.5", isHero ? "h-4 w-4" : "h-3.5 w-3.5")} />
                {t("thread.composer.imageMode.label")}
              </Button>
              {imageMode ? (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={disabled}
                  aria-haspopup="listbox"
                  aria-expanded={aspectMenuOpen}
                  aria-label={t("thread.composer.imageMode.aspectAria")}
                  onClick={() => setAspectMenuOpen((open) => !open)}
                  className={cn(
                    "rounded-full bg-card px-2.5 font-medium text-foreground/80 hover:bg-card",
                    "h-9 text-sm",
                  )}
                >
                  <span>{t(`thread.composer.imageMode.aspect.${imageAspectRatio.replace(":", "_")}`)}</span>
                  <ChevronDown className={cn("ml-1.5", isHero ? "h-3.5 w-3.5" : "h-3 w-3")} />
                </Button>
              ) : null}
              {imageMode && aspectMenuOpen ? (
                <ImageAspectMenu
                  selected={imageAspectRatio}
                  isHero={isHero}
                  onSelect={(ratio) => {
                    setImageAspectRatio(ratio);
                    setAspectMenuOpen(false);
                    textareaRef.current?.focus();
                  }}
                />
              ) : null}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {modelLabel ? (
              <span
                title={modelLabel}
                className={cn(
                  "inline-flex min-w-0 font-medium text-foreground/72",
                  isHero
                    ? "max-w-[13rem] text-sm"
                    : "max-w-[12rem] text-sm",
                )}
              >
                <span className="truncate">{modelLabel}</span>
              </span>
            ) : null}
            <Button
              type={showStopButton ? "button" : "submit"}
              variant="ghost"
              size="icon"
              disabled={showStopButton ? disabled : !canSend}
              aria-label={showStopButton ? t("thread.composer.stop") : t("thread.composer.send")}
              onClick={showStopButton ? onStop : undefined}
              className={cn(
                "rounded-full transition-transform disabled:opacity-100",
                showStopButton
                  ? "bg-card text-foreground/85 shadow-[0_3px_10px_rgba(15,23,42,0.08)] hover:bg-muted/65 hover:text-foreground disabled:text-muted-foreground/50"
                  : canSend
                    ? "!bg-[#1A1C1F] text-background shadow-[0_3px_10px_rgba(15,23,42,0.18)] hover:!bg-[#1A1C1F]/90 disabled:!bg-[#1A1C1F]/35 disabled:text-background/80"
                    : "!bg-[#8C8D8F] text-background shadow-[0_3px_10px_rgba(15,23,42,0.18)] hover:!bg-[#8C8D8F]/90 disabled:!bg-[#8C8D8F]/35 disabled:text-background/80",
                isHero ? "" : "h-8 w-8",
                (canSend || showStopButton) && "hover:scale-[1.03] active:scale-95",
              )}
            >
              {showStopButton ? (
                <Square className={cn("fill-current stroke-current", isHero ? "h-3 w-3" : "h-3 w-3")} />
              ) : isStreaming ? (
                <Loader2 className={cn(isHero ? "h-4 w-4" : "h-4 w-4", "animate-spin")} />
              ) : (
                <ArrowUp className={cn(isHero ? "h-4 w-4" : "h-4 w-4")} />
              )}
            </Button>
          </div>
        </div>
      </div>
      {isHero ? (
        <div className="mt-4 w-full max-w-[36rem] overflow-hidden rounded-2xl">
          {HERO_TOPIC_SUGGESTIONS.map((topic, index) => {
            const Icon = topic.icon;
            return (
              <button
                key={topic.label}
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  insertHeroTopic(topic.prompt);
                }}
                className={cn(
                  "group flex w-full items-center gap-3 px-3 py-3 text-left",
                  "transition-colors hover:bg-accent/40",
                  "focus-visible:outline-none focus-visible:bg-accent/40",
                  index > 0 && "border-t border-border/40",
                )}
              >
                <Icon
                  className="h-[18px] w-[18px] shrink-0 text-muted-foreground transition-colors group-hover:text-foreground"
                  aria-hidden
                />
                <span className="min-w-0 flex-1 truncate text-sm text-foreground/80 transition-colors group-hover:text-foreground">
                  {topic.label}
                </span>
                <ArrowRight
                  className={cn(
                    "h-[18px] w-[18px] shrink-0 text-muted-foreground",
                    "translate-x-1 opacity-0 transition-all",
                    "group-hover:translate-x-0 group-hover:opacity-100",
                  )}
                  aria-hidden
                />
              </button>
            );
          })}
        </div>
      ) : null}
    </form>
  );
}

interface SlashCommandPaletteProps {
  commands: SlashCommand[];
  selectedIndex: number;
  layout: SlashPaletteLayout;
  isHero: boolean;
  onHover: (index: number) => void;
  onChoose: (command: SlashCommand) => void;
}

function ImageAspectMenu({
  selected,
  isHero,
  onSelect,
}: {
  selected: ImageAspectRatio;
  isHero: boolean;
  onSelect: (ratio: ImageAspectRatio) => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      role="listbox"
      aria-label={t("thread.composer.imageMode.aspectAria")}
      className={cn(
        "absolute left-0 z-30 w-44 overflow-hidden rounded-[16px] border",
        isHero ? "top-full mt-2" : "bottom-full mb-2",
        "border-border/65 bg-popover p-1.5 text-popover-foreground shadow-[0_16px_45px_rgba(15,23,42,0.16)]",
        "dark:border-white/10 dark:shadow-[0_18px_45px_rgba(0,0,0,0.42)]",
        "text-sm",
      )}
    >
      <div className="px-2 pb-1 pt-1 font-medium text-muted-foreground/70">
        {t("thread.composer.imageMode.aspectLabel")}
      </div>
      {IMAGE_ASPECT_RATIOS.map((ratio) => {
        const label = t(`thread.composer.imageMode.aspect.${ratio.replace(":", "_")}`);
        return (
          <button
            key={ratio}
            type="button"
            role="option"
            aria-selected={selected === ratio}
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(ratio);
            }}
            className={cn(
              "flex w-full items-center justify-between rounded-[11px] px-2.5 py-2 text-left transition-colors",
              selected === ratio
                ? "bg-primary/10 text-foreground"
                : "text-foreground/86 hover:bg-accent/55",
            )}
          >
            <span>{label}</span>
            {selected === ratio ? <Check className="h-3.5 w-3.5 text-primary" /> : null}
          </button>
        );
      })}
    </div>
  );
}

function SlashCommandPalette({
  commands,
  selectedIndex,
  layout,
  isHero,
  onHover,
  onChoose,
}: SlashCommandPaletteProps) {
  const { t } = useTranslation();
  const listMaxHeight = Math.max(
    0,
    layout.maxHeight - SLASH_PALETTE_CHROME_PX,
  );
  return (
    <div
      role="listbox"
      aria-label={t("thread.composer.slash.ariaLabel")}
      style={{ maxHeight: layout.maxHeight }}
      className={cn(
        "absolute left-1/2 z-30 w-[calc(100%-0.5rem)] -translate-x-1/2 overflow-hidden rounded-[18px] border",
        layout.placement === "above" ? "bottom-full mb-2" : "top-full mt-2",
        "border-border/65 bg-popover p-1.5 text-popover-foreground shadow-[0_18px_55px_rgba(15,23,42,0.18)]",
        "dark:border-white/10 dark:shadow-[0_22px_55px_rgba(0,0,0,0.45)]",
        isHero ? "max-w-[58rem]" : "max-w-[49.5rem]",
      )}
    >
      <div className="px-2 pb-1 pt-1 text-sm font-medium tracking-[0.08em] text-muted-foreground/70">
        {t("thread.composer.slash.label")}
      </div>
      <div className="overflow-y-auto pr-0.5" style={{ maxHeight: listMaxHeight }}>
        {commands.map((command, index) => {
          const Icon = COMMAND_ICONS[command.icon] ?? CircleHelp;
          const selected = index === selectedIndex;
          const commandKey = slashCommandI18nKey(command.command);
          const title = t(`thread.composer.slash.commands.${commandKey}.title`, {
            defaultValue: command.title,
          });
          const description = t(`thread.composer.slash.commands.${commandKey}.description`, {
            defaultValue: command.description,
          });
          return (
            <button
              key={command.command}
              type="button"
              role="option"
              aria-selected={selected}
              onMouseEnter={() => onHover(index)}
              onMouseDown={(e) => {
                e.preventDefault();
                onChoose(command);
              }}
              className={cn(
                "flex w-full items-center gap-3 rounded-[13px] px-3 py-2.5 text-left transition-colors",
                selected
                  ? "bg-primary/10 text-foreground"
                  : "text-foreground/86 hover:bg-accent/55",
              )}
            >
              <span
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] border",
                  selected
                    ? "border-primary/25 bg-primary/12 text-primary"
                    : "border-border/65 bg-muted/45 text-muted-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex min-w-0 items-baseline gap-2">
                  <span className="font-mono text-sm font-semibold text-foreground">
                    {command.command}
                  </span>
                  {command.argHint ? (
                    <span className="font-mono text-sm text-muted-foreground">
                      {command.argHint}
                    </span>
                  ) : null}
                  <span className="truncate text-sm font-medium">
                    {title}
                  </span>
                </span>
                <span className="mt-0.5 block truncate text-sm text-muted-foreground">
                  {description}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      <div className="flex items-center gap-2 px-2 pt-1.5 text-sm text-muted-foreground/70">
        <span>{t("thread.composer.slash.navigateHint")}</span>
        <span>{t("thread.composer.slash.selectHint")}</span>
        <span>{t("thread.composer.slash.closeHint")}</span>
      </div>
    </div>
  );
}

interface AttachmentChipProps {
  image: AttachedImage;
  labelRemove: string;
  labelEncoding: string;
  normalizedHint: (origBytes: number, currentBytes: number) => string;
  formatError: (reason: AttachmentError) => string;
  onRemove: () => void;
  onKeyDown: (e: ReactKeyboardEvent<HTMLButtonElement>) => void;
  registerRef: (el: HTMLButtonElement | null) => void;
}

function AttachmentChip({
  image,
  labelRemove,
  labelEncoding,
  normalizedHint,
  formatError,
  onRemove,
  onKeyDown,
  registerRef,
}: AttachmentChipProps) {
  const sizeLabel =
    image.status === "ready" && image.normalized && image.encodedBytes
      ? normalizedHint(image.file.size, image.encodedBytes)
      : formatBytes(image.file.size);
  const tone =
    image.status === "error"
      ? "border-destructive/40 bg-destructive/5 text-destructive"
      : "border-border/70 bg-muted/60";

  return (
    <div
      className={cn(
        "group relative flex items-center gap-2 rounded-[12px] border px-2 py-1.5",
        "transition-colors motion-reduce:transition-none",
        tone,
      )}
      data-testid="composer-chip"
    >
      <div className="relative h-10 w-10 overflow-hidden rounded-md bg-background">
        {image.previewUrl ? (
          <img
            src={image.previewUrl}
            alt=""
            aria-hidden
            loading="eager"
            draggable={false}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <ImageIcon className="h-4 w-4 text-muted-foreground" aria-hidden />
          </div>
        )}
        {image.status === "encoding" ? (
          <div
            className="absolute inset-0 flex items-center justify-center bg-background/60"
            aria-label={labelEncoding}
          >
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />
          </div>
        ) : null}
      </div>
      <div className="flex min-w-0 flex-col text-sm leading-4">
        <span className="truncate max-w-[14rem] font-medium" title={image.file.name}>
          {image.file.name}
        </span>
        <span className="truncate text-muted-foreground">
          {image.status === "error" && image.error
            ? formatError(image.error)
            : sizeLabel}
        </span>
      </div>
      <button
        type="button"
        ref={registerRef}
        onClick={onRemove}
        onKeyDown={onKeyDown}
        aria-label={labelRemove}
        className={cn(
          "ml-1 grid h-5 w-5 flex-none place-items-center rounded-full",
          "text-muted-foreground/80 hover:bg-foreground/8 hover:text-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/30",
        )}
      >
        <X className="h-3.5 w-3.5" aria-hidden />
      </button>
    </div>
  );
}
