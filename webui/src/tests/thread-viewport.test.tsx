import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThreadViewport } from "@/components/thread/ThreadViewport";
import type { UIMessage } from "@/lib/types";

const messages: UIMessage[] = [
  {
    id: "u1",
    role: "user",
    content: "hello",
    createdAt: Date.now(),
  },
];

const emptyMessages: UIMessage[] = [];

describe("ThreadViewport", () => {
  it("resets to the bottom when opening a different conversation", async () => {
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    try {
      const { container, rerender } = render(
        <ThreadViewport
          messages={messages}
          isStreaming={false}
          composer={<div />}
          conversationKey="chat-a"
        />,
      );
      const scroller = container.firstElementChild?.firstElementChild as HTMLElement;
      Object.defineProperties(scroller, {
        scrollHeight: { configurable: true, value: 2400 },
        clientHeight: { configurable: true, value: 600 },
        scrollTop: { configurable: true, value: 0 },
      });
      act(() => {
        scroller.dispatchEvent(new Event("scroll"));
      });
      scrollIntoView.mockClear();

      rerender(
        <ThreadViewport
          messages={messages}
          isStreaming={false}
          composer={<div />}
          conversationKey="chat-b"
        />,
      );

      await waitFor(() =>
        expect(scrollIntoView).toHaveBeenCalledWith({
          block: "end",
          behavior: "auto",
        }),
      );
    } finally {
      HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
    }
  });

  it("waits for hydrated messages before fulfilling open-chat bottom scroll", async () => {
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    try {
      const { container, rerender } = render(
        <ThreadViewport
          messages={emptyMessages}
          isStreaming={false}
          composer={<div />}
          conversationKey={null}
        />,
      );
      const scroller = container.firstElementChild?.firstElementChild as HTMLElement;
      Object.defineProperty(scroller, "scrollHeight", {
        configurable: true,
        value: 0,
      });
      scrollIntoView.mockClear();

      rerender(
        <ThreadViewport
          messages={emptyMessages}
          isStreaming={false}
          composer={<div />}
          conversationKey="chat-a"
        />,
      );
      expect(scrollIntoView).toHaveBeenCalledWith({
        block: "end",
        behavior: "auto",
      });

      Object.defineProperty(scroller, "scrollHeight", {
        configurable: true,
        value: 2400,
      });
      scrollIntoView.mockClear();

      rerender(
        <ThreadViewport
          messages={messages}
          isStreaming={false}
          composer={<div />}
          conversationKey="chat-a"
        />,
      );

      await waitFor(() =>
        expect(scrollIntoView).toHaveBeenCalledWith({
          block: "end",
          behavior: "auto",
        }),
      );
    } finally {
      HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
    }
  });

  it("scrolls to the bottom when explicitly signalled after send", async () => {
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    try {
      const { container, rerender } = render(
        <ThreadViewport
          messages={messages}
          isStreaming={false}
          composer={<div />}
          scrollToBottomSignal={0}
        />,
      );
      const scroller = container.firstElementChild?.firstElementChild as HTMLElement;
      Object.defineProperty(scroller, "scrollHeight", {
        configurable: true,
        value: 2400,
      });
      scrollIntoView.mockClear();

      rerender(
        <ThreadViewport
          messages={messages}
          isStreaming={false}
          composer={<div />}
          scrollToBottomSignal={1}
        />,
      );

      await waitFor(() =>
        expect(scrollIntoView).toHaveBeenCalledWith({
          block: "end",
          behavior: "auto",
        }),
      );
    } finally {
      HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
    }
  });

  it("renders a draggable divider when learning support is present", () => {
    render(
      <ThreadViewport
        messages={messages}
        isStreaming={false}
        composer={<div />}
        learningSupport={{
          retrieval_active: true,
          prompt_support_bundle: [
            {
              source_ref: "notes/force.md",
              summary: "force summary",
              target_label: "Newton",
            },
          ],
          retrieval_hits: [],
          retrieval_misses: [],
          retrieval_evidence_map: {},
          retrieval_query_context: {},
          continuation_retrieval_hint: {},
        }}
      />,
    );

    expect(screen.getByRole("button", { name: "Resize preview panel" })).toBeInTheDocument();
  });

  it("updates preview panel width while dragging the divider", () => {
    const { container } = render(
      <ThreadViewport
        messages={messages}
        isStreaming={false}
        composer={<div />}
        learningSupport={{
          retrieval_active: true,
          prompt_support_bundle: [
            {
              source_ref: "notes/force.md",
              summary: "force summary",
              target_label: "Newton",
            },
          ],
          retrieval_hits: [],
          retrieval_misses: [],
          retrieval_evidence_map: {},
          retrieval_query_context: {},
          continuation_retrieval_hint: {},
        }}
      />,
    );

    const viewport = container.firstElementChild as HTMLElement;
    Object.defineProperty(viewport, "clientWidth", {
      configurable: true,
      value: 1200,
    });
    viewport.getBoundingClientRect = () => ({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 1200,
      bottom: 800,
      width: 1200,
      height: 800,
      toJSON: () => ({}),
    });

    const divider = screen.getByRole("button", { name: "Resize preview panel" });
    const aside = divider.nextElementSibling as HTMLElement;

    act(() => {
      fireEvent.pointerDown(divider, { clientX: 840 });
    });

    act(() => {
      fireEvent.pointerMove(window, { clientX: 900 });
      fireEvent.pointerUp(window, { clientX: 900 });
    });

    expect(aside.style.width).toBe("300px");
  });
});
