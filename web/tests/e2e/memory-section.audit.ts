import { test, expect, type Page, type Route } from "@playwright/test";

const projects = [
  {
    project_id: "project-a",
    slug: "project-a",
    title: "Fractions",
    goal: "Compare values",
    status: "active",
    created_at: "2026-05-15T10:00:00Z",
    updated_at: "2026-05-15T10:00:00Z",
    last_active_at: "2026-05-15T10:00:00Z",
    source_count: 1,
    session_count: 2,
    memory_ref_count: 1,
    turn_mode: "PAUSED",
    board_facts: { current_turn_mode: "PAUSED", board_version: 1 },
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
  },
  {
    project_id: "project-b",
    slug: "project-b",
    title: "Algebra",
    goal: "Solve equations",
    status: "active",
    created_at: "2026-05-15T11:00:00Z",
    updated_at: "2026-05-15T11:00:00Z",
    last_active_at: "2026-05-15T11:00:00Z",
    source_count: 1,
    session_count: 1,
    memory_ref_count: 1,
    turn_mode: "EXPLORE",
    board_facts: { current_turn_mode: "EXPLORE", board_version: 1 },
    board_version: 1,
    source_refs: ["src-b"],
    source_references: [],
    memory_refs: ["profile"],
    anchor: {
      topic: "Algebra",
      source_refs: ["src-b"],
      prior_knowledge: "Variables",
      target_depth: "Explain balancing both sides",
      preferred_method: "Practice-first",
      created_at: "2026-05-15T11:00:00Z",
      updated_at: "2026-05-15T11:00:00Z",
    },
  },
];

const sessionsByProject: Record<string, Array<Record<string, unknown>>> = {
  "project-a": [
    {
      id: "session-a-1",
      session_id: "session-a-1",
      title: "Fractions paused session",
      project_id: "project-a",
      project_title: "Fractions",
      turn_mode: "PAUSED",
      board_facts: { current_turn_mode: "PAUSED", board_version: 1 },
      board_version: 1,
      source_refs: ["src-a"],
      memory_refs: ["profile"],
      anchor: projects[0].anchor,
      created_at: 1000,
      updated_at: 2000,
      message_count: 4,
      last_message: "Let us continue fractions",
      status: "idle",
    },
  ],
  "project-b": [
    {
      id: "session-b-1",
      session_id: "session-b-1",
      title: "Algebra active session",
      project_id: "project-b",
      project_title: "Algebra",
      turn_mode: "EXPLORE",
      board_facts: { current_turn_mode: "EXPLORE", board_version: 1 },
      board_version: 1,
      source_refs: ["src-b"],
      memory_refs: ["profile"],
      anchor: projects[1].anchor,
      created_at: 3000,
      updated_at: 4000,
      message_count: 6,
      last_message: "Keep solving equations",
      status: "idle",
    },
  ],
};

const latestReviews: Record<string, Record<string, unknown>> = {
  "project-a": {
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
  },
  "project-b": {
    latest_review: {
      project_id: "project-b",
      project_slug: "project-b",
      project_title: "Algebra",
      session_id: "session-b-1",
      timestamp: "2026-05-15T13:00:00Z",
      review_path: "reviews/algebra.md",
      review_summary: "Algebra review summary",
      mastery_points: ["Can isolate x"],
      confusion_points: ["Misses sign changes"],
      next_steps: ["Do two more balancing drills"],
      understanding_alignment: {
        learner_claim: "I move terms across the equals sign",
        target_concept: "Each operation must preserve equality on both sides",
        gap: "Needs a tighter equality-preserving explanation",
      },
      references: ["src-b"],
    },
  },
};

const projectionPayload = {
  profile_projection: {
    session_count: 7,
    topics_studied: ["fractions", "algebra"],
    routine_revisit_prompt: "Revisit the latest confusion before moving on.",
    recent_next_steps: [
      {
        project_id: "project-a",
        project_title: "Fractions",
        step: "Explain denominator scaling with one example",
        recorded_at: "2026-05-15T12:00:00Z",
      },
      {
        project_id: "project-b",
        project_title: "Algebra",
        step: "Do two more balancing drills",
        recorded_at: "2026-05-15T13:00:00Z",
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
      {
        project_id: "project-b",
        project_title: "Algebra",
        concept: "Sign changes",
        resolved: false,
        detected_at: "2026-05-15T13:00:00Z",
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
      {
        project_id: "project-b",
        project_title: "Algebra",
        learner_claim: "I move terms across the equals sign",
        target_concept: "Each operation must preserve equality on both sides",
        gap: "Needs a tighter equality-preserving explanation",
        recorded_at: "2026-05-15T13:00:00Z",
      },
    ],
  },
  mastery_projection: {
    concept_mastery: {
      Fractions: {
        state: "REVIEW",
        last_review_summary: "Fraction review summary",
      },
      Algebra: {
        state: "STABLE",
        last_review_summary: "Algebra review summary",
      },
    },
    misconceptions: ["Denominator scaling", "Sign changes"],
  },
  recent_events: [],
};

const memoryPayload = {
  summary: "## Current Focus\n- Continue comparing fractions and balancing equations.",
  profile: "## Identity\n- Learner in active practice.",
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

async function stubMemoryPage(page: Page) {
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "GET") {
      await fulfillJson(route, { projects });
      return;
    }
    await route.fallback();
  });

  await page.route("**/api/v1/memory", async (route) => {
    if (route.request().method() === "GET") {
      await fulfillJson(route, memoryPayload);
      return;
    }
    await route.fallback();
  });

  await page.route("**/api/v1/memory/projection", async (route) => {
    await fulfillJson(route, projectionPayload);
  });

  await page.route("**/api/v1/projects/*/latest-review", async (route) => {
    const url = new URL(route.request().url());
    const projectId = url.pathname.split("/").at(-2) || "";
    await fulfillJson(route, {
      project: projects.find((item) => item.project_id === projectId) || projects[0],
      latest_review: latestReviews[projectId]?.latest_review ?? null,
    });
  });

  await page.route("**/api/v1/sessions?**", async (route) => {
    const url = new URL(route.request().url());
    const projectId = url.searchParams.get("project_id") || "";
    await fulfillJson(route, {
      sessions: sessionsByProject[projectId] ?? [],
    });
  });

  await page.route("**/api/v1/sessions/session-a-1/resume", async (route) => {
    await fulfillJson(route, {
      session: {
        ...sessionsByProject["project-a"][0],
        turn_mode: "ANCHOR",
        board_facts: { current_turn_mode: "ANCHOR", board_version: 1 },
        board_version: 1,
      },
    });
  });
}

test.describe("memory section view behavior", () => {
  test.beforeEach(async ({ page }) => {
    await stubMemoryPage(page);
    await page.addInitScript(() => {
      window.localStorage.setItem("colearn.activeProjectId", "project-a");
      window.localStorage.setItem("deeptutor-language", "en");
    });
  });

  test("active memory view shows current-project cards and paused-session continue entry", async ({
    page,
  }) => {
    await page.goto("/memory");

    await expect(page.getByTestId("memory-focus-label")).toContainText("Fractions");
    await expect(page.getByTestId("memory-latest-review")).toContainText("Fraction review summary");
    await expect(page.getByTestId("memory-latest-next-step")).toContainText(
      "Explain denominator scaling with one example",
    );
    await expect(page.getByTestId("memory-continue-learning")).toHaveText("Resume paused session");

    const resumeRequest = page.waitForRequest("**/api/v1/sessions/session-a-1/resume");
    await page.getByTestId("memory-continue-learning").click();
    await resumeRequest;
    await expect(page).toHaveURL(/\/chat(?:\/session-a-1)?$/);
  });

  test("recent memory view switches cards and continue entry to the most recently learned project", async ({
    page,
  }) => {
    await page.goto("/memory");
    await page.getByTestId("memory-view-recent").click();

    await expect(page.getByTestId("memory-focus-label")).toContainText("Algebra");
    await expect(page.getByTestId("memory-latest-review")).toContainText("Algebra review summary");
    await expect(page.getByTestId("memory-latest-next-step")).toContainText(
      "Do two more balancing drills",
    );
    await expect(page.getByTestId("memory-continue-learning")).toHaveText("Continue learning");

    await page.getByTestId("memory-continue-learning").click();
    await expect(page).toHaveURL(/\/chat\/session-b-1$/);
  });

  test("global memory view keeps aggregate cards while preserving continue entry", async ({
    page,
  }) => {
    await page.goto("/memory");
    await page.getByTestId("memory-view-global").click();

    await expect(page.getByTestId("memory-focus-label")).toContainText("Global learning memory");
    await expect(page.getByText("Revisit the latest confusion before moving on.")).toBeVisible();
    await expect(page.getByText("Latest next step")).toHaveCount(0);
    await expect(page.getByTestId("memory-continue-learning")).toHaveText("Start learning");
    await expect(page.getByTestId("memory-latest-review")).toHaveCount(0);

    const resumeRequest = page.waitForRequest("**/api/v1/sessions/session-a-1/resume");
    await page.getByTestId("memory-continue-learning").click();
    await resumeRequest;
    await expect(page).toHaveURL(/\/chat(?:\/session-a-1)?$/);
  });
});
