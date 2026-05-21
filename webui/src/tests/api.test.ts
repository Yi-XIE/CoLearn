import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteSession,
  fetchLearningSupport,
  fetchWebuiThread,
  listSessions,
  listSlashCommands,
  updateProviderSettings,
  updateSettings,
  updateWebSearchSettings,
} from "@/lib/api";

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

  it("normalizes learning support from CoLearn session detail", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session: {
          last_turn_result: {
            runtime_v2: {
              retrieval: {
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
          providers: { search: [] },
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

  it("keeps slash commands empty when the backend does not expose them", async () => {
    await expect(listSlashCommands("tok")).resolves.toEqual([]);
    expect(fetch).not.toHaveBeenCalled();
  });
});
