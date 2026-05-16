import test from "node:test";
import assert from "node:assert/strict";

import type { LearningProject } from "../lib/projects-api";
import {
  focusBadgeLabel,
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

test("pickMemoryFocusProject prefers active project when present", () => {
  const focus = pickMemoryFocusProject([projectA, projectB], "project-b", [], [], []);
  assert.equal(focus.project?.project_id, "project-b");
  assert.equal(focus.reason, "active");
});

test("pickMemoryFocusProject falls back to most recently learned project", () => {
  const nextSteps: NextStepEntry[] = [
    { project_id: "project-a", step: "Old" },
    { project_id: "project-b", step: "Latest" },
  ];
  const alignments: AlignmentEntry[] = [];
  const confusion: ConfusionEntry[] = [];
  const focus = pickMemoryFocusProject([projectA, projectB], "", nextSteps, confusion, alignments);
  assert.equal(focus.project?.project_id, "project-b");
  assert.equal(focus.reason, "recent");
});

test("pickMemoryFocusProject supports global mode without selecting a project", () => {
  const focus = pickMemoryFocusProject([projectA, projectB], "project-a", [], [], [], "global");
  assert.equal(focus.project, null);
  assert.equal(focus.reason, "none");
});

test("selectLatestNextStep prefers project-specific step before global fallback", () => {
  const nextSteps: NextStepEntry[] = [
    { project_id: "project-a", step: "Restate the fraction rule." },
    { project_id: "project-b", step: "Solve one more algebra equation." },
  ];
  assert.equal(
    selectLatestNextStep(nextSteps, "project-a", "fallback"),
    "Restate the fraction rule.",
  );
  assert.equal(
    selectLatestNextStep(nextSteps, "project-x", "fallback"),
    "Solve one more algebra equation.",
  );
});

test("focusBadgeLabel only exposes visible badge reasons", () => {
  assert.equal(focusBadgeLabel("recent"), "recent");
  assert.equal(focusBadgeLabel("fallback"), "fallback");
  assert.equal(focusBadgeLabel("active"), "");
});
