"use client";

import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import Modal from "@/components/common/Modal";
import type { SessionSummary } from "@/lib/session-api";

interface SessionDeleteModalProps {
  open: boolean;
  session: SessionSummary | null;
  deleting?: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
}

export default function SessionDeleteModal({
  open,
  session,
  deleting = false,
  onClose,
  onConfirm,
}: SessionDeleteModalProps) {
  const { t } = useTranslation();
  const title = session?.title?.trim() || t("Untitled");

  return (
    <Modal
      isOpen={open}
      onClose={deleting ? () => {} : onClose}
      title={t("Delete chat")}
      titleIcon={<AlertTriangle className="h-4 w-4 text-amber-400" />}
      width="sm"
      closeOnBackdrop={!deleting}
      closeOnEscape={!deleting}
      showCloseButton={false}
      headerClassName="border-b-0 pb-1"
      footerClassName="border-t-0 pt-2"
      footer={
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={deleting}
            className="rounded-lg border border-[var(--border)]/70 px-3 py-2 text-[12px] font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)]/40 hover:text-[var(--foreground)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("Cancel")}
          </button>
          <button
            type="button"
            onClick={() => void onConfirm()}
            disabled={deleting}
            className="rounded-lg bg-[var(--foreground)] px-3 py-2 text-[12px] font-medium text-[var(--background)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("Delete")}
          </button>
        </div>
      }
    >
      <div className="px-5 pb-1 pt-2">
        <div className="text-[13px] font-medium text-[var(--foreground)]">
          {title}
        </div>
        <p className="mt-2 text-[12px] leading-6 text-[var(--muted-foreground)]">
          {t("Delete this chat history?")}
        </p>
      </div>
    </Modal>
  );
}
