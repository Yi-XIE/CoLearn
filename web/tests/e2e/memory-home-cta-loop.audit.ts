import { test, expect, type Page, type Route } from "@playwright/test";

const project = {
  project_id: "project-a",
  slug: "project-a",
  title: "Fractions",
  goal: "Compare values",
  status: "active",
  created_at: "2026-05-15T10:00:00Z",
  updated_at: "2026-05-15T10:00:00Z",
  last_active_at: "2026-05-15T10:00:00Z",
  source_count: 1,
  session_count: 0,
  memory_ref_count: 1,
  turn_mode: "ANCHOR",
  board_facts: { current_turn_mode: "ANCHOR", board_version: 1 },
  board_version: 1,
  source_refs: ["src-a"],
  source_references: [],
  memory_refs: ["profile"],
  anchor: {
    topic: "Fractions",
    source_refs: ["src-a"],
    prior_knowledge: "Basic arithmetic",
    target_depth: "Explain why common denominators work",
    preferred_method: "Worked examples",
    created_at: "2026-05-15T10:00:00Z",
    updated_at: "2026-05-15T10:00:00Z",
  },
};

const sessionCreated = {
  id: "session-a-1",
  session_id: "session-a-1",
  title: "Fractions learning loop",
  project_id: "project-a",
  project_title: "Fractions",
  turn_mode: "ANCHOR",
  board_facts: { current_turn_mode: "ANCHOR", board_version: 1 },
  board_version: 1,
  source_refs: ["src-a"],
  memory_refs: ["profile"],
  anchor: project.anchor,
  created_at: 1000,
  updated_at: 2000,
  message_count: 0,
  last_message: "",
  status: "idle",
};

const sessionSummary = {
  ...sessionCreated,
  turn_mode: "PAUSED",
  board_facts: { current_turn_mode: "PAUSED", board_version: 1 },
  board_version: 1,
  message_count: 4,
  last_message: "Let us continue fractions",
};

const projectionPayload = {
  profile_projection: {
    session_count: 1,
    topics_studied: ["fractions"],
    routine_revisit_prompt: "Return to denominator scaling before moving on.",
    recent_next_steps: [
      {
        project_id: "project-a",
        project_title: "Fractions",
        step: "Explain denominator scaling with one example",
        recorded_at: "2026-05-15T12:00:00Z",
      },
    ],
    confusion_history: [
      {
        project_id: "project-a",
        project_title: "Fractions",
        concept: "Denominator scaling",
        resolved: false,
        detected_at: "2026-05-15T12:00:00Z",
      },
    ],
    recent_alignments: [
      {
        project_id: "project-a",
        project_title: "Fractions",
        learner_claim: "I think denominators should match first",
        target_concept: "Equivalent fractions preserve value while matching units",
        gap: "Needs to explain why value stays constant",
        recorded_at: "2026-05-15T12:00:00Z",
      },
    ],
  },
  mastery_projection: {
    concept_mastery: {
      Fractions: {
        state: "REVIEW",
        last_review_summary: "Fraction review summary",
      },
    },
    misconceptions: ["Denominator scaling"],
  },
  recent_events: [],
};

const reviewPayload = {
  latest_review: {
    project_id: "project-a",
    project_slug: "project-a",
    project_title: "Fractions",
    session_id: "session-a-1",
    timestamp: "2026-05-15T12:00:00Z",
    review_path: "reviews/fractions.md",
    review_summary: "Fraction review summary",
    mastery_points: ["Can compare fractions"],
    confusion_points: ["Still confuses denominator scaling"],
    next_steps: ["Explain denominator scaling with one example"],
    understanding_alignment: {
      learner_claim: "I think denominators should match first",
      target_concept: "Equivalent fractions preserve value while matching units",
      gap: "Needs to explain why value stays constant",
    },
    references: ["src-a"],
  },
};

const memoryPayload = {
  summary: "## Current Focus\n- Continue comparing fractions.",
  profile: "## Identity\n- Learner in active review.",
  summary_updated_at: "2026-05-15T13:30:00Z",
  profile_updated_at: "2026-05-15T13:30:00Z",
};

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function stubHomeLoop(page: Page) {
  let sessionListMode: "empty" | "paused" = "empty";

  await page.route("**/api/v1/projects", async (route) => {
    await fulfillJson(route, { projects: [project] });
  });

  await page.route("**/api/v1/projects/project-a/latest-review", async (route) => {
    await fulfillJson(route, {
      project,
      latest_review: sessionListMode === "paused" ? reviewPayload.latest_review : null,
    });
  });

  await page.route("**/api/v1/memory", async (route) => {
    await fulfillJson(route, memoryPayload);
  });

  await page.route("**/api/v1/memory/projection", async (route) => {
    await fulfillJson(route, projectionPayload);
  });

  await page.route("**/api/v1/sessions?**", async (route) => {
    await fulfillJson(route, {
      sessions: sessionListMode === "paused" ? [sessionSummary] : [],
    });
  });

  await page.route("**/api/v1/sessions", async (route) => {
    if (route.request().method() === "POST") {
      sessionListMode = "paused";
      await fulfillJson(route, { session: sessionCreated });
      return;
    }
    await route.fallback();
  });

  await page.route("**/api/v1/sessions/session-a-1", async (route) => {
    await fulfillJson(route, sessionCreated);
  });

  await page.route("**/api/v1/sessions/session-a-1/resume", async (route) => {
    await fulfillJson(route, { session: sessionSummary });
  });

  return {
    setReviewReady() {
      sessionListMode = "paused";
    },
  };
}

test("workspace home CTA can start learning and memory reflects the loop afterwards", async ({
  page,
}) => {
  const controls = await stubHomeLoop(page);
  await page.addInitScript(() => {
    window.localStorage.setItem("colearn.activeProjectId", "project-a");
    window.localStorage.setItem("deeptutor-language", "en");
  });

  await page.goto("/");
  await expect(page.getByRole("button", { name: "Start learning" })).toBeVisible();
  await expect(page.getByText("Continue from latest next step")).toContainText(
    "Explain denominator scaling with one example",
  );

  const createRequest = page.waitForRequest("**/api/v1/sessions");
  await page.getByRole("button", { name: "Start learning" }).click();
  await createRequest;
  await expect(page).toHaveURL(/\/chat\/session-a-1$/);

  controls.setReviewReady();
  await page.getByRole("link", { name: "Memory" }).click();
  await expect(page).toHaveURL(/\/memory$/);
  await expect(page.getByTestId("memory-latest-review")).toContainText("Fraction review summary");
  await expect(page.getByTestId("memory-latest-next-step")).toContainText(
    "Explain denominator scaling with one example",
  );
  await expect(page.getByTestId("memory-continue-learning")).toHaveText("Resume paused session");
});
