"use client";

import { Fragment, useMemo } from "react";

import MarkdownRenderer from "@/components/common/MarkdownRenderer";
import { hasVisibleMarkdownContent } from "@/lib/markdown-display";
import { parseModelThinkingSegments } from "@/lib/think-segments";

interface AssistantResponseProps {
  content: string;
  className?: string;
}

export default function AssistantResponse({
  content,
  className = "text-[14px] leading-[1.75]",
}: AssistantResponseProps) {
  const segments = useMemo(
    () => parseModelThinkingSegments(content),
    [content],
  );

  const hasRenderableSegment = useMemo(() => {
    return segments.some((segment) => {
      if (segment.kind === "think") return false;
      return hasVisibleMarkdownContent(segment.content);
    });
  }, [segments]);

  if (!hasRenderableSegment) return null;

  return (
    <div className={className}>
      {segments.map((segment, index) => {
        if (segment.kind === "think") {
          return <Fragment key={`think-${index}`} />;
        }

        if (!hasVisibleMarkdownContent(segment.content)) {
          return <Fragment key={`text-${index}`} />;
        }

        return (
          <MarkdownRenderer
            key={`text-${index}`}
            content={segment.content}
            variant="prose"
            className="text-[var(--foreground)]"
          />
        );
      })}
    </div>
  );
}
