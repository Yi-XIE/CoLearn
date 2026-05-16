"use client";

import { useEffect, useState } from "react";
import { Check, FolderOpen, Loader2, Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import Modal from "@/components/common/Modal";
import type { LearningProject } from "@/lib/projects-api";

interface ProjectPickerModalProps {
  open: boolean;
  projects: LearningProject[];
  activeProjectId: string | null;
  loading?: boolean;
  onClose: () => void;
  onSelectProject: (projectId: string) => void | Promise<void>;
  onCreateProject: (payload: { title: string; goal: string }) => Promise<void>;
}

export default function ProjectPickerModal({
  open,
  projects,
  activeProjectId,
  loading = false,
  onClose,
  onSelectProject,
  onCreateProject,
}: ProjectPickerModalProps) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle("");
    setGoal("");
    setSubmitting(false);
  }, [open]);

  const handleCreate = async () => {
    const nextTitle = title.trim();
    if (!nextTitle) return;
    setSubmitting(true);
    try {
      await onCreateProject({
        title: nextTitle,
        goal: goal.trim(),
      });
      setTitle("");
      setGoal("");
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={open}
      onClose={onClose}
      title={t("Learning Projects")}
      titleIcon={<FolderOpen className="h-4 w-4" />}
      width="lg"
    >
      <div className="space-y-5 p-5">
        <section className="space-y-3">
          <div>
            <h3 className="text-[13px] font-semibold text-[var(--foreground)]">
              {t("Switch Project")}
            </h3>
            <p className="mt-1 text-[12px] text-[var(--muted-foreground)]">
              {t("Every learning session belongs to one CoLearn project.")}
            </p>
          </div>
          <div className="max-h-[320px] overflow-y-auto rounded-xl border border-[var(--border)]">
            {loading ? (
              <div className="flex min-h-[180px] items-center justify-center">
                <Loader2 className="h-5 w-5 animate-spin text-[var(--muted-foreground)]" />
              </div>
            ) : projects.length === 0 ? (
              <div className="flex min-h-[120px] items-center justify-center px-4 text-center text-[12px] text-[var(--muted-foreground)]">
                {t("No CoLearn projects yet. Create one below.")}
              </div>
            ) : (
              <div className="divide-y divide-[var(--border)]">
                {projects.map((project) => {
                  const active = project.project_id === activeProjectId;
                  return (
                    <button
                      key={project.project_id}
                      type="button"
                      onClick={() => {
                        void onSelectProject(project.project_id);
                        onClose();
                      }}
                      className={`flex w-full items-start gap-3 px-4 py-3 text-left transition-colors ${
                        active
                          ? "bg-[var(--primary)]/8"
                          : "hover:bg-[var(--muted)]/40"
                      }`}
                    >
                      <div
                        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${
                          active
                            ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)]"
                            : "border-[var(--border)] text-transparent"
                        }`}
                      >
                        <Check size={12} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-[13px] font-medium text-[var(--foreground)]">
                            {project.title}
                          </span>
                          <span className="shrink-0 rounded-full border border-[var(--border)] px-1.5 py-px text-[10px] text-[var(--muted-foreground)]">
                            {project.board_facts?.current_turn_mode || project.turn_mode}
                          </span>
                        </div>
                        {project.goal ? (
                          <p className="mt-1 line-clamp-2 text-[12px] text-[var(--muted-foreground)]">
                            {project.goal}
                          </p>
                        ) : null}
                        <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-[var(--muted-foreground)]">
                          <span>{t("Sessions")}: {project.session_count}</span>
                          <span>{t("Sources")}: {project.source_count}</span>
                          <span>{t("Memory")}: {project.memory_ref_count}</span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        <section className="space-y-3 rounded-xl border border-[var(--border)] bg-[var(--background)]/40 p-4">
          <div>
            <h3 className="text-[13px] font-semibold text-[var(--foreground)]">
              {t("Create Project")}
            </h3>
            <p className="mt-1 text-[12px] text-[var(--muted-foreground)]">
              {t("Give this CoLearn project a topic and a short goal.")}
            </p>
          </div>
          <div className="space-y-3">
            <label className="block">
              <span className="mb-1 block text-[12px] text-[var(--muted-foreground)]">
                {t("Title")}
              </span>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={t("Decision trees")}
                className="h-[38px] w-full rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 text-[13px] outline-none transition focus:border-[var(--primary)]/50 focus:ring-2 focus:ring-[var(--primary)]/15"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[12px] text-[var(--muted-foreground)]">
                {t("Goal")}
              </span>
              <textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                placeholder={t("Understand the core idea, practice with examples, and review misconceptions.")}
                className="min-h-[88px] w-full rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-[13px] outline-none transition focus:border-[var(--primary)]/50 focus:ring-2 focus:ring-[var(--primary)]/15"
              />
            </label>
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] px-3 py-2 text-[12px] font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
            >
              <X size={12} />
              {t("Close")}
            </button>
            <button
              type="button"
              onClick={() => void handleCreate()}
              disabled={!title.trim() || submitting}
              className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-3 py-2 text-[12px] font-medium text-[var(--primary-foreground)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Plus size={12} />
              )}
              {t("Create Project")}
            </button>
          </div>
        </section>
      </div>
    </Modal>
  );
}
