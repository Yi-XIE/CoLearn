"use client";

import { ArrowRight, BookOpen, Brain, ChevronRight, RefreshCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { useAppShell } from "@/context/AppShellContext";
import {
  createProject,
  getLatestProjectReview,
  initialLearningStateForAnchor,
  listProjects,
  type LatestProjectReview,
  type LearningProject,
} from "@/lib/projects-api";
import {
  createSession,
  listSessions,
  resumeSession,
  type SessionSummary,
} from "@/lib/session-api";
import { apiFetch, apiUrl } from "@/lib/api";
import { openLearningEntry, pickLatestProjectSession } from "@/lib/learning-session-entry";

interface MemoryProjectionPayload {
  profile_projection?: Record<string, unknown>;
}

interface NextStepEntry {
  project_id?: string;
  project_title?: string;
  step?: string;
  recorded_at?: string;
}

function formatSessionTime(value: string, emptyLabel: string) {
  if (!value) return emptyLabel;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asNextStepEntries(value: unknown): NextStepEntry[] {
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

function SummaryList({
  title,
  items,
  emptyLabel,
}: {
  title: string;
  items: string[];
  emptyLabel: string;
}) {
  return (
    <section className="rounded-lg border border-[var(--border)]/60 bg-[var(--background)]/55 p-4">
      <div className="mb-2 text-sm font-medium text-[var(--foreground)]">{title}</div>
      {items.length ? (
        <ul className="space-y-2 text-sm text-[var(--muted-foreground)]">
          {items.slice(0, 3).map((item) => (
            <li key={item} className="flex gap-2 leading-6">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--foreground)]/55" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-sm text-[var(--muted-foreground)]">{emptyLabel}</div>
      )}
    </section>
  );
}

export default function HomePage() {
  const router = useRouter();
  const { t } = useTranslation();
  const { activeProjectId, setActiveProjectId, setActiveSessionId } = useAppShell();
  const activeProjectIdRef = useRef(activeProjectId);
  const [projects, setProjects] = useState<LearningProject[]>([]);
  const [latestReview, setLatestReview] = useState<LatestProjectReview | null>(null);
  const [latestSession, setLatestSession] = useState<SessionSummary | null>(null);
  const [latestNextStep, setLatestNextStep] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const activeProject = useMemo(() => {
    if (!projects.length) return null;
    return (
      projects.find((item) => item.project_id === activeProjectId) ??
      projects[0]
    );
  }, [activeProjectId, projects]);

  useEffect(() => {
    activeProjectIdRef.current = activeProjectId;
  }, [activeProjectId]);

  const loadHome = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let items = await listProjects({ force: true });
      if (!items.length) {
        const created = await createProject({
          title: t("Current CoLearn project"),
          goal: t(
            "Build understanding with CoLearn through explanation, practice, and review.",
          ),
        });
        items = [created];
      }
      setProjects(items);
      const currentProjectId = activeProjectIdRef.current;
      const selected =
        items.find((item) => item.project_id === currentProjectId) ?? items[0];
      if (selected.project_id !== currentProjectId) {
        setActiveProjectId(selected.project_id);
      }
      const sessions = await listSessions(20, 0, {
        force: true,
        projectId: selected.project_id,
      });
      setLatestSession(pickLatestProjectSession(sessions));
      const memoryProjectionRes = await apiFetch(apiUrl("/api/v1/memory/projection"));
      const memoryProjection =
        (await memoryProjectionRes.json().catch(() => null)) as MemoryProjectionPayload | null;
      const nextSteps = asNextStepEntries(
        asRecord(memoryProjection?.profile_projection).recent_next_steps,
      );
      const matchingNextStep =
        [...nextSteps]
          .reverse()
          .find((item) => item.project_id === selected.project_id && item.step) ??
        [...nextSteps].reverse().find((item) => item.step);
      setLatestNextStep(matchingNextStep?.step || "");
      const payload = await getLatestProjectReview(selected.project_id);
      setLatestReview(payload.latest_review);
    } catch (loadError) {
      console.error("Failed to load CoLearn home", loadError);
      setError(t("Failed to load the latest CoLearn review."));
    } finally {
      setLoading(false);
    }
  }, [setActiveProjectId, t]);

  useEffect(() => {
    void loadHome();
  }, [loadHome]);

  const startLearning = useCallback(async () => {
    if (!activeProject) return;
    setStarting(true);
    try {
      const session = await openLearningEntry(activeProject, {
        untitledLabel: t("Untitled"),
      });
      setActiveSessionId(session.session_id);
      router.push(`/chat/${session.session_id}`);
    } catch (sessionError) {
      console.error("Failed to start learning session", sessionError);
      setError(t("Failed to open the learning session."));
    } finally {
      setStarting(false);
    }
  }, [activeProject, router, setActiveSessionId, t]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div className="text-sm text-[var(--muted-foreground)]">
          {t("Loading your latest CoLearn review...")}
        </div>
      </div>
    );
  }

  if (!activeProject) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div className="text-sm text-[var(--muted-foreground)]">
          {t("No CoLearn project available.")}
        </div>
      </div>
    );
  }

  const hasReview = Boolean(latestReview);
  const hasSession = Boolean(latestSession);
  const latestSessionTime = latestSession
    ? formatSessionTime(String(latestSession.updated_at || ""), t("No session yet"))
    : t("No session yet");
  const resumeLabel =
    latestSession?.turn_mode === "PAUSED"
      ? t("Resume paused session")
      : hasSession
        ? t("Continue learning")
        : t("Start learning");

  return (
    <div className="h-full overflow-y-auto bg-[var(--background)]">
      <div className="mx-auto flex min-h-full w-full max-w-6xl flex-col px-6 py-8 lg:px-8">
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <div className="mb-2 text-sm text-[var(--muted-foreground)]">
              {t("CoLearn workspace")}
            </div>
            <h1 className="text-3xl font-semibold tracking-normal text-[var(--foreground)]">
              {activeProject.title}
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">
              {activeProject.goal ||
                t(
                  "Continue learning with CoLearn through explanation, practice, and review.",
                )}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadHome()}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--secondary)]"
          >
            <RefreshCcw size={15} />
            <span>{t("Refresh")}</span>
          </button>
        </div>

        <section className="mb-6 rounded-xl border border-[var(--border)]/70 bg-[var(--secondary)]/55 p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border)]/60 bg-[var(--background)]/70 px-3 py-1 text-xs text-[var(--muted-foreground)]">
                <Brain size={14} />
                <span>
                  {latestSession?.turn_mode === "PAUSED"
                    ? t("Paused CoLearn session ready to resume")
                    : hasSession
                      ? t("Recent CoLearn session ready to continue")
                      : t("Ready for your first CoLearn session")}
                </span>
              </div>
              <div>
                <div className="text-sm text-[var(--muted-foreground)]">
                  {hasSession
                    ? t("Last session activity: {{time}}", {
                        time: latestSessionTime,
                      })
                    : t("No previous CoLearn session found.")}
                </div>
                <div className="mt-2 text-lg font-medium text-[var(--foreground)]">
                  {latestSession?.turn_mode === "PAUSED"
                    ? t("Resume the paused learning loop from the last active state.")
                    : hasSession
                      ? t("Pick up from the latest learning state and continue the next loop.")
                      : t(
                          "Start your first CoLearn project and let CoLearn capture the first explanation, practice, and review.",
                        )}
                </div>
                {latestNextStep ? (
                  <div className="mt-3 rounded-lg border border-[var(--border)]/60 bg-[var(--background)]/60 px-3 py-2 text-sm text-[var(--muted-foreground)]">
                    {t("Continue from latest next step")}: {latestNextStep}
                  </div>
                ) : null}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void startLearning()}
              disabled={starting}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-[var(--foreground)] px-4 text-sm font-medium text-[var(--background)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span>{resumeLabel}</span>
              <ArrowRight size={15} />
            </button>
          </div>
        </section>

        {error ? (
          <div className="mb-6 rounded-lg border border-rose-500/25 bg-rose-500/8 px-4 py-3 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <section className="mb-6 rounded-xl border border-[var(--border)]/70 bg-[var(--secondary)]/35 p-6">
          <div className="mb-3 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
            <Brain size={15} />
            <span>{t("Current learning loop")}</span>
          </div>
          <p className="max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">
            {t(
              "This branch is currently assembled around the reduced CoLearn core: session flow, learner memory, and explanation-practice-review output. The knowledge layer is intentionally waiting for LightRAG.",
            )}
          </p>
        </section>

        {hasReview ? (
          <>
            <div className="mb-4 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
              <BookOpen size={15} />
              <span>{t("Latest CoLearn review")}</span>
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <SummaryList
                title={t("Mastery points")}
                items={latestReview?.mastery_points || []}
                emptyLabel={t("No highlights recorded yet.")}
              />
              <SummaryList
                title={t("Confusion points")}
                items={latestReview?.confusion_points || []}
                emptyLabel={t("No highlights recorded yet.")}
              />
              <SummaryList
                title={t("Next steps")}
                items={latestReview?.next_steps || []}
                emptyLabel={t("No highlights recorded yet.")}
              />
            </div>

            <section className="mt-6 rounded-xl border border-[var(--border)]/70 bg-[var(--secondary)]/45 p-6">
              <div className="mb-3 text-sm font-medium text-[var(--foreground)]">
                {t("Understanding alignment")}
              </div>
              <div className="grid gap-3 lg:grid-cols-3">
                <div className="rounded-lg border border-[var(--border)]/60 bg-[var(--background)]/55 p-4">
                  <div className="mb-2 text-xs uppercase tracking-[0.08em] text-[var(--muted-foreground)]">
                    {t("Learner claim")}
                  </div>
                  <div className="text-sm leading-6 text-[var(--foreground)]">
                    {latestReview?.understanding_alignment?.learner_claim ||
                      t("Not captured.")}
                  </div>
                </div>
                <div className="rounded-lg border border-[var(--border)]/60 bg-[var(--background)]/55 p-4">
                  <div className="mb-2 text-xs uppercase tracking-[0.08em] text-[var(--muted-foreground)]">
                    {t("Target concept")}
                  </div>
                  <div className="text-sm leading-6 text-[var(--foreground)]">
                    {latestReview?.understanding_alignment?.target_concept ||
                      t("Not captured.")}
                  </div>
                </div>
                <div className="rounded-lg border border-[var(--border)]/60 bg-[var(--background)]/55 p-4">
                  <div className="mb-2 text-xs uppercase tracking-[0.08em] text-[var(--muted-foreground)]">
                    {t("Main gap")}
                  </div>
                  <div className="text-sm leading-6 text-[var(--foreground)]">
                    {latestReview?.understanding_alignment?.gap ||
                      t("Not captured.")}
                  </div>
                </div>
              </div>
              {latestReview?.references?.length ? (
                <div className="mt-5 border-t border-[var(--border)]/50 pt-4">
                  <div className="mb-2 text-sm font-medium text-[var(--foreground)]">
                    {t("References")}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {latestReview.references.slice(0, 6).map((reference) => (
                      <span
                        key={reference}
                        className="inline-flex items-center gap-1 rounded-full border border-[var(--border)]/60 bg-[var(--background)]/60 px-3 py-1 text-xs text-[var(--muted-foreground)]"
                      >
                        <ChevronRight size={12} />
                        <span>{reference}</span>
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>
          </>
        ) : (
          <section className="rounded-xl border border-dashed border-[var(--border)]/70 bg-[var(--secondary)]/30 p-8">
            <div className="max-w-2xl">
              <div className="mb-2 text-lg font-medium text-[var(--foreground)]">
                {t("Start your first CoLearn project")}
              </div>
              <p className="text-sm leading-6 text-[var(--muted-foreground)]">
                {t(
                  "Once the first session is complete, CoLearn will place the latest mastery points, confusion points, and next steps here by default.",
                )}
              </p>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
