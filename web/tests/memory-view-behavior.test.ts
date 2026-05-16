import test from "node:test";
import assert from "node:assert/strict";

import type { LearningProject } from "../lib/projects-api";
import {
  pickMemoryFocusProject,
  selectLatestNextStep,
  type AlignmentEntry,
  type ConfusionEntry,
  type NextStepEntry,
} from "../lib/memory-learning";

const projectA: LearningProject = {
  project_id: "project-a",
  slug: "project-a",
  title: "Fractions",
  goal: "Compare values",
  status: "active",
  created_at: "",
  updated_at: "",
  last_active_at: "",
  source_count: 1,
  session_count: 1,
  memory_ref_count: 1,
  turn_mode: "EXPLORE",
  board_facts: { current_turn_mode: "EXPLORE", board_version: 1 },
  board_version: 1,
  source_refs: [],
  source_references: [],
  memory_refs: ["profile"],
  anchor: null,
};

const projectB: LearningProject = {
  ...projectA,
  project_id: "project-b",
  slug: "project-b",
  title: "Algebra",
};

test("memory active view prefers current project for latest next step", () => {
  const nextSteps: NextStepEntry[] = [
    { project_id: "project-b", step: "Latest global step" },
    { project_id: "project-a", step: "Current project step" },
  ];
  const focus = pickMemoryFocusProject([projectA, projectB], "project-a", nextSteps, [], [], "active");
  assert.equal(focus.project?.project_id, "project-a");
  assert.equal(
    selectLatestNextStep(nextSteps, focus.project?.project_id || "", "fallback"),
    "Current project step",
  );
});

test("memory recent view prefers most recently learned project", () => {
  const nextSteps: NextStepEntry[] = [
    { project_id: "project-a", step: "Old step" },
    { project_id: "project-b", step: "Recent step" },
  ];
  const focus = pickMemoryFocusProject([projectA, projectB], "project-a", nextSteps, [], [], "recent");
  assert.equal(focus.project?.project_id, "project-b");
});

test("memory global view keeps cross-project aggregates visible", () => {
  const nextSteps: NextStepEntry[] = [
    { project_id: "project-a", step: "Fraction step" },
    { project_id: "project-b", step: "Algebra step" },
  ];
  const alignments: AlignmentEntry[] = [
    { project_id: "project-a", gap: "Fractions gap" },
    { project_id: "project-b", gap: "Algebra gap" },
  ];
  const confusion: ConfusionEntry[] = [
    { project_id: "project-a", concept: "Fraction confusion" },
    { project_id: "project-b", concept: "Algebra confusion" },
  ];
  const focus = pickMemoryFocusProject([projectA, projectB], "project-a", nextSteps, confusion, alignments, "global");
  assert.equal(focus.project, null);
  assert.equal(nextSteps.length, 2);
  assert.equal(alignments.length, 2);
  assert.equal(confusion.length, 2);
});
