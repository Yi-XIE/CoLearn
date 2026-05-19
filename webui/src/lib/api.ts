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
  return (await res.json()) as WebuiThreadPersistedPayload;
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
  return request<SettingsPayload>(`${base}/api/v1/settings`, token);
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
  const query = new URLSearchParams();
  if (update.model !== undefined) query.set("model", update.model);
  if (update.provider !== undefined) query.set("provider", update.provider);
  return request<SettingsPayload>(`${base}/api/v1/settings/update?${query}`, token);
}

export async function updateProviderSettings(
  token: string,
  update: ProviderSettingsUpdate,
  base: string = "",
): Promise<SettingsPayload> {
  const query = new URLSearchParams();
  query.set("provider", update.provider);
  if (update.apiKey !== undefined) query.set("api_key", update.apiKey);
  if (update.apiBase !== undefined) query.set("api_base", update.apiBase);
  return request<SettingsPayload>(
    `${base}/api/v1/settings/provider/update?${query}`,
    token,
  );
}

export async function updateWebSearchSettings(
  token: string,
  update: WebSearchSettingsUpdate,
  base: string = "",
): Promise<SettingsPayload> {
  const query = new URLSearchParams();
  query.set("provider", update.provider);
  if (update.apiKey !== undefined) query.set("api_key", update.apiKey);
  if (update.baseUrl !== undefined) query.set("base_url", update.baseUrl);
  return request<SettingsPayload>(
    `${base}/api/v1/settings/web-search/update?${query}`,
    token,
  );
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
