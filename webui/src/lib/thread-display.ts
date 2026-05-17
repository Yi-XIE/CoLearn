import type { UIMessage } from "@/lib/types";

/**
 * Normalize historical thread rows into the current display shape.
 */
export function projectThreadMessages(messages: UIMessage[]): UIMessage[] {
  return messages.map((m) => {
    const kind = (m as { kind?: string }).kind;
    if (kind !== "long_task") return m;
    const text = (m.content ?? "").trim() || "(thread activity)";
    return {
      id: m.id,
      role: "tool",
      kind: "trace",
      content: text,
      traces: [text],
      createdAt: m.createdAt,
    };
  });
}
