import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteSession,
  fetchLearningSupport,
  fetchSettings,
  fetchWebuiThread,
  listSessions,
  listSlashCommands,
  updateMemorySettings,
  updateSessionTitle,
  updateProviderSettings,
  updateSettings,
  updateWebSearchSettings,
} from "@/lib/api";
import { deriveTitle } from "@/lib/format";

describe("webui API helpers", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ deleted: true, key: "chat-1", messages: [] }),
      }),
    );
  });

  it("percent-encodes websocket keys when fetching webui-thread snapshot", async () => {
    await fetchWebuiThread("tok", "websocket:chat-1");

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/sessions/chat-1",
      expect.objectContaining({
        headers: { Authorization: "Bearer tok" },
        credentials: "same-origin",
      }),
    );
  });

  it("percent-encodes websocket keys when deleting a session", async () => {
    await deleteSession("tok", "websocket:chat-1");

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/sessions/chat-1",
      expect.objectContaining({
        headers: { Authorization: "Bearer tok" },
      }),
    );
  });

  it("percent-encodes websocket keys when renaming a session", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session: {
          session_id: "chat-1",
          created_at: "2026-05-01T10:00:00Z",
          updated_at: "2026-05-01T10:02:00Z",
          title: "Renamed chat",
          last_message: "first user message",
        },
      }),
    } as Response);

    await expect(updateSessionTitle("tok", "websocket:chat-1", "Renamed chat")).resolves.toMatchObject({
      key: "chat-1",
      chatId: "chat-1",
      title: "Renamed chat",
      preview: "first user message",
    });

    expect(fetch).toHaveBeenLastCalledWith(
      "/api/v1/sessions/chat-1",
      expect.objectContaining({
        method: "PATCH",
        headers: expect.objectContaining({
          Authorization: "Bearer tok",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({ title: "Renamed chat" }),
      }),
    );
  });

  it("normalizes learning support from CoLearn session detail", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session: {
          last_turn_result: {
            runtime_v2: {
                retrieval: {
                  retrieval_active: true,
                  prompt_support_bundle: [
                    {
                      source_ref: "note.md",
                      chunk_id: "c1",
                      support_type: "definition",
                    summary: "Core idea",
                  },
                ],
                retrieval_misses: [],
              },
            },
          },
        },
      }),
    } as Response);

    const support = await fetchLearningSupport("tok", "session-1");

    expect(fetch).toHaveBeenLastCalledWith(
      "/api/v1/sessions/session-1",
      expect.objectContaining({
        headers: { Authorization: "Bearer tok" },
        credentials: "same-origin",
      }),
    );
    expect(support?.prompt_support_bundle[0]?.summary).toBe("Core idea");
  });

  it("returns null when retrieval metadata only exists in deprecated top-level fields", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session: {
          last_turn_result: {
            prompt_support_bundle: [
              {
                source_ref: "legacy.md",
                summary: "legacy support",
              },
            ],
          },
        },
      }),
    } as Response);

    await expect(fetchLearningSupport("tok", "session-legacy")).resolves.toBeNull();
  });

  it("updates settings through the catalog apply flow", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          catalog: {
            services: {
              llm: {
                active_profile_id: "openrouter",
                active_model_id: "model-1",
                profiles: [
                  {
                    id: "openrouter",
                    binding: "openrouter",
                    provider: "openrouter",
                    models: [{ id: "model-1", name: "old-model", model: "old-model" }],
                  },
                ],
              },
            },
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ catalog: { services: {} } }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ applied: true }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          catalog: {
            services: {
              llm: {
                active_profile_id: "openrouter",
                active_model_id: "model-1",
                profiles: [
                  {
                    id: "openrouter",
                    binding: "openrouter",
                    provider: "openrouter",
                    api_key: "sk-test",
                    models: [{ id: "model-1", name: "openrouter/test", model: "openrouter/test" }],
                  },
                ],
              },
            },
          },
          providers: { search: [] },
          memory: { enabled: true },
          runtime: { config_path: "D:/Colearn-nightly/.colearn/nanobot-v0.2-slim.config.json" },
        }),
      } as Response);

    await updateSettings("tok", {
      model: "openrouter/test",
      provider: "openrouter",
    });

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/v1/settings/catalog",
      expect.objectContaining({
        headers: { Authorization: "Bearer tok" },
        credentials: "same-origin",
      }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/v1/settings/catalog",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({
          Authorization: "Bearer tok",
          "Content-Type": "application/json",
        }),
      }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "/api/v1/settings/apply",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer tok",
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("updates provider settings through catalog persistence", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          catalog: {
            services: {
              llm: {
                profiles: [
                  { id: "openrouter", binding: "openrouter", provider: "openrouter" },
                ],
              },
              embedding: {
                profiles: [
                  { id: "openrouter-embed", binding: "openrouter", provider: "openrouter" },
                ],
              },
            },
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ catalog: { services: {} } }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ applied: true }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          catalog: {
            services: {
              llm: {
                profiles: [
                  {
                    id: "openrouter",
                    binding: "openrouter",
                    provider: "openrouter",
                    api_key: "sk-or-test",
                    base_url: "https://openrouter.ai/api/v1",
                  },
                ],
              },
            },
          },
          providers: { search: [] },
          memory: { enabled: true },
          runtime: { config_path: "D:/Colearn-nightly/.colearn/nanobot-v0.2-slim.config.json" },
        }),
      } as Response);

    await updateProviderSettings("tok", {
      provider: "openrouter",
      apiKey: "sk-or-test",
      apiBase: "https://openrouter.ai/api/v1",
    });

    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/v1/settings/catalog",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({
          Authorization: "Bearer tok",
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("updates web search settings through catalog persistence", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          catalog: {
            services: {
              search: {
                active_profile_id: "search-1",
                profiles: [{ id: "search-1", provider: "duckduckgo" }],
              },
            },
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ catalog: { services: {} } }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ applied: true }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          catalog: {
            services: {
              search: {
                active_profile_id: "search-1",
                profiles: [
                  {
                    id: "search-1",
                    provider: "searxng",
                    base_url: "https://search.example.com",
                  },
                ],
              },
            },
          },
          providers: {
            search: [{ value: "searxng", label: "SearXNG", credential: "base_url" }],
          },
          memory: { enabled: false },
          runtime: { config_path: "D:/Colearn-nightly/.colearn/nanobot-v0.2-slim.config.json" },
        }),
      } as Response);

    await updateWebSearchSettings("tok", {
      provider: "searxng",
      baseUrl: "https://search.example.com",
    });

    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/v1/settings/catalog",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({
          Authorization: "Bearer tok",
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("normalizes memory settings from the settings payload", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        catalog: { services: {} },
        providers: { search: [] },
        memory: { enabled: false },
        runtime: { config_path: "D:/Colearn-nightly/.colearn/nanobot-v0.2-slim.config.json" },
      }),
    } as Response);

    await expect(fetchSettings("tok")).resolves.toMatchObject({
      memory: { enabled: false },
    });
  });

  it("updates memory settings through the dedicated endpoint", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ memory: { enabled: false } }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          catalog: { services: {} },
          providers: { search: [] },
          memory: { enabled: false },
          runtime: { config_path: "D:/Colearn-nightly/.colearn/nanobot-v0.2-slim.config.json" },
        }),
      } as Response);

    await expect(updateMemorySettings("tok", { enabled: false })).resolves.toMatchObject({
      memory: { enabled: false },
    });

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/v1/settings/memory",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({
          Authorization: "Bearer tok",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({ enabled: false }),
      }),
    );
  });

  it("maps generated session titles from the sessions list", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        sessions: [
          {
            session_id: "websocket:chat-1",
            created_at: "2026-05-01T10:00:00",
            updated_at: "2026-05-01T10:01:00",
            title: "Generated title",
          },
        ],
      }),
    } as Response);

    await expect(listSessions("tok")).resolves.toMatchObject([
      {
        key: "websocket:chat-1",
        channel: "websocket",
        chatId: "chat-1",
        title: "Generated title",
        preview: "",
      },
    ]);
  });

  it("normalizes numeric Unix timestamps from the sessions list to ISO strings", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        sessions: [
          {
            session_id: "chat-1",
            created_at: 1779453251,
            updated_at: "1779453568",
            title: "CoLearn",
          },
        ],
      }),
    } as Response);

    await expect(listSessions("tok")).resolves.toEqual([
      expect.objectContaining({
        key: "chat-1",
        createdAt: "2026-05-22T12:34:11.000Z",
        updatedAt: "2026-05-22T12:39:28.000Z",
      }),
    ]);
  });

  it("truncates long default chat titles to a single compact line", () => {
    const title = deriveTitle(
      "This is a very long first user sentence that should become the default title and be truncated neatly for the sidebar",
      "New chat",
    );

    expect(title).toHaveLength(60);
    expect(title.startsWith("This is a very long first user sentence")).toBe(true);
    expect(title.endsWith("...")).toBe(true);
  });

  it("keeps slash commands empty when the backend does not expose them", async () => {
    await expect(listSlashCommands("tok")).resolves.toEqual([]);
    expect(fetch).not.toHaveBeenCalled();
  });
});
