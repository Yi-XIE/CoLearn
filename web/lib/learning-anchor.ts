export interface LearningAnchorShape {
  topic: string;
  source_refs: string[];
  prior_knowledge: string;
  target_depth: string;
  preferred_method: string;
}

function asAnchorShape(value: unknown): LearningAnchorShape | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const anchor = value as Record<string, unknown>;
  return {
    topic: String(anchor.topic || ""),
    source_refs: Array.isArray(anchor.source_refs)
      ? anchor.source_refs.map((item) => String(item || ""))
      : [],
    prior_knowledge: String(anchor.prior_knowledge || ""),
    target_depth: String(anchor.target_depth || ""),
    preferred_method: String(anchor.preferred_method || ""),
  };
}

export function hasCompleteLearningAnchor(
  anchor: unknown,
): anchor is LearningAnchorShape {
  const normalized = asAnchorShape(anchor);
  if (!normalized) return false;
  return Boolean(
    normalized.topic.trim() &&
      normalized.source_refs.some((item) => item.trim()) &&
      normalized.prior_knowledge.trim() &&
      normalized.target_depth.trim() &&
      normalized.preferred_method.trim(),
  );
}

export function initialLearningStateForAnchor(
  anchor: unknown,
): "IDLE" {
  void anchor;
  return "IDLE";
}
