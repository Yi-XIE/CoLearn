import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatSummary } from "@/lib/types";

const connectSpy = vi.fn();
const refreshSpy = vi.fn();
const createChatSpy = vi.fn().mockResolvedValue("chat-1");
const deleteChatSpy = vi.fn();
const toggleThemeSpy = vi.fn();
let mockSessions: ChatSummary[] = [];

vi.mock("@/hooks/useSessions", async (importOriginal) => {
  const React = await import("react");
  const actual = await importOriginal<typeof import("@/hooks/useSessions")>();
  return {
    ...actual,
    useSessions: () => {
      const [sessions, setSessions] = React.useState(mockSessions);
      return {
        sessions,
        loading: false,
        error: null,
        refresh: refreshSpy,
        createChat: createChatSpy,
        deleteChat: async (key: string) => {
          await deleteChatSpy(key);
          setSessions((prev: ChatSummary[]) => prev.filter((s) => s.key !== key));
        },
      };
    },
  };
});

vi.mock("@/hooks/useTheme", () => ({
  useTheme: () => ({
    theme: "light" as const,
    toggle: toggleThemeSpy,
  }),
}));

vi.mock("@/lib/bootstrap", () => ({
  fetchBootstrap: vi.fn().mockResolvedValue({
    token: "tok",
    ws_path: "/",
    expires_in: 300,
  }),
  deriveWsUrl: vi.fn(() => "ws://test"),
  loadSavedSecret: vi.fn(() => ""),
  saveSecret: vi.fn(),
  clearSavedSecret: vi.fn(),
}));

vi.mock("@/lib/nanobot-client", () => {
  class MockClient {
    status = "idle" as const;
    defaultChatId: string | null = null;
    connect = connectSpy;
    onStatus = () => () => {};
    onRuntimeModelUpdate = () => () => {};
    onError = () => () => {};
    onChat = () => () => {};
    sendMessage = vi.fn();
    newChat = vi.fn();
    attach = vi.fn();
    close = vi.fn();
    updateUrl = vi.fn();
  }

  return { NanobotClient: MockClient };
});

import App from "@/App";

describe("App layout", () => {
  beforeEach(() => {
    mockSessions = [];
    connectSpy.mockClear();
    refreshSpy.mockReset();
    createChatSpy.mockClear();
    deleteChatSpy.mockReset();
    toggleThemeSpy.mockReset();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
      }),
    );
  });

  it("keeps sidebar layout out of the main thread width contract", async () => {
    const { container } = render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());

    const main = container.querySelector("main");
    expect(main).toBeInTheDocument();
    expect(main).not.toHaveAttribute("style");

    const asideClassNames = Array.from(container.querySelectorAll("aside")).map(
      (el) => el.className,
    );
    expect(asideClassNames.some((cls) => cls.includes("lg:block"))).toBe(true);
  });

  it("switches to the next session when deleting the active chat", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "First chat",
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Second chat",
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });
    await waitFor(() =>
      expect(
        within(sidebar).getByRole("button", { name: /^First chat$/ }),
      ).toBeInTheDocument(),
    );

    fireEvent.pointerDown(screen.getByLabelText("Chat actions for First chat"), {
      button: 0,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));

    await waitFor(() =>
      expect(screen.getByText("Delete this chat?")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(deleteChatSpy).toHaveBeenCalledWith("websocket:chat-a"),
    );
    await waitFor(() =>
      expect(
        within(sidebar).getByRole("button", { name: /^Second chat$/ }),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("Delete this chat?")).not.toBeInTheDocument();
    expect(document.body.style.pointerEvents).not.toBe("none");
  }, 15_000);

  it("opens the settings view from the sidebar footer", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Existing chat",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/api/settings")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent: {
                model: "openai/gpt-4o",
                provider: "auto",
                resolved_provider: "openai",
                has_api_key: true,
              },
              providers: [
                {
                  name: "openai",
                  label: "OpenAI",
                  configured: true,
                  api_key_hint: "open-key",
                },
                {
                  name: "openrouter",
                  label: "OpenRouter",
                  configured: false,
                  default_api_base: "https://openrouter.ai/api/v1",
                },
              ],
              web_search: {
                provider: "brave",
                api_key_hint: "brave-key",
                base_url: null,
                providers: [
                  { name: "duckduckgo", label: "DuckDuckGo", credential: "none" },
                  { name: "brave", label: "Brave Search", credential: "api_key" },
                ],
              },
              runtime: {
                config_path: "/tmp/config.json",
              },
              requires_restart: false,
            }),
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });
    fireEvent.click(within(sidebar).getByRole("button", { name: "Settings" }));

    expect(await screen.findByText("设置")).toBeInTheDocument();
    expect(document.title).toBe("设置 - CoLearn");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.getByText("CoLearn mode")).toBeInTheDocument();
    expect(screen.getByDisplayValue("openai/gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("连接")).toBeInTheDocument();
    expect(screen.getByText("OpenRouter")).toBeInTheDocument();
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByPlaceholderText("Leave blank to keep the current key"), {
      target: { value: "unsaved-openai-key" },
    });
    fireEvent.click(screen.getByText("OpenRouter"));
    fireEvent.click(screen.getByText("OpenAI"));
    expect(screen.getByRole("button", { name: "重启运行时" })).toBeInTheDocument();
  });

  it("renders real knowledge garden data from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/knowledge/list")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              knowledge_bases: [
                {
                  id: "kb-math",
                  name: "线性代数资料库",
                  source_count: 2,
                  status: "ready",
                  provider: "lightrag",
                },
              ],
            }),
          };
        }
        if (url.includes("/api/v1/knowledge/kb-math/files")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              files: [
                { name: "notes.md", path: "/tmp/notes.md", size: 2048, modified: 1 },
              ],
            }),
          };
        }
        if (url.includes("/api/v1/knowledge/kb-math/graph")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              nodes: [
                {
                  id: "library:kb-math",
                  label: "线性代数资料库",
                  kind: "library",
                  metadata: { library_id: "kb-math" },
                },
                {
                  id: "file:kb-math:api-graph.md",
                  label: "api-graph.md",
                  kind: "file",
                  metadata: { library_id: "kb-math", path: "/tmp/api-graph.md" },
                },
                {
                  id: "concept:matrix",
                  label: "矩阵概念",
                  kind: "concept",
                  metadata: { source: "test" },
                },
              ],
              edges: [
                {
                  id: "edge:contains:library:kb-math:file:kb-math:api-graph.md",
                  source: "library:kb-math",
                  target: "file:kb-math:api-graph.md",
                  kind: "contains",
                  metadata: {},
                },
                {
                  id: "edge:mentions:file:kb-math:api-graph.md:concept:matrix",
                  source: "file:kb-math:api-graph.md",
                  target: "concept:matrix",
                  kind: "mentions",
                  metadata: {},
                },
              ],
            }),
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });
    fireEvent.click(within(sidebar).getByRole("button", { name: "知识花园" }));

    expect(await screen.findAllByText("线性代数资料库")).not.toHaveLength(0);
    expect(await screen.findByText("矩阵概念")).toBeInTheDocument();
    expect(await screen.findByText("notes.md")).toBeInTheDocument();
  });

  it("renders memory and skills pages with API-backed content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/memory/summary")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              summary: "已沉淀的长期记忆",
              profile: "",
              summary_updated_at: null,
              profile_updated_at: null,
              current_continuity: "继续验证关键结论。",
              long_term_facts: [{ label: "note.md", detail: "lightrag" }],
              blockers: [{ label: "缺少证据支持", detail: "critical" }],
              recent_events: [{ event_id: "evt-1", kind: "review_written", summary: "需要进一步核对证据", recorded_at: "" }],
            }),
          };
        }
        if (url.includes("/api/v1/skills/list")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              skills: [
                { name: "review", description: "整理学习回顾", tags: ["learning"] },
              ],
            }),
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });

    fireEvent.click(within(sidebar).getByRole("button", { name: "记忆" }));
    expect(await screen.findByText("学习摘要")).toBeInTheDocument();
    expect(screen.getByDisplayValue("已沉淀的长期记忆")).toBeInTheDocument();
    expect(screen.getByText("个人画像")).toBeInTheDocument();
    expect(screen.getByText("启用记忆")).toBeInTheDocument();

    fireEvent.click(within(sidebar).getByRole("button", { name: "技能" }));
    expect(await screen.findByText("review")).toBeInTheDocument();
    expect(await screen.findByText("整理学习回顾")).toBeInTheDocument();
  });

  it("returns from settings to the blank start page when no session was active", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "First chat",
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Second chat",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/api/settings")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent: {
                model: "openai/gpt-4o",
                provider: "openai",
                resolved_provider: "openai",
                has_api_key: true,
              },
              providers: [{ name: "openai", label: "OpenAI", configured: true }],
              web_search: {
                provider: "duckduckgo",
                api_key_hint: null,
                base_url: null,
                providers: [
                  { name: "duckduckgo", label: "DuckDuckGo", credential: "none" },
                  { name: "brave", label: "Brave Search", credential: "api_key" },
                ],
              },
              runtime: {
                config_path: "/tmp/config.json",
              },
              requires_restart: false,
            }),
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });
    fireEvent.click(within(sidebar).getByRole("button", { name: "New chat" }));
    await waitFor(() => expect(document.title).toBe("CoLearn"));

    fireEvent.click(within(sidebar).getByRole("button", { name: "Settings" }));
    expect(await screen.findByRole("heading", { name: "设置" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back to chat" }));

    await waitFor(() => expect(document.title).toBe("CoLearn"));
    expect(screen.getByText("What can I do for you?")).toBeInTheDocument();
  });

  it("filters sidebar sessions through the lightweight search row", async () => {
    mockSessions = [
      {
        key: "websocket:chat-alpha",
        channel: "websocket",
        chatId: "chat-alpha",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        title: "Q2 roadmap",
        preview: "Project planning notes",
      },
      {
        key: "websocket:chat-beta",
        channel: "websocket",
        chatId: "chat-beta",
        createdAt: "2026-04-15T10:00:00Z",
        updatedAt: "2026-04-15T10:00:00Z",
        preview: "Travel ideas",
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });
    expect(within(sidebar).getByText("Q2 roadmap")).toBeInTheDocument();
    expect(within(sidebar).getByText("Travel ideas")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "Search chats" }), {
      target: { value: "planning" },
    });

    expect(within(sidebar).getByText("Q2 roadmap")).toBeInTheDocument();
    expect(within(sidebar).queryByText("Travel ideas")).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "Search chats" }), {
      target: { value: "road q2" },
    });

    expect(within(sidebar).getByText("Q2 roadmap")).toBeInTheDocument();
    expect(within(sidebar).queryByText("Travel ideas")).not.toBeInTheDocument();
  });

  it("opens a blank start page without creating an empty chat", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Existing chat",
      },
    ];

    const matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("1024px"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    vi.stubGlobal("matchMedia", matchMedia);

    const { container } = render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Toggle theme from header" }));
    expect(toggleThemeSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    const desktopAside = container.querySelector("aside.lg\\:block") as HTMLElement;
    await waitFor(() => expect(desktopAside.style.width).toBe("0px"));

    expect(screen.queryByRole("button", { name: "Start a new chat" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Toggle sidebar" }));
    await waitFor(() => expect(desktopAside.style.width).toBe("272px"));

    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });
    fireEvent.click(within(sidebar).getByRole("button", { name: "New chat" }));
    expect(createChatSpy).not.toHaveBeenCalled();
    expect(screen.getByText("What can I do for you?")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start a new chat" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Toggle theme from header" })).toBeInTheDocument();
    expect(within(sidebar).getByRole("button", { name: "Settings" })).toBeInTheDocument();

    expect(within(sidebar).getByText("Existing chat")).toBeInTheDocument();
  });
});



