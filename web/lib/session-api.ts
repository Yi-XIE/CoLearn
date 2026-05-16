import type { LLMSelection, StreamEvent } from "@/lib/unified-ws";
import { apiUrl } from "@/lib/api";
import { invalidateClientCache, withClientCache } from "@/lib/client-cache";
import type { LearningAnchor, TurnMode } from "@/lib/projects-api";
import type { SourceReferencePayload } from "@/lib/source-references";

export interface SessionMessage {
  id: number;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  events: StreamEvent[];
  attachments: Array<{
    type: string;
    filename?: string;
    base64?: string;
    url?: string;
    mime_type?: string;
    id?: string;
    extracted_text?: string;
  }>;
  metadata?: Record<string, unknown>;
  created_at: number;
}

export interface SessionSummary {
  id: string;
  session_id: string;
  title: string;
  project_id?: string;
  project_title?: string;
  turn_mode?: TurnMode;
  board_facts?: Record<string, unknown>;
  board_version?: number;
  source_refs?: string[];
  memory_refs?: string[];
  anchor?: LearningAnchor | Record<string, unknown>;
  created_at: number;
  updated_at: number;
  message_count: number;
  last_message: string;
  has_unread_reply?: boolean;
  status?:
    | "idle"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "rejected";
  active_turn_id?: string;
  preferences?: {
    tools?: string[];
    knowledge_bases?: string[];
    language?: string;
    llm_selection?: LLMSelection | null;
    source_references?: SourceReferencePayload[];
  };
}

export interface ActiveTurnSummary {
  id: string;
  turn_id: string;
  session_id: string;
  status: "running" | "completed" | "failed" | "cancelled" | "rejected";
  error: string;
  created_at: number;
  updated_at: number;
  finished_at?: number | null;
  last_seq: number;
}

export interface SessionDetail {
  id: string;
  session_id: string;
  title: string;
  project_id?: string;
  project_title?: string;
  turn_mode?: TurnMode;
  board_facts?: Record<string, unknown>;
  board_version?: number;
  source_refs?: string[];
  memory_refs?: string[];
  anchor?: LearningAnchor | Record<string, unknown>;
  created_at: number;
  updated_at: number;
  status?:
    | "idle"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "rejected";
  active_turn_id?: string;
  compressed_summary?: string;
  summary_up_to_msg_id?: number;
  preferences?: {
    tools?: string[];
    knowledge_bases?: string[];
    language?: string;
    llm_selection?: LLMSelection | null;
    source_references?: SourceReferencePayload[];
  };
  messages: SessionMessage[];
  active_turns?: ActiveTurnSummary[];
}

export interface SessionCreatePayload {
  title?: string;
  project_id: string;
  project_title?: string;
  turn_mode?: TurnMode;
  source_refs?: string[];
  memory_refs?: string[];
}

async function expectJson<T>(response: Response): Promise<T> {
  if (response.status === 401 && typeof window !== "undefined") {
    const next = encodeURIComponent(window.location.pathname);
    window.location.href = `/login?next=${next}`;
    return new Promise(() => {});
  }
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listSessions(
  limit = 50,
  offset = 0,
  options?: { force?: boolean; projectId?: string },
): Promise<SessionSummary[]> {
  return withClientCache<SessionSummary[]>(
    `sessions:${limit}:${offset}:${options?.projectId || ""}`,
    async () => {
      const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
      });
      if (options?.projectId) params.set("project_id", options.projectId);
      const response = await fetch(apiUrl(`/api/v1/sessions?${params.toString()}`), {
        cache: "no-store",
        credentials: "include",
      });
      const data = await expectJson<{ sessions: SessionSummary[] }>(response);
      return data.sessions ?? [];
    },
    {
      force: options?.force,
      ttlMs: 15_000,
    },
  );
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(apiUrl(`/api/v1/sessions/${sessionId}`), {
    cache: "no-store",
    credentials: "include",
  });
  return expectJson<SessionDetail>(response);
}

export async function createSession(
  payload: SessionCreatePayload,
): Promise<SessionDetail> {
  const response = await fetch(apiUrl("/api/v1/sessions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  const data = await expectJson<{ session: SessionDetail }>(response);
  invalidateClientCache("sessions:");
  return data.session;
}

export async function updateSessionTitle(
  sessionId: string,
  title: string,
): Promise<SessionDetail> {
  const response = await fetch(apiUrl(`/api/v1/sessions/${sessionId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ title }),
  });
  const data = await expectJson<{ session: SessionDetail }>(response);
  invalidateClientCache("sessions:");
  return data.session;
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/sessions/${sessionId}`), {
    method: "DELETE",
    credentials: "include",
  });
  await expectJson<{ deleted: boolean }>(response);
  invalidateClientCache("sessions:");
}

export async function pauseSession(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(apiUrl(`/api/v1/sessions/${sessionId}/pause`), {
    method: "POST",
    credentials: "include",
  });
  const data = await expectJson<{ session: SessionDetail }>(response);
  invalidateClientCache("sessions:");
  return data.session;
}

export async function resumeSession(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(apiUrl(`/api/v1/sessions/${sessionId}/resume`), {
    method: "POST",
    credentials: "include",
  });
  const data = await expectJson<{ session: SessionDetail }>(response);
  invalidateClientCache("sessions:");
  return data.session;
}
