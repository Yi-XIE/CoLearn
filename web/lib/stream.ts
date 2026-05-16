import type { StreamEvent } from "@/lib/unified-ws";

export function shouldAppendEventContent(event: StreamEvent): boolean {
  if (event.type !== "content" && event.type !== "result") return false;
  const metadata = (event.metadata ?? {}) as {
    call_id?: string;
    call_kind?: string;
  };
  if (!metadata.call_id) return event.type === "content";
  return metadata.call_kind === "llm_final_response";
}
