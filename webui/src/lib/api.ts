import type {
  ChatSummary,
  KnowledgeBaseSummary,
  KnowledgeFileSummary,
  KnowledgeTaskResult,
  LearningSupportPayload,
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
    key: string;
    created_at: string | null;
    updated_at: string | null;
    title?: string;
    preview?: string;
  };
  const body = await request<{ sessions: Row[] }>(
    `${base}/api/sessions`,
    token,
  );
  return body.sessions.map((s) => ({
    key: s.key,
    ...splitKey(s.key),
    createdAt: s.created_at,
    updatedAt: s.updated_at,
    title: s.title ?? "",
    preview: s.preview ?? "",
  }));
}

/** Disk-backed WebUI display thread snapshot (separate from agent session). */
export async function fetchWebuiThread(
  token: string,
  key: string,
  base: string = "",
): Promise<WebuiThreadPersistedPayload | null> {
  const url = `${base}/api/sessions/${encodeURIComponent(key)}/webui-thread`;
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
    `${base}/api/sessions/${encodeURIComponent(key)}/delete`,
    token,
  );
  return body.deleted;
}

export async function fetchSettings(
  token: string,
  base: string = "",
): Promise<SettingsPayload> {
  return request<SettingsPayload>(`${base}/api/settings`, token);
}

export async function listSlashCommands(
  token: string,
  base: string = "",
): Promise<SlashCommand[]> {
  type Row = {
    command: string;
    title: string;
    description: string;
    icon: string;
    arg_hint?: string;
  };
  const body = await request<{ commands: Row[] }>(`${base}/api/commands`, token);
  return body.commands
    .filter((command) => !["/stop", "/restart"].includes(command.command))
    .map((command) => ({
      command: command.command,
      title: command.title,
      description: command.description,
      icon: command.icon,
      argHint: command.arg_hint ?? "",
    }));
}

export async function updateSettings(
  token: string,
  update: SettingsUpdate,
  base: string = "",
): Promise<SettingsPayload> {
  const query = new URLSearchParams();
  if (update.model !== undefined) query.set("model", update.model);
  if (update.provider !== undefined) query.set("provider", update.provider);
  return request<SettingsPayload>(`${base}/api/settings/update?${query}`, token);
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
    `${base}/api/settings/provider/update?${query}`,
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
    `${base}/api/settings/web-search/update?${query}`,
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
