import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ThreadMessages } from "@/components/thread/ThreadMessages";
import type { UIMessage } from "@/lib/types";

describe("ThreadMessages", () => {
  it("groups consecutive reasoning and tool rows into one cluster before the answer", () => {
    const messages: UIMessage[] = [
      {
        id: "r1",
        role: "assistant",
        content: "",
        reasoning: "thinking",
        reasoningStreaming: false,
        isStreaming: true,
        createdAt: Date.now(),
      },
      {
        id: "t1",
        role: "tool",
        kind: "trace",
        content: "search()",
        traces: ["search()"],
        createdAt: Date.now(),
      },
      {
        id: "r2",
        role: "assistant",
        content: "",
        reasoning: "more thinking",
        reasoningStreaming: false,
        isStreaming: true,
        createdAt: Date.now(),
      },
      {
        id: "a1",
        role: "assistant",
        content: "final answer",
        createdAt: Date.now(),
      },
    ];

    const { container } = render(
      <ThreadMessages messages={messages} isStreaming={false} />,
    );
    const rows = Array.from(container.firstElementChild?.children ?? []);

    expect(rows).toHaveLength(2);
    expect(rows[0]).not.toHaveClass("mt-2", "mt-4", "mt-5");
    expect(rows[1]).toHaveClass("mt-4");
  });

  it("shows copy only on the last assistant slice before the next user turn", () => {
    const messages: UIMessage[] = [
      {
        id: "early",
        role: "assistant",
        content: "starting…",
        createdAt: 1,
      },
      {
        id: "t1",
        role: "tool",
        kind: "trace",
        content: "search()",
        traces: ["search()"],
        createdAt: 2,
      },
      {
        id: "late",
        role: "assistant",
        content: "final reply",
        createdAt: 3,
      },
    ];

    render(<ThreadMessages messages={messages} isStreaming={false} />);

    expect(screen.getAllByRole("button", { name: "Copy reply" })).toHaveLength(1);
    expect(screen.getByText("final reply")).toBeInTheDocument();
  });

  it("shows copy only on the second assistant when two text slices appear before user", () => {
    const messages: UIMessage[] = [
      { id: "a1", role: "assistant", content: "part one", createdAt: 1 },
      { id: "a2", role: "assistant", content: "part two", createdAt: 2 },
    ];
    render(<ThreadMessages messages={messages} isStreaming={false} />);
    expect(screen.getAllByRole("button", { name: "Copy reply" })).toHaveLength(1);
  });

  it("shows a thinking placeholder in the message area before the assistant starts responding", () => {
    const messages: UIMessage[] = [
      { id: "u1", role: "user", content: "hi", createdAt: 1 },
    ];

    render(<ThreadMessages messages={messages} isStreaming />);

    expect(screen.getByText("Thinking...")).toBeInTheDocument();
  });

  it("hides the synthetic thinking placeholder once an assistant streaming row exists", () => {
    const messages: UIMessage[] = [
      { id: "u1", role: "user", content: "hi", createdAt: 1 },
      { id: "a1", role: "assistant", content: "", isStreaming: true, createdAt: 2 },
    ];

    render(<ThreadMessages messages={messages} isStreaming />);

    expect(screen.getAllByText("Thinking...")).toHaveLength(1);
  });
});
