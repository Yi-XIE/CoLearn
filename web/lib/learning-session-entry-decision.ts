import type { LearningProject } from "./projects-api";
import type { SessionSummary } from "./session-api";
import { nextUntitledSessionTitle } from "./session-titles";

export function pickLatestProjectSession(
  sessions: SessionSummary[],
): SessionSummary | null {
  if (!sessions.length) return null;
  return [...sessions].sort((a, b) => b.updated_at - a.updated_at)[0] ?? null;
}

export type LearningEntryDecision =
  | { kind: "resume"; sessionId: string }
  | { kind: "reuse"; session: SessionSummary }
  | {
      kind: "create";
      turnMode: "ANCHOR" | "EXPLORE";
      title: string;
      projectId: string;
      projectTitle: string;
      sourceRefs: string[];
      memoryRefs: string[];
    };

export function decideLearningEntry(
  project: LearningProject,
  sessions: SessionSummary[],
  untitledLabel: string,
): LearningEntryDecision {
  const latestSession = pickLatestProjectSession(sessions);
  const anchorComplete = Boolean(
    project.anchor &&
      project.anchor.topic?.trim() &&
      project.anchor.prior_knowledge?.trim() &&
      project.anchor.target_depth?.trim() &&
      project.anchor.preferred_method?.trim(),
  );

  if (latestSession) {
    if (!anchorComplete) {
      return {
        kind: "create",
        turnMode: "ANCHOR",
        title: nextUntitledSessionTitle(
          sessions.map((session) => session.title),
          untitledLabel,
        ),
        projectId: project.project_id,
        projectTitle: project.title || "",
        sourceRefs: project.source_refs || [],
        memoryRefs: project.memory_refs || [],
      };
    }
    if (latestSession.turn_mode === "PAUSED") {
      return { kind: "resume", sessionId: latestSession.session_id };
    }
    return { kind: "reuse", session: latestSession };
  }

  return {
    kind: "create",
    turnMode: anchorComplete ? "EXPLORE" : "ANCHOR",
    title: nextUntitledSessionTitle(
      sessions.map((session) => session.title),
      untitledLabel,
    ),
    projectId: project.project_id,
    projectTitle: project.title || "",
    sourceRefs: project.source_refs || [],
    memoryRefs: project.memory_refs || [],
  };
}
