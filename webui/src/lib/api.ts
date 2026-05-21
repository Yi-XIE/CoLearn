import type {
  ChatSummary,
  KnowledgeBaseSummary,
  KnowledgeFileSummary,
  KnowledgeGraphPayload,
  KnowledgeTaskResult,
  LearningSupportPayload,
  MemoryDocPayload,
  MemoryDocumentName,
  MemoryRefreshPayload,
  MemorySummaryPayload,
  ProviderSettingsUpdate,
  SettingsPayload,
  SettingsUpdate,
  SlashCommand,
  SkillSummary,
  WebSearchSettingsUpdate,
  WebuiThreadPersistedPayload,
} from "./types";

type RawCatalogProfileModel = {
  id?: string;
  name?: string;
  model?: string;
};

type RawCatalogProfile = {
  id?: string;
  name?: string;
  binding?: string | null;
  provider?: string | null;
  base_url?: string | null;
  api_key?: string | null;
  models?: RawCatalogProfileModel[];
};

type RawCatalogService = {
  active_profile_id?: string;
  active_model_id?: string;
  profiles?: RawCatalogProfile[];
};

type RawSettingsState = {
  ui?: {
    theme?: string;
    language?: string;
  };
  catalog?: {
    version?: number;
    services?: {
      llm?: RawCatalogService;
      embedding?: RawCatalogService;
      search?: RawCatalogService;
    };
  };
  providers?: {
    llm?: Array<{ value?: string; label?: string; base_url?: string }>;
    search?: Array<{ value?: string; label?: string }>;
  };
};

type RawSettingsCatalog = NonNullable<RawSettingsState["catalog"]>;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(
  url: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(url, {
    ...(init ?? {}),
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw new ApiError(res.status, `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

function splitKey(key: string): { channel: string; chatId: string } {
  const idx = key.indexOf(":");
  if (idx === -1) return { channel: "", chatId: key };
  return { channel: key.slice(0, idx), chatId: key.slice(idx + 1) };
}

function maskApiKey(value: string | null | undefined): string | null {
  const text = String(value ?? "").trim();
  if (!text) return null;
  if (text.length <= 4) return text;
  return `****${text.slice(-4)}`;
}

function pickActiveProfile(service: RawCatalogService | undefined): RawCatalogProfile | null {
  const profiles = service?.profiles ?? [];
  if (profiles.length === 0) return null;
  return (
    profiles.find((profile) => String(profile.id ?? "") === String(service?.active_profile_id ?? ""))
    ?? profiles[0]
    ?? null
  );
}

function pickActiveModel(service: RawCatalogService | undefined, profile: RawCatalogProfile | null): RawCatalogProfileModel | null {
  const models = profile?.models ?? [];
  if (models.length === 0) return null;
  return (
    models.find((model) => String(model.id ?? "") === String(service?.active_model_id ?? ""))
    ?? models[0]
    ?? null
  );
}

function normalizeSettingsPayload(raw: RawSettingsState): SettingsPayload {
  const services = raw.catalog?.services ?? {};
  const llmService = services.llm;
  const activeProfile = pickActiveProfile(llmService);
  const activeModel = pickActiveModel(llmService, activeProfile);
  const searchService = services.search;
  const activeSearchProfile = pickActiveProfile(searchService);
  const providerRows = (llmService?.profiles ?? []).map((profile) => {
    const name =
      String(profile.binding ?? profile.provider ?? profile.id ?? "")
        .trim()
        .toLowerCase()
      || "custom";
    return {
      name,
      label: String(profile.name ?? (name || "Provider")),
      configured: !!String(profile.api_key ?? "").trim(),
      api_key_hint: maskApiKey(profile.api_key),
      api_base: String(profile.base_url ?? "").trim() || null,
      default_api_base: String(profile.base_url ?? "").trim() || null,
    };
  });
  const providerMap = new Map<string, SettingsPayload["providers"][number]>();
  for (const provider of providerRows) {
    if (!providerMap.has(provider.name)) {
      providerMap.set(provider.name, provider);
      continue;
    }
    const current = providerMap.get(provider.name)!;
    providerMap.set(provider.name, {
      ...current,
      configured: current.configured || provider.configured,
      api_key_hint: current.api_key_hint ?? provider.api_key_hint,
      api_base: current.api_base ?? provider.api_base,
      default_api_base: current.default_api_base ?? provider.default_api_base,
    });
  }
  return {
    agent: {
      model: String(activeModel?.model ?? activeModel?.name ?? ""),
      provider: String(activeProfile?.binding ?? activeProfile?.provider ?? ""),
      resolved_provider: String(activeProfile?.binding ?? activeProfile?.provider ?? "") || null,
      has_api_key: !!String(activeProfile?.api_key ?? "").trim(),
    },
    providers: Array.from(providerMap.values()),
    web_search: {
      provider: String(activeSearchProfile?.provider ?? ""),
      api_key_hint: maskApiKey(activeSearchProfile?.api_key),
      base_url: String(activeSearchProfile?.base_url ?? "").trim() || null,
      providers: (raw.providers?.search ?? []).map((provider) => ({
        name: String(provider.value ?? ""),
        label: String(provider.label ?? provider.value ?? ""),
        credential: "api_key" as const,
      })),
    },
    runtime: {
      config_path: "",
    },
    requires_restart: false,
  };
}

async function fetchRawSettingsState(
  token: string,
  base: string = "",
): Promise<RawSettingsState> {
  return request<RawSettingsState>(`${base}/api/v1/settings`, token);
}

async function fetchSettingsCatalogState(
  token: string,
  base: string = "",
): Promise<RawSettingsCatalog> {
  const body = await request<{ catalog?: RawSettingsCatalog }>(
    `${base}/api/v1/settings/catalog`,
    token,
  );
  return body.catalog ?? {};
}

async function applySettingsCatalogState(
  token: string,
  catalog: RawSettingsCatalog,
  base: string = "",
): Promise<SettingsPayload> {
  await request<{ catalog: RawSettingsCatalog }>(`${base}/api/v1/settings/catalog`, token, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ catalog }),
  });
  await request<{ applied: boolean }>(`${base}/api/v1/settings/apply`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ catalog }),
  });
  return normalizeSettingsPayload(await fetchRawSettingsState(token, base));
}

function normalizeTimestamp(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const asNumber = Number(value);
    if (Number.isFinite(asNumber)) return asNumber;
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return Date.now();
}

export async function listSessions(
  token: string,
  base: string = "",
): Promise<ChatSummary[]> {
  type Row = {
    id?: string;
    session_id?: string;
    created_at?: string | null;
    updated_at?: string | null;
    title?: string;
    last_message?: string;
  };
  const body = await request<{ sessions: Row[] }>(
    `${base}/api/v1/sessions`,
    token,
  );
  return body.sessions.map((s) => ({
    key: s.session_id ?? s.id ?? "",
    ...splitKey(s.session_id ?? s.id ?? ""),
    createdAt: s.created_at ?? null,
    updatedAt: s.updated_at ?? null,
    title: s.title ?? "",
    preview: s.last_message ?? "",
  }));
}

/** Disk-backed WebUI display thread snapshot (separate from agent session). */
export async function fetchWebuiThread(
  token: string,
  key: string,
  base: string = "",
): Promise<WebuiThreadPersistedPayload | null> {
  const url = `${base}/api/v1/sessions/${encodeURIComponent(splitKey(key).chatId || key)}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
    credentials: "same-origin",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
  const body = (await res.json()) as {
    session?: {
      session_id?: string;
      messages?: Array<{
        id?: string | number;
        role?: "user" | "assistant" | "tool" | "system";
        content?: string;
        created_at?: string | number | null;
      }>;
    };
    session_id?: string;
    messages?: Array<{
      id?: string | number;
      role?: "user" | "assistant" | "tool" | "system";
      content?: string;
      created_at?: string | number | null;
    }>;
  };
  const session = body.session ?? body;
  const messages = (session.messages ?? []).map((message, index) => ({
    id: String(message.id ?? `hist-${index}`),
    role: message.role ?? "assistant",
    content: String(message.content ?? ""),
    createdAt: normalizeTimestamp(message.created_at),
  }));
  return {
    schemaVersion: 3,
    sessionKey: String(session.session_id ?? (splitKey(key).chatId || key)),
    messages,
  };
}

export async function fetchLearningSupport(
  token: string,
  sessionId: string,
  base: string = "",
): Promise<LearningSupportPayload | null> {
  const res = await fetch(`${base}/api/v1/sessions/${encodeURIComponent(sessionId)}`, {
    headers: { Authorization: `Bearer ${token}` },
    credentials: "same-origin",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
  const body = (await res.json()) as { session?: { last_turn_result?: unknown }; last_turn_result?: unknown };
  const session = body.session ?? body;
  const lastTurn = (session.last_turn_result ?? {}) as Record<string, unknown>;
  const runtime = (lastTurn.runtime_v2 ?? {}) as Record<string, unknown>;
  const retrieval = ((runtime.retrieval as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
  const promptSupport =
    (retrieval.prompt_support_bundle as LearningSupportPayload["prompt_support_bundle"] | undefined)
    ?? (lastTurn.prompt_support_bundle as LearningSupportPayload["prompt_support_bundle"] | undefined)
    ?? [];
  const misses =
    (retrieval.retrieval_misses as LearningSupportPayload["retrieval_misses"] | undefined)
    ?? (lastTurn.retrieval_misses as LearningSupportPayload["retrieval_misses"] | undefined)
    ?? [];
  const hits =
    (retrieval.retrieval_hits as LearningSupportPayload["retrieval_hits"] | undefined)
    ?? (lastTurn.retrieval_hits as LearningSupportPayload["retrieval_hits"] | undefined)
    ?? [];
  if (promptSupport.length === 0 && hits.length === 0 && misses.length === 0) return null;
  return {
    prompt_support_bundle: promptSupport,
    retrieval_hits: hits,
    retrieval_misses: misses,
    retrieval_evidence_map:
      (retrieval.retrieval_evidence_map as LearningSupportPayload["retrieval_evidence_map"] | undefined)
      ?? (lastTurn.retrieval_evidence_map as LearningSupportPayload["retrieval_evidence_map"] | undefined)
      ?? {},
    retrieval_query_context:
      (retrieval.retrieval_query_context as LearningSupportPayload["retrieval_query_context"] | undefined)
      ?? (lastTurn.retrieval_query_context as LearningSupportPayload["retrieval_query_context"] | undefined)
      ?? {},
    continuation_retrieval_hint:
      (retrieval.continuation_retrieval_hint as LearningSupportPayload["continuation_retrieval_hint"] | undefined)
      ?? (lastTurn.continuation_retrieval_hint as LearningSupportPayload["continuation_retrieval_hint"] | undefined)
      ?? {},
  };
}

export async function deleteSession(
  token: string,
  key: string,
  base: string = "",
): Promise<boolean> {
  const body = await request<{ deleted: boolean }>(
    `${base}/api/v1/sessions/${encodeURIComponent(splitKey(key).chatId || key)}`,
    token,
    { method: "DELETE" },
  );
  return body.deleted;
}

export interface BoardHistoryEvent {
  event_id: string;
  kind: string;
  payload: Record<string, unknown>;
}

export async function fetchBoardHistory(
  token: string,
  sessionId: string,
  base: string = "",
): Promise<BoardHistoryEvent[]> {
  const res = await fetch(`${base}/api/v1/sessions/${encodeURIComponent(sessionId)}/board_history`, {
    headers: { Authorization: `Bearer ${token}` },
    credentials: "same-origin",
  });
  if (res.status === 404) return [];
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
  const body = (await res.json()) as { history?: BoardHistoryEvent[] };
  return body.history ?? [];
}

export async function fetchSettings(
  token: string,
  base: string = "",
): Promise<SettingsPayload> {
  return normalizeSettingsPayload(await fetchRawSettingsState(token, base));
}

export async function listSlashCommands(
  token: string,
  base: string = "",
): Promise<SlashCommand[]> {
  void token;
  void base;
  return [];
}

export async function updateSettings(
  token: string,
  update: SettingsUpdate,
  base: string = "",
): Promise<SettingsPayload> {
  const catalog = await fetchSettingsCatalogState(token, base);
  const services = catalog.services ?? {};
  const llm = services.llm;
  if (!llm) {
    return normalizeSettingsPayload(await fetchRawSettingsState(token, base));
  }
  const profiles = llm.profiles ?? [];
  const activeProfile = pickActiveProfile(llm);
  const targetProfile = update.provider
    ? profiles.find((profile) =>
        String(profile.binding ?? profile.provider ?? "")
          .trim()
          .toLowerCase() === update.provider?.trim().toLowerCase())
      ?? activeProfile
      : activeProfile;
  if (targetProfile?.id) llm.active_profile_id = String(targetProfile.id);
  const models = targetProfile?.models ?? [];
  if (models.length > 0) {
    let targetModel = models.find((model) =>
      [model.id, model.name, model.model]
        .map((value) => String(value ?? "").trim())
        .includes(String(update.model ?? "").trim()))
      ?? pickActiveModel(llm, targetProfile);
    if (!targetModel) targetModel = models[0];
    if (update.model !== undefined && targetModel) {
      targetModel.model = update.model;
      targetModel.name = update.model;
    }
    if (targetModel?.id) llm.active_model_id = String(targetModel.id);
  }
  return applySettingsCatalogState(token, catalog, base);
}

export async function updateProviderSettings(
  token: string,
  update: ProviderSettingsUpdate,
  base: string = "",
): Promise<SettingsPayload> {
  const catalog = await fetchSettingsCatalogState(token, base);
  const services = catalog.services ?? {};
  for (const serviceName of ["llm", "embedding"] as const) {
    const service = services[serviceName];
    for (const profile of service?.profiles ?? []) {
      const binding = String(profile.binding ?? profile.provider ?? "").trim().toLowerCase();
      if (binding !== update.provider.trim().toLowerCase()) continue;
      if (update.apiKey !== undefined) profile.api_key = update.apiKey;
      if (update.apiBase !== undefined) profile.base_url = update.apiBase;
    }
  }
  return applySettingsCatalogState(token, catalog, base);
}

export async function updateWebSearchSettings(
  token: string,
  update: WebSearchSettingsUpdate,
  base: string = "",
): Promise<SettingsPayload> {
  const catalog = await fetchSettingsCatalogState(token, base);
  const search = catalog.services?.search;
  if (!search) {
    return normalizeSettingsPayload(await fetchRawSettingsState(token, base));
  }
  const activeProfile = pickActiveProfile(search);
  if (activeProfile) {
    activeProfile.provider = update.provider;
    if (update.apiKey !== undefined) activeProfile.api_key = update.apiKey;
    if (update.baseUrl !== undefined) activeProfile.base_url = update.baseUrl;
    if (activeProfile.id) search.active_profile_id = String(activeProfile.id);
  }
  return applySettingsCatalogState(token, catalog, base);
}

export async function listKnowledgeBases(
  token: string,
  base: string = "",
): Promise<KnowledgeBaseSummary[]> {
  const body = await request<{ knowledge_bases: KnowledgeBaseSummary[] }>(
    `${base}/api/v1/knowledge/list`,
    token,
  );
  return body.knowledge_bases;
}

export async function listKnowledgeFiles(
  token: string,
  name: string,
  base: string = "",
): Promise<KnowledgeFileSummary[]> {
  const body = await request<{ files: KnowledgeFileSummary[] }>(
    `${base}/api/v1/knowledge/${encodeURIComponent(name)}/files`,
    token,
  );
  return body.files;
}

export async function fetchKnowledgeGraph(
  token: string,
  id: string,
  base: string = "",
): Promise<KnowledgeGraphPayload> {
  return request<KnowledgeGraphPayload>(
    `${base}/api/v1/knowledge/${encodeURIComponent(id)}/graph`,
    token,
  );
}

export async function createKnowledgeBase(
  token: string,
  params: { name: string; files: File[]; ragProvider?: string },
  base: string = "",
): Promise<KnowledgeTaskResult> {
  const form = new FormData();
  form.append("name", params.name);
  form.append("rag_provider", params.ragProvider ?? "lightrag");
  for (const file of params.files) form.append("files", file);
  return request<KnowledgeTaskResult>(
    `${base}/api/v1/knowledge/create`,
    token,
    { method: "POST", body: form },
  );
}

export async function uploadKnowledgeFiles(
  token: string,
  params: { name: string; files: File[]; ragProvider?: string },
  base: string = "",
): Promise<KnowledgeTaskResult> {
  const form = new FormData();
  form.append("rag_provider", params.ragProvider ?? "lightrag");
  for (const file of params.files) form.append("files", file);
  return request<KnowledgeTaskResult>(
    `${base}/api/v1/knowledge/${encodeURIComponent(params.name)}/upload`,
    token,
    { method: "POST", body: form },
  );
}

export async function reindexKnowledgeBase(
  token: string,
  name: string,
  base: string = "",
): Promise<KnowledgeTaskResult> {
  return request<KnowledgeTaskResult>(
    `${base}/api/v1/knowledge/${encodeURIComponent(name)}/reindex`,
    token,
    { method: "POST" },
  );
}

export async function fetchMemorySummary(
  token: string,
  base: string = "",
): Promise<MemorySummaryPayload> {
  return request<MemorySummaryPayload>(`${base}/api/v1/memory/summary`, token);
}

export async function updateMemoryDocument(
  token: string,
  file: MemoryDocumentName,
  content: string,
  base: string = "",
): Promise<MemoryDocPayload> {
  return request<MemoryDocPayload>(`${base}/api/v1/memory`, token, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file, content }),
  });
}

export async function refreshMemoryDocument(
  token: string,
  base: string = "",
): Promise<MemoryRefreshPayload> {
  return request<MemoryRefreshPayload>(`${base}/api/v1/memory/refresh`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
}

export async function clearMemoryDocument(
  token: string,
  file: MemoryDocumentName,
  base: string = "",
): Promise<MemoryDocPayload> {
  return request<MemoryDocPayload>(`${base}/api/v1/memory/clear`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file }),
  });
}

export async function listSkills(
  token: string,
  base: string = "",
): Promise<SkillSummary[]> {
  const body = await request<{ skills: SkillSummary[] }>(
    `${base}/api/v1/skills/list`,
    token,
  );
  return body.skills;
}
