import type { LearningProject, LatestProjectReview } from "./projects-api";
import type { SessionSummary } from "./session-api";

export interface AlignmentEntry {
  project_id?: string;
  project_title?: string;
  learner_claim?: string;
  target_concept?: string;
  gap?: string;
  recorded_at?: string;
}

export interface ConfusionEntry {
  project_id?: string;
  project_title?: string;
  concept?: string;
  detected_at?: string;
  resolved?: boolean;
}

export interface NextStepEntry {
  project_id?: string;
  project_title?: string;
  step?: string;
  recorded_at?: string;
}

export interface MemoryFocusProject {
  project: LearningProject | null;
  reason: "active" | "recent" | "fallback" | "none";
}

export type MemoryViewMode = "active" | "recent" | "global";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function asAlignmentEntries(value: unknown): AlignmentEntry[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asRecord(item))
    .map((item) => ({
      project_id: asString(item.project_id),
      project_title: asString(item.project_title),
      learner_claim: asString(item.learner_claim),
      target_concept: asString(item.target_concept),
      gap: asString(item.gap),
      recorded_at: asString(item.recorded_at),
    }))
    .filter((item) => item.learner_claim || item.target_concept || item.gap);
}

export function asConfusionEntries(value: unknown): ConfusionEntry[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asRecord(item))
    .map((item) => ({
      project_id: asString(item.project_id),
      project_title: asString(item.project_title),
      concept: asString(item.concept),
      detected_at: asString(item.detected_at),
      resolved: Boolean(item.resolved),
    }))
    .filter((item) => item.concept);
}

export function asNextStepEntries(value: unknown): NextStepEntry[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asRecord(item))
    .map((item) => ({
      project_id: asString(item.project_id),
      project_title: asString(item.project_title),
      step: asString(item.step),
      recorded_at: asString(item.recorded_at),
    }))
    .filter((item) => item.step);
}

export function pickMemoryFocusProject(
  projects: LearningProject[],
  activeProjectId: string | null | undefined,
  recentNextSteps: NextStepEntry[],
  confusionHistory: ConfusionEntry[],
  recentAlignments: AlignmentEntry[],
  mode: MemoryViewMode = "active",
): MemoryFocusProject {
  if (!projects.length) {
    return { project: null, reason: "none" };
  }
  if (mode === "global") {
    return { project: null, reason: "none" };
  }
  if (activeProjectId) {
    const activeProject =
      projects.find((item) => item.project_id === activeProjectId) ?? null;
    if (activeProject && mode === "active") {
      return { project: activeProject, reason: "active" };
    }
  }

  const candidateProjectIds = [
    ...recentNextSteps.map((item) => item.project_id || ""),
    ...confusionHistory.map((item) => item.project_id || ""),
    ...recentAlignments.map((item) => item.project_id || ""),
  ].filter(Boolean);
  for (let index = candidateProjectIds.length - 1; index >= 0; index -= 1) {
    const project = projects.find(
      (item) => item.project_id === candidateProjectIds[index],
    );
    if (project) {
      return { project, reason: "recent" };
    }
  }

  return { project: projects[0] ?? null, reason: "fallback" };
}

export function filterEntriesForProject<T extends { project_id?: string }>(
  entries: T[],
  projectId: string,
  limit: number,
): T[] {
  const filtered = entries.filter((item) => item.project_id === projectId);
  return filtered.slice(-limit).reverse();
}

export function selectLatestNextStep(
  nextSteps: NextStepEntry[],
  projectId: string,
  fallbackPrompt: string,
): string {
  const projectStep = [...nextSteps]
    .reverse()
    .find((item) => item.project_id === projectId && item.step);
  if (projectStep?.step) return projectStep.step;
  const latestStep = [...nextSteps].reverse().find((item) => item.step);
  return latestStep?.step || fallbackPrompt;
}

export function selectLatestReviewLike(
  latestReview: LatestProjectReview | null,
  latestAlignment: AlignmentEntry | null,
  latestConfusion: ConfusionEntry | null,
  fallbackLabel: string,
): string {
  if (latestReview?.review_summary) return latestReview.review_summary;
  if (latestAlignment?.gap) return latestAlignment.gap;
  if (latestConfusion?.concept) return latestConfusion.concept;
  return fallbackLabel;
}

export function pickLatestProjectSession(
  sessions: SessionSummary[],
): SessionSummary | null {
  if (!sessions.length) return null;
  return [...sessions].sort((a, b) => b.updated_at - a.updated_at)[0] ?? null;
}

export function focusBadgeLabel(
  reason: MemoryFocusProject["reason"],
): "recent" | "fallback" | "" {
  if (reason === "recent") return "recent";
  if (reason === "fallback") return "fallback";
  return "";
}
