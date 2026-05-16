import test from "node:test";
import assert from "node:assert/strict";

import type { LearningProject } from "../lib/projects-api";
import type { SessionSummary } from "../lib/session-api";
import { decideLearningEntry } from "../lib/learning-session-entry-decision";

const baseProject: LearningProject = {
  project_id: "project-1",
  slug: "project-1",
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
  board_facts: {
    current_turn_mode: "EXPLORE",
    board_version: 1,
  },
  board_version: 1,
  source_refs: ["kb:file.md"],
  source_references: [],
  memory_refs: ["profile"],
  anchor: {
    topic: "Fractions",
    source_refs: ["kb:file.md"],
    prior_knowledge: "Knows basics",
    target_depth: "Explain common denominators",
    preferred_method: "feynman",
    created_at: "",
    updated_at: "",
  },
};

function buildSession(
  overrides: Partial<SessionSummary> = {},
): SessionSummary {
  return {
    id: overrides.id || "session-row-1",
    session_id: overrides.session_id || "session-1",
    title: overrides.title || "Session 1",
    project_id: "project-1",
    project_title: "Fractions",
    turn_mode: "EXPLORE",
    board_facts: {
      current_turn_mode: "EXPLORE",
      board_version: 1,
    },
    board_version: 1,
    source_refs: ["kb:file.md"],
    memory_refs: ["profile"],
    anchor: baseProject.anchor!,
    created_at: Date.now() - 1000,
    updated_at: Date.now(),
    message_count: 0,
    last_message: "",
    ...overrides,
  };
}

test("decideLearningEntry creates an anchor session when anchor is incomplete even if latest session exists", () => {
  const project: LearningProject = {
    ...baseProject,
    anchor: {
      ...baseProject.anchor!,
      prior_knowledge: "",
    },
  };
  const sessions = [buildSession({ turn_mode: "EXPLORE" })];

  const decision = decideLearningEntry(project, sessions, "Untitled");

  assert.equal(decision.kind, "create");
  if (decision.kind === "create") {
    assert.equal(decision.turnMode, "ANCHOR");
  }
});

test("decideLearningEntry resumes paused session when anchor is complete", () => {
  const sessions = [buildSession({ session_id: "paused-1", turn_mode: "PAUSED" })];

  const decision = decideLearningEntry(baseProject, sessions, "Untitled");

  assert.deepEqual(decision, {
    kind: "resume",
    sessionId: "paused-1",
  });
});

test("decideLearningEntry reuses latest active session when anchor is complete", () => {
  const latest = buildSession({ session_id: "active-1", turn_mode: "EXPLORE" });
  const decision = decideLearningEntry(baseProject, [latest], "Untitled");

  assert.equal(decision.kind, "reuse");
  if (decision.kind === "reuse") {
    assert.equal(decision.session.session_id, "active-1");
    assert.equal(decision.session.turn_mode, "EXPLORE");
  }
});
