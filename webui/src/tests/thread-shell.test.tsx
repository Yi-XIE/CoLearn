import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThreadShell } from "@/components/thread/ThreadShell";
import { ClientProvider } from "@/providers/ClientProvider";
import type { UIMessage } from "@/lib/types";
function makeClient() {
  const errorHandlers = new Set<(err: { kind: string }) => void>();
  const chatHandlers = new Map<string, Set<(ev: import("@/lib/types").InboundEvent) => void>>();
  const sessionUpdateHandlers = new Set<(chatId: string) => void>();
  const goalStateByChatId = new Map<string, import("@/lib/types").GoalStateWsPayload>();
  return {
    status: "open" as const,
    defaultChatId: null as string | null,
    onStatus: () => () => {},
    onRuntimeModelUpdate: () => () => {},
    getRunStartedAt: () => null,
    getGoalState: (chatId: string) => goalStateByChatId.get(chatId),
    onChat: (chatId: string, handler: (ev: import("@/lib/types").InboundEvent) => void) => {
      let handlers = chatHandlers.get(chatId);
      if (!handlers) {
        handlers = new Set();
        chatHandlers.set(chatId, handlers);
      }
      handlers.add(handler);
      return () => {
        handlers?.delete(handler);
      };
    },
    onError: (handler: (err: { kind: string }) => void) => {
      errorHandlers.add(handler);
      return () => {
        errorHandlers.delete(handler);
      };
    },
    onSessionUpdate: (handler: (chatId: string) => void) => {
      sessionUpdateHandlers.add(handler);
      return () => {
        sessionUpdateHandlers.delete(handler);
      };
    },
    _emitError(err: { kind: string }) {
      for (const h of errorHandlers) h(err);
    },
    _emitChat(chatId: string, ev: import("@/lib/types").InboundEvent) {
      if (ev.event === "goal_state") {
        goalStateByChatId.set(chatId, ev.goal_state);
      }
      for (const h of chatHandlers.get(chatId) ?? []) h(ev);
    },
    _emitSessionUpdate(chatId: string) {
      for (const h of sessionUpdateHandlers) h(chatId);
    },
    sendMessage: vi.fn(),
    newChat: vi.fn(),
    attach: vi.fn(),
    connect: vi.fn(),
    close: vi.fn(),
    updateUrl: vi.fn(),
  };
}

function wrap(client: ReturnType<typeof makeClient>, children: ReactNode) {
  return (
    <ClientProvider
      client={client as unknown as import("@/lib/nanobot-client").NanobotClient}
      token="tok"
    >
      {children}
    </ClientProvider>
  );
}

function session(chatId: string) {
  return {
    key: chatId,
    channel: "" as const,
    chatId,
    createdAt: null,
    updatedAt: null,
    preview: "",
  };
}

function transcriptFromSimpleMessages(
  rows: Array<{ role: "user" | "assistant"; content: string }>,
): { schemaVersion: number; messages: UIMessage[] } {
  return {
    schemaVersion: 3,
    messages: rows.map((m, i) => ({
      id: `m-${i}`,
      role: m.role,
      content: m.content,
      createdAt: 1000 + i,
    })),
  };
}

function httpJson(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  };
}

describe("ThreadShell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({}),
      }),
    );
  });

  it("does not navigate away when clicking the chat title", async () => {
    const client = makeClient();
    const onGoHome = vi.fn();
    render(wrap(
      client,
      <ThreadShell
        session={session("chat-title")}
        title="Important conversation"
        onToggleSidebar={() => {}}
        onGoHome={onGoHome}
        onNewChat={() => {}}
      />,
    ));

    await waitFor(() => expect(screen.getByText("Important conversation")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Important conversation"));

    expect(onGoHome).not.toHaveBeenCalled();
  });

  it("restores in-memory messages when switching away and back to a session", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "persist me across tabs" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() =>
      expect(client.sendMessage).toHaveBeenCalledWith(
        "chat-a",
        "persist me across tabs",
        undefined,
      ),
    );
    expect(screen.getByText("persist me across tabs")).toBeInTheDocument();

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-b")}
            title="Chat chat-b"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-a")}
            title="Chat chat-a"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    expect(screen.getByText("persist me across tabs")).toBeInTheDocument();
  });

  it("clears the old thread when the active session is removed", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "delete me cleanly" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() =>
      expect(client.sendMessage).toHaveBeenCalledWith(
        "chat-a",
        "delete me cleanly",
        undefined,
      ),
    );
    expect(screen.getByText("delete me cleanly")).toBeInTheDocument();

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={null}
            title="nanobot"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    await waitFor(() => {
      expect(screen.queryByText("delete me cleanly")).not.toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText("先告诉我你想从哪里开始")).toBeInTheDocument();
  });

  it("creates a chat only when the blank landing sends a first message", async () => {
    const client = makeClient();
    const onNewChat = vi.fn();
    const onCreateChat = vi.fn().mockResolvedValue("chat-new");

    render(
      wrap(
        client,
        <ThreadShell
          session={null}
          title="nanobot"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
          onCreateChat={onCreateChat}
        />,
      ),
    );

    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "start for real" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(onCreateChat).toHaveBeenCalledTimes(1));
    expect(onNewChat).not.toHaveBeenCalled();
  });

  it("keeps the first landing message when new chat history is still empty", async () => {
    const client = makeClient();
    const onCreateChat = vi.fn().mockResolvedValue("chat-new");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 404,
        json: async () => ({}),
      })),
    );

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={null}
          title="nanobot"
          onToggleSidebar={() => {}}
          onCreateChat={onCreateChat}
        />,
      ),
    );

    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "first message should stay" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(onCreateChat).toHaveBeenCalledTimes(1));

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-new")}
            title="Chat chat-new"
            onToggleSidebar={() => {}}
            onCreateChat={onCreateChat}
          />,
        ),
      );
    });

    await waitFor(() =>
      expect(client.sendMessage).toHaveBeenCalledWith(
        "chat-new",
        "first message should stay",
        undefined,
      ),
    );
    await waitFor(() =>
      expect(screen.getByText("first message should stay")).toBeInTheDocument(),
    );
    expect(screen.queryByText("What can I do for you?")).not.toBeInTheDocument();
  });

  it("does not leak the previous thread when opening a brand-new chat", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-new");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/sessions/chat-a")) {
          return httpJson(
            transcriptFromSimpleMessages([
              { role: "user", content: "old question" },
              { role: "assistant", content: "old answer" },
            ]),
          );
        }
        return {
          ok: false,
          status: 404,
          json: async () => ({}),
        };
      }),
    );

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    await waitFor(() => expect(screen.getByText("old answer")).toBeInTheDocument());

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-new")}
            title="Chat chat-new"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    expect(screen.queryByText("old answer")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByPlaceholderText("先告诉我你想从哪里开始")).toBeInTheDocument(),
    );
    const input = screen.getByPlaceholderText("先告诉我你想从哪里开始");
    expect(input.className).toContain("min-h-[78px]");
    expect(screen.queryByText("old answer")).not.toBeInTheDocument();
  });

  it("does not cache optimistic messages under the next chat during a session switch", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-b");

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "only in chat a" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() =>
      expect(client.sendMessage).toHaveBeenCalledWith(
        "chat-a",
        "only in chat a",
        undefined,
      ),
    );
    expect(screen.getByText("only in chat a")).toBeInTheDocument();

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-b")}
            title="Chat chat-b"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    await waitFor(() => {
      expect(screen.queryByText("only in chat a")).not.toBeInTheDocument();
    });

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-a")}
            title="Chat chat-a"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    expect(screen.getByText("only in chat a")).toBeInTheDocument();

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-b")}
            title="Chat chat-b"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    await waitFor(() => {
      expect(screen.queryByText("only in chat a")).not.toBeInTheDocument();
    });
  });

  it("keeps live assistant replies after visiting the blank new-chat page", async () => {
    const client = makeClient();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/sessions/chat-a")) {
          return httpJson(transcriptFromSimpleMessages([{ role: "user", content: "hello" }]));
        }
        return {
          ok: false,
          status: 404,
          json: async () => ({}),
        };
      }),
    );

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onNewChat={() => {}}
        />,
      ),
    );

    await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
    await act(async () => {
      client._emitChat("chat-a", {
        event: "message",
        chat_id: "chat-a",
        text: "live assistant reply",
      });
    });
    expect(screen.getByText("live assistant reply")).toBeInTheDocument();

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={null}
            title="nanobot"
            onToggleSidebar={() => {}}
            onNewChat={() => {}}
          />,
        ),
      );
    });

    expect(screen.queryByText("live assistant reply")).not.toBeInTheDocument();
    expect(screen.getByText("What can I do for you?")).toBeInTheDocument();

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-a")}
            title="Chat chat-a"
            onToggleSidebar={() => {}}
            onNewChat={() => {}}
          />,
        ),
      );
    });

    await waitFor(() => expect(screen.getByText("live assistant reply")).toBeInTheDocument());
  });

  it("does not refetch thread history on turn_end", async () => {
    const client = makeClient();
    let historyCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/sessions/chat-a")) {
          historyCalls += 1;
          return httpJson(
            transcriptFromSimpleMessages(
              historyCalls === 1
                ? [{ role: "user", content: "question" }]
                : [
                    { role: "user", content: "question" },
                    { role: "assistant", content: "canonical markdown answer" },
                  ],
            ),
          );
        }
        return {
          ok: false,
          status: 404,
          json: async () => ({}),
        };
      }),
    );

    render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onNewChat={() => {}}
        />,
      ),
    );

    await waitFor(() => expect(screen.getByText("question")).toBeInTheDocument());
    await act(async () => {
      client._emitChat("chat-a", {
        event: "delta",
        chat_id: "chat-a",
        text: "live half-parsed | markdown",
      });
      client._emitChat("chat-a", {
        event: "turn_end",
        chat_id: "chat-a",
      });
    });

    await waitFor(() => expect(screen.getByText("live half-parsed | markdown")).toBeInTheDocument());
    expect(screen.queryByText("canonical markdown answer")).not.toBeInTheDocument();
  });

  it("scrolls to the bottom after loading a session from the blank new-chat page", async () => {
    const client = makeClient();
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = scrollIntoView;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/sessions/chat-a")) {
          return httpJson(
            transcriptFromSimpleMessages([
              { role: "user", content: "question" },
              { role: "assistant", content: "loaded answer" },
            ]),
          );
        }
        return {
          ok: false,
          status: 404,
          json: async () => ({}),
        };
      }),
    );

    try {
      const { rerender } = render(
        wrap(
          client,
          <ThreadShell
            session={null}
            title="nanobot"
            onToggleSidebar={() => {}}
            onNewChat={() => {}}
          />,
        ),
      );

      expect(screen.getByText("What can I do for you?")).toBeInTheDocument();
      scrollIntoView.mockClear();

      await act(async () => {
        rerender(
          wrap(
            client,
            <ThreadShell
              session={session("chat-a")}
              title="Chat chat-a"
              onToggleSidebar={() => {}}
              onNewChat={() => {}}
            />,
          ),
        );
      });

      await waitFor(() => expect(screen.getByText("loaded answer")).toBeInTheDocument());
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

  it("keeps the blank welcome page free of remote slash-command fetches", async () => {
    const client = makeClient();
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(
      wrap(
        client,
        <ThreadShell
          session={null}
          title="nanobot"
          onToggleSidebar={() => {}}
          onNewChat={() => {}}
        />,
      ),
    );

    await waitFor(() => expect(screen.getByText("What can I do for you?")).toBeInTheDocument());
    expect(fetchSpy).not.toHaveBeenCalledWith(
      "/api/commands",
      expect.anything(),
    );

    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "/" },
    });

    expect(screen.queryByRole("listbox", { name: "Slash commands" })).not.toBeInTheDocument();
  });

  it("surfaces a dismissible banner when the stream reports message_too_big", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");

    render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    // No banner yet: only appears once the client emits a matching error.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await act(async () => {});
    await act(async () => {
      client._emitError({ kind: "message_too_big" });
    });

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Message too large");

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("clears the stream error banner when the user switches to another chat", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    await act(async () => {});
    await act(async () => {
      client._emitError({ kind: "message_too_big" });
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    // Switch to a different chat. The banner was about the *previous* send
    // in chat-a; it must not leak into chat-b's view.
    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-b")}
            title="Chat chat-b"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("clears the previous thread immediately while the next session loads", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-b");
    let resolveChatB:
      | ((value: { ok: boolean; status: number; json: () => Promise<unknown> }) => void)
      | null = null;
    const pendingChatB = new Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>((resolve) => {
      resolveChatB = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/sessions/chat-a")) {
          return Promise.resolve(
            httpJson(
              transcriptFromSimpleMessages([{ role: "assistant", content: "from chat a" }]),
            ),
          );
        }
        if (url.includes("/api/v1/sessions/chat-b")) {
          return pendingChatB;
        }
        return Promise.resolve({
          ok: false,
          status: 404,
          json: async () => ({}),
        });
      }),
    );

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    await waitFor(() => expect(screen.getByText("from chat a")).toBeInTheDocument());

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-b")}
            title="Chat chat-b"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    expect(screen.queryByText("from chat a")).not.toBeInTheDocument();
    expect(screen.getByText("Loading conversation…")).toBeInTheDocument();

    await act(async () => {
      resolveChatB?.(
        httpJson(transcriptFromSimpleMessages([{ role: "assistant", content: "from chat b" }])),
      );
    });

    await waitFor(() => expect(screen.getByText("from chat b")).toBeInTheDocument());
    expect(screen.queryByText("from chat a")).not.toBeInTheDocument();
  });
});
