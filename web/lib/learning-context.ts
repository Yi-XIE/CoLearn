"use client";

import type { LearningProject } from "@/lib/projects-api";

export type MemoryReferenceFile =
  | "summary"
  | "profile"
  | "mastery"
  | "event_store";

export interface LearningProjectRef {
  projectId: string;
  title: string;
  goal?: string;
  turnMode?: string;
}

export const DEFAULT_COLEARN_PROJECT: LearningProjectRef = {
  projectId: "project-colearn-workspace",
  title: "Current CoLearn project",
};

export function projectToRef(
  project: LearningProject | null | undefined,
): LearningProjectRef {
  if (!project) return DEFAULT_COLEARN_PROJECT;
  return {
    projectId: project.project_id,
    title: project.title,
    goal: project.goal,
    turnMode: project.board_facts?.current_turn_mode || project.turn_mode,
  };
}
