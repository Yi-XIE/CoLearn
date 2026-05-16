import type { LearningProject } from "./projects-api";
import {
  createSession,
  listSessions,
  resumeSession,
  type SessionDetail,
  type SessionSummary,
} from "./session-api";
export {
  decideLearningEntry,
  pickLatestProjectSession,
  type LearningEntryDecision,
} from "./learning-session-entry-decision";
import { decideLearningEntry } from "./learning-session-entry-decision";

export async function openLearningEntry(
  project: LearningProject,
  {
    untitledLabel,
  }: {
    untitledLabel: string;
  },
): Promise<SessionSummary | SessionDetail> {
  const existingSessions = await listSessions(100, 0, {
    force: true,
    projectId: project.project_id,
  });
  const decision = decideLearningEntry(project, existingSessions, untitledLabel);
  if (decision.kind === "reuse") {
    return decision.session;
  }
  if (decision.kind === "resume") {
    return resumeSession(decision.sessionId);
  }
  return createSession({
    title: decision.title,
    project_id: decision.projectId,
    project_title: decision.projectTitle,
    turn_mode: decision.turnMode,
    source_refs: decision.sourceRefs,
    memory_refs: decision.memoryRefs,
  });
}
