import type { ReactNode } from "react";

export function InfoCard({
  title,
  body,
  actions,
}: {
  title: string;
  body: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border/50 bg-card/85 p-5 shadow-[0_16px_50px_rgba(15,23,42,0.06)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-semibold text-foreground">{title}</div>
          <div className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{body}</div>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
    </div>
  );
}

export function EmptyHint({ text }: { text: string }) {
  return <div className="text-sm text-muted-foreground">{text}</div>;
}
