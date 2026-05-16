import test from "node:test";
import assert from "node:assert/strict";

import {
  hasCompleteLearningAnchor,
  initialLearningStateForAnchor,
} from "../lib/learning-anchor";

test("hasCompleteLearningAnchor returns true only when all contract fields are complete", () => {
  assert.equal(
    hasCompleteLearningAnchor({
      topic: "Fractions",
      source_refs: ["kb:file.md"],
      prior_knowledge: "Knows numerator and denominator",
      target_depth: "Can explain common denominators",
      preferred_method: "feynman",
    }),
    true,
  );
});

test("hasCompleteLearningAnchor rejects partial anchor payloads", () => {
  assert.equal(
    hasCompleteLearningAnchor({
      topic: "Fractions",
      source_refs: ["kb:file.md"],
      prior_knowledge: "",
      target_depth: "Can explain common denominators",
      preferred_method: "feynman",
    }),
    false,
  );
  assert.equal(
    hasCompleteLearningAnchor({
      topic: "Fractions",
      source_refs: [],
      prior_knowledge: "Knows basics",
      target_depth: "Can explain common denominators",
      preferred_method: "feynman",
    }),
    false,
  );
});

test("initialLearningStateForAnchor keeps product state idle before the anchor gate", () => {
  assert.equal(
    initialLearningStateForAnchor({
      topic: "Fractions",
      source_refs: [],
      prior_knowledge: "",
      target_depth: "",
      preferred_method: "",
    }),
    "IDLE",
  );
  assert.equal(
    initialLearningStateForAnchor({
      topic: "Fractions",
      source_refs: ["kb:file.md"],
      prior_knowledge: "Knows basics",
      target_depth: "Can explain common denominators",
      preferred_method: "feynman",
    }),
    "IDLE",
  );
});
