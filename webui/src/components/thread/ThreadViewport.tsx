import {
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { ArrowDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LearningSupportPanel } from "@/components/thread/LearningSupportPanel";
import { ThreadMessages } from "@/components/thread/ThreadMessages";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { LearningSupportPayload, UIMessage } from "@/lib/types";

interface ThreadViewportProps {
  messages: UIMessage[];
  isStreaming: boolean;
  composer: ReactNode;
  emptyState?: ReactNode;
  scrollToBottomSignal?: number;
  conversationKey?: string | null;
  learningSupport?: LearningSupportPayload | null;
}

const NEAR_BOTTOM_PX = 48;
const LEARNING_PANEL_MIN_WIDTH = 280;
const LEARNING_PANEL_MAX_WIDTH = 560;
const LEARNING_PANEL_DEFAULT_WIDTH = 360;

export function ThreadViewport({
  messages,
  isStreaming,
  composer,
  emptyState,
  scrollToBottomSignal = 0,
  conversationKey = null,
  learningSupport = null,
}: ThreadViewportProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastConversationKeyRef = useRef<string | null>(conversationKey);
  const pendingConversationScrollRef = useRef(true);
  const scrollFrameIdsRef = useRef<number[]>([]);
  const viewportRef = useRef<HTMLDivElement>(null);
  const learningPanelWidthRef = useRef(LEARNING_PANEL_DEFAULT_WIDTH);
  /** User scrolled away from the bottom; do not auto-yank until they return or we reset (new chat / send). */
  const userReadingHistoryRef = useRef(false);
  const [atBottom, setAtBottom] = useState(true);
  const [isResizingLearningPanel, setIsResizingLearningPanel] = useState(false);
  const [learningPanelWidth, setLearningPanelWidth] = useState(LEARNING_PANEL_DEFAULT_WIDTH);
  const hasMessages = messages.length > 0;
  const hasLearningSupport = !!learningSupport
    && (
      (learningSupport.prompt_support_bundle?.length ?? 0) > 0
      || (learningSupport.retrieval_hits?.length ?? 0) > 0
      || (learningSupport.retrieval_misses?.length ?? 0) > 0
    );

  const clampLearningPanelWidth = useCallback((rawWidth: number) => {
    const viewportWidth = viewportRef.current?.clientWidth ?? 0;
    const dynamicMax = viewportWidth > 0
      ? Math.min(LEARNING_PANEL_MAX_WIDTH, Math.max(LEARNING_PANEL_MIN_WIDTH, viewportWidth * 0.45))
      : LEARNING_PANEL_MAX_WIDTH;
    return Math.min(Math.max(rawWidth, LEARNING_PANEL_MIN_WIDTH), dynamicMax);
  }, []);

  const cancelScheduledBottomScroll = useCallback(() => {
    for (const id of scrollFrameIdsRef.current) {
      window.cancelAnimationFrame(id);
    }
    scrollFrameIdsRef.current = [];
  }, []);

  const scrollToBottomNow = useCallback((smooth = false) => {
    const el = scrollRef.current;
    const marker = bottomRef.current;
    const behavior: ScrollBehavior = smooth ? "smooth" : "auto";
    if (marker) {
      marker.scrollIntoView({ block: "end", behavior });
    } else if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior });
    }
    setAtBottom(true);
  }, []);

  const scrollToBottom = useCallback(
    (smooth = false, frames = 1, options?: { force?: boolean }) => {
      const force = options?.force ?? false;
      cancelScheduledBottomScroll();
      const run = () => {
        if (!force && userReadingHistoryRef.current) return;
        scrollToBottomNow(smooth);
      };
      run();
      for (let i = 1; i < frames; i += 1) {
        const id = window.requestAnimationFrame(() => {
          if (!force && userReadingHistoryRef.current) return;
          scrollToBottomNow(smooth);
        });
        scrollFrameIdsRef.current.push(id);
      }
    },
    [cancelScheduledBottomScroll, scrollToBottomNow],
  );

  useEffect(() => {
    if (!atBottom) return;
    // Instant jump: CSS scroll-smooth + behavior "auto" still animates in some
    // browsers; session switches and history hydration should never slide from top.
    scrollToBottom(false);
  }, [messages, atBottom, scrollToBottom]);

  useEffect(() => {
    if (scrollToBottomSignal <= 0) return;
    userReadingHistoryRef.current = false;
    scrollToBottom(false, 8);
  }, [scrollToBottomSignal, scrollToBottom]);

  useLayoutEffect(() => {
    if (lastConversationKeyRef.current === conversationKey) return;
    lastConversationKeyRef.current = conversationKey;
    pendingConversationScrollRef.current = true;
    userReadingHistoryRef.current = false;
    setAtBottom(true);
  }, [conversationKey]);

  useLayoutEffect(() => {
    if (!pendingConversationScrollRef.current) return;
    if (!conversationKey) {
      pendingConversationScrollRef.current = false;
      scrollToBottom(false, 4);
      return;
    }
    scrollToBottom(false, 8);
    if (!hasMessages) return;
    pendingConversationScrollRef.current = false;
  }, [conversationKey, hasMessages, messages, scrollToBottom]);

  useEffect(() => cancelScheduledBottomScroll, [cancelScheduledBottomScroll]);

  useEffect(() => {
    const target = contentRef.current;
    if (!target || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (userReadingHistoryRef.current) return;
      scrollToBottom(false, 4);
    });
    observer.observe(target);
    return () => observer.disconnect();
  }, [hasMessages, scrollToBottom]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onScroll = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      const near = distance < NEAR_BOTTOM_PX;
      setAtBottom(near);
      userReadingHistoryRef.current = !near;
    };

    onScroll();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const nextWidth = clampLearningPanelWidth(learningPanelWidthRef.current);
    learningPanelWidthRef.current = nextWidth;
    setLearningPanelWidth(nextWidth);
  }, [clampLearningPanelWidth, hasLearningSupport]);

  useEffect(() => {
    if (!hasLearningSupport || typeof window === "undefined") return;

    const handleResize = () => {
      const nextWidth = clampLearningPanelWidth(learningPanelWidthRef.current);
      learningPanelWidthRef.current = nextWidth;
      setLearningPanelWidth(nextWidth);
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [clampLearningPanelWidth, hasLearningSupport]);

  useEffect(() => {
    if (!isResizingLearningPanel || typeof window === "undefined") return;

    const handlePointerMove = (event: PointerEvent) => {
      const viewport = viewportRef.current;
      if (!viewport) return;
      const bounds = viewport.getBoundingClientRect();
      const rawWidth = bounds.right - event.clientX;
      const nextWidth = clampLearningPanelWidth(rawWidth);
      learningPanelWidthRef.current = nextWidth;
      setLearningPanelWidth(nextWidth);
    };

    const stopResizing = () => {
      setIsResizingLearningPanel(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopResizing);
    window.addEventListener("pointercancel", stopResizing);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopResizing);
      window.removeEventListener("pointercancel", stopResizing);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [clampLearningPanelWidth, isResizingLearningPanel]);

  const handleLearningPanelResizeStart = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setIsResizingLearningPanel(true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  return (
    <div ref={viewportRef} className="relative flex min-h-0 flex-1 overflow-hidden">
      <div className="relative min-w-0 flex-1 overflow-hidden">
        <div
          ref={scrollRef}
          className={cn(
            "absolute inset-0 overflow-y-auto scroll-auto scrollbar-none",
          )}
        >
          {hasMessages ? (
            <div ref={contentRef} className="mx-auto flex min-h-full w-full max-w-[64rem] flex-col">
              <div className="flex-1 px-4 pb-20 pt-4">
                <div className="mx-auto w-full max-w-[49.5rem]">
                  <ThreadMessages messages={messages} isStreaming={isStreaming} />
                </div>
              </div>

              <div className="sticky bottom-0 z-10 mt-auto bg-background">
                <div className="px-4 pb-3">
                  {composer}
                </div>
              </div>
            </div>
          ) : (
            <div ref={contentRef} className="mx-auto flex min-h-full w-full max-w-[72rem] flex-col px-4">
              <div className="flex w-full flex-1 items-center justify-center pb-[7vh] pt-8">
                <div className="flex w-full max-w-[58rem] flex-col gap-6">
                  {emptyState}
                  <div className="w-full">{composer}</div>
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} aria-hidden className="h-px" />
        </div>

        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-background to-transparent"
        />

        {!atBottom && (
          <Button
            variant="outline"
            size="icon"
            onClick={() => scrollToBottom(true, 1, { force: true })}
            className={cn(
              /* Keep clear of sticky composer (textarea + toolbar + optional goal strip). */
              "absolute bottom-48 left-1/2 z-20 h-8 w-8 -translate-x-1/2 rounded-full shadow-md",
              "bg-background/90 backdrop-blur",
              "animate-in fade-in-0 zoom-in-95",
            )}
            aria-label={t("thread.scrollToBottom")}
          >
            <ArrowDown className="h-4 w-4" />
          </Button>
        )}
      </div>

      {hasMessages && hasLearningSupport ? (
        <>
          <button
            type="button"
            aria-label="Resize preview panel"
            aria-orientation="vertical"
            aria-valuemin={LEARNING_PANEL_MIN_WIDTH}
            aria-valuemax={LEARNING_PANEL_MAX_WIDTH}
            aria-valuenow={Math.round(learningPanelWidth)}
            onPointerDown={handleLearningPanelResizeStart}
            className={cn(
              "relative hidden w-4 shrink-0 cursor-col-resize bg-transparent lg:block",
              "hover:bg-transparent focus-visible:bg-transparent focus-visible:outline-none",
              isResizingLearningPanel && "bg-transparent",
            )}
          >
            <span className="sr-only">Resize preview panel</span>
          </button>

          <aside
            className="hidden h-full shrink-0 bg-background/95 lg:flex lg:flex-col"
            style={{ width: learningPanelWidth }}
          >
            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
              <LearningSupportPanel support={learningSupport} />
            </div>
          </aside>
        </>
      ) : null}
    </div>
  );
}
