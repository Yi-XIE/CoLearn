"use client";

import { apiUrl } from "@/lib/api";
import { invalidateClientCache, withClientCache } from "@/lib/client-cache";
import {
  hasCompleteLearningAnchor,
  initialLearningStateForAnchor,
} from "@/lib/learning-anchor";
import type { SourceReferencePayload } from "@/lib/source-references";

const PROJECTS_CACHE_PREFIX = "projects:";

export type LearningState =
  | "IDLE"
  | "EXPLAINING"
  | "QA"
  | "PRACTICE"
  | "REVIEW"
  | "PAUSED";

export type TurnMode =
  | "ANCHOR"
  | "CORRECTION"
  | "VERIFY"
  | "EXPLORE"
  | "PAUSED";

export interface LearningAnchor {
  topic: string;
  source_refs: string[];
  prior_knowledge: string;
  target_depth: string;
  preferred_method: string;
  created_at: string;
  updated_at: string;
}

export interface LearningProject {
  project_id: string;
  slug: string;
  title: string;
  goal: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
  last_active_at: string;
  source_count: number;
  session_count: number;
  memory_ref_count: number;
  turn_mode: TurnMode;
  board_facts?: {
    current_turn_mode?: TurnMode;
    board_version?: number;
    continuation?: {
      next_prompt_hint?: string;
      last_completed_turn_id?: string;
    };
  };
  board_version?: number;
  source_refs: string[];
  source_references?: SourceReferencePayload[];
  memory_refs: string[];
  anchor?: LearningAnchor | null;
}

export interface LatestProjectReview {
  project_id: string;
  project_slug: string;
  project_title: string;
  session_id: string;
  timestamp: string;
  review_path: string;
  review_summary: string;
  mastery_points: string[];
  confusion_points: string[];
  next_steps: string[];
  understanding_alignment: {
    learner_claim: string;
    target_concept: string;
    gap: string;
  };
  references: string[];
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

export async function listProjects(options?: { force?: boolean }) {
  return withClientCache<LearningProject[]>(
    `${PROJECTS_CACHE_PREFIX}list`,
    async () => {
      const response = await fetch(apiUrl("/api/v1/projects"), {
        cache: "no-store",
        credentials: "include",
      });
      const data = await expectJson<{ projects: LearningProject[] }>(response);
      return data.projects ?? [];
    },
    { force: options?.force, ttlMs: 15_000 },
  );
}

export async function createProject(payload: {
  title: string;
  goal?: string;
  slug?: string;
}) {
  const response = await fetch(apiUrl("/api/v1/projects"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  const data = await expectJson<{ project: LearningProject }>(response);
  invalidateClientCache(PROJECTS_CACHE_PREFIX);
  return data.project;
}

export async function getProject(projectId: string) {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}`), {
    cache: "no-store",
    credentials: "include",
  });
  const data = await expectJson<{ project: LearningProject }>(response);
  return data.project;
}

export async function updateProject(
  projectId: string,
  payload: {
    title?: string;
    goal?: string;
    status?: "active" | "archived";
    source_refs?: string[];
  },
) {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  const data = await expectJson<{ project: LearningProject }>(response);
  invalidateClientCache(PROJECTS_CACHE_PREFIX);
  return data.project;
}

export async function saveProjectSources(
  projectId: string,
  sourceRefs: string[],
  sourceReferences: SourceReferencePayload[] = [],
) {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}/sources`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      source_refs: sourceRefs,
      source_references: sourceReferences,
    }),
  });
  const data = await expectJson<{
    project: LearningProject;
    source_refs: string[];
    source_references: SourceReferencePayload[];
  }>(response);
  invalidateClientCache(PROJECTS_CACHE_PREFIX);
  return data;
}

export async function saveProjectAnchor(
  projectId: string,
  payload: {
    topic: string;
    source_refs?: string[];
    prior_knowledge?: string;
    target_depth?: string;
    preferred_method?: string;
  },
) {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}/anchor`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  const data = await expectJson<{
    project: LearningProject;
    anchor: LearningAnchor | null;
  }>(response);
  invalidateClientCache(PROJECTS_CACHE_PREFIX);
  return data;
}

export async function getLatestProjectReview(projectId: string) {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}/latest-review`), {
    cache: "no-store",
    credentials: "include",
  });
  const data = await expectJson<{
    project: LearningProject;
    latest_review: LatestProjectReview | null;
  }>(response);
  return data;
}

export { hasCompleteLearningAnchor, initialLearningStateForAnchor };
