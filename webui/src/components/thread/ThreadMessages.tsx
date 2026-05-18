import { MessageBubble } from "@/components/MessageBubble";
import {
  AgentActivityCluster,
  isAgentActivityMember,
} from "@/components/thread/AgentActivityCluster";
import type { UIMessage } from "@/lib/types";

interface ThreadMessagesProps {
  messages: UIMessage[];
  /** When true, agent turn still in flight — keeps activity cluster expanded. */
  isStreaming?: boolean;
}

export type DisplayUnit =
  | { type: "cluster"; messages: UIMessage[] }
  | { type: "single"; message: UIMessage };

/** True when this unit index is the last assistant text slice before the next user message (or end of thread). */
export function isFinalAssistantSliceBeforeNextUser(
  units: DisplayUnit[],
  index: number,
): boolean {
  const u = units[index];
  if (u.type !== "single" || u.message.role !== "assistant") return true;
  for (let j = index + 1; j < units.length; j++) {
    const v = units[j];
    if (v.type === "single" && v.message.role === "user") break;
    return false;
  }
  return true;
}

function buildDisplayUnits(messages: UIMessage[]): DisplayUnit[] {
  const out: DisplayUnit[] = [];
  let i = 0;
  while (i < messages.length) {
    const m = messages[i];
    if (isAgentActivityMember(m)) {
      const cluster: UIMessage[] = [];
      while (i < messages.length && isAgentActivityMember(messages[i])) {
        cluster.push(messages[i]);
        i += 1;
      }
      out.push({ type: "cluster", messages: cluster });
      continue;
    }
    out.push({ type: "single", message: m });
    i += 1;
  }
  return out;
}

function shouldShowThinkingPlaceholder(messages: UIMessage[], isStreaming: boolean): boolean {
  if (!isStreaming) return false;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.role === "user") break;
    if (message.kind === "trace") return false;
    if (message.role !== "assistant") continue;
    if (message.reasoningStreaming || message.reasoning?.trim()) return false;
    if (message.content.trim().length > 0) return false;
    if (message.isStreaming) return false;
  }
  return true;
}

function thinkingPlaceholderAnchorIndex(units: DisplayUnit[]): number {
  for (let i = units.length - 1; i >= 0; i -= 1) {
    const unit = units[i];
    if (unit.type === "single" && unit.message.role === "user") return i;
  }
  return -1;
}

export function ThreadMessages({ messages, isStreaming = false }: ThreadMessagesProps) {
  const units = buildDisplayUnits(messages);
  const showThinkingPlaceholder = shouldShowThinkingPlaceholder(messages, isStreaming);
  const placeholderAfterIndex = showThinkingPlaceholder
    ? thinkingPlaceholderAnchorIndex(units)
    : -1;

  return (
    <div className="flex w-full flex-col">
      {units.map((unit, index) => {
        const prev = units[index - 1];
        const marginTop =
          index > 0
            ? marginAfterPrevUnit(prev)
            : "";
        const next = units[index + 1];
        const hasBodyBelow =
          unit.type === "cluster"
          && next?.type === "single"
          && next.message.role === "assistant";

        return (
          <div key={unitKey(unit, index)} className={marginTop}>
            {unit.type === "cluster" ? (
              <AgentActivityCluster
                messages={unit.messages}
                isTurnStreaming={isStreaming}
                hasBodyBelow={hasBodyBelow}
              />
            ) : (
              <MessageBubble
                message={unit.message}
                showAssistantCopyAction={
                  unit.message.role === "assistant"
                    ? isFinalAssistantSliceBeforeNextUser(units, index)
                    : true
                }
              />
            )}
            {placeholderAfterIndex === index ? (
              <div className="mt-3">
                <MessageBubble
                  message={{
                    id: "assistant-thinking-placeholder",
                    role: "assistant",
                    content: "",
                    isStreaming: true,
                    createdAt: Date.now(),
                  }}
                />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function unitKey(unit: DisplayUnit, index: number): string {
  if (unit.type === "cluster") {
    const anchor = unit.messages[0]?.id;
    return anchor != null ? `cluster-${anchor}` : `cluster-idx-${index}`;
  }
  return unit.message.id;
}

function marginAfterPrevUnit(prev: DisplayUnit): string {
  if (prev.type === "cluster") {
    return "mt-4";
  }
  const p = prev.message;
  const denseP =
    p.kind === "trace"
    || (
      p.role === "assistant"
      && p.content.trim().length === 0
      && (!!p.reasoning || !!p.reasoningStreaming)
    );
  if (denseP) {
    return "mt-2";
  }
  return "mt-5";
}
