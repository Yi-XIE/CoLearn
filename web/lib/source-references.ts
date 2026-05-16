"use client";

export type SourceReferenceType =
  | "knowledge_file"
  | "attachment_file"
  | "web_note";

export interface SelectedSourceRef {
  sourceId: string;
  sourceType: SourceReferenceType;
  title: string;
  kbId?: string;
  kbName?: string;
  fileName?: string;
  textPreview?: string;
  url?: string;
  mimeType?: string | null;
  size?: number;
  modified?: number;
}

export interface SourceReferencePayload {
  source_id: string;
  source_type: SourceReferenceType;
  title: string;
  kb_id?: string;
  kb_name?: string;
  file_name?: string;
  text_preview?: string;
  url?: string;
}

export function selectedSourcesToPayload(
  refs: SelectedSourceRef[],
): SourceReferencePayload[] {
  const seen = new Set<string>();
  return refs.flatMap((ref) => {
    const sourceId = ref.sourceId.trim();
    if (!sourceId || seen.has(sourceId)) return [];
    seen.add(sourceId);
    return [
      {
        source_id: sourceId,
        source_type: ref.sourceType,
        title: ref.title.trim() || ref.fileName?.trim() || sourceId,
        kb_id: ref.kbId?.trim(),
        kb_name: ref.kbName?.trim(),
        file_name: ref.fileName?.trim(),
        text_preview: ref.textPreview?.trim(),
        url: ref.url?.trim(),
      },
    ];
  });
}

export function normalizeSourceReferences(
  value: unknown,
): SourceReferencePayload[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.flatMap((item) => {
    const record =
      item && typeof item === "object" && !Array.isArray(item)
        ? (item as Record<string, unknown>)
        : null;
    if (!record) return [];
    const sourceId =
      typeof record.source_id === "string" ? record.source_id.trim() : "";
    const sourceType =
      record.source_type === "knowledge_file" ||
      record.source_type === "attachment_file" ||
      record.source_type === "web_note"
        ? record.source_type
        : null;
    const title = typeof record.title === "string" ? record.title.trim() : "";
    const kbId = typeof record.kb_id === "string" ? record.kb_id.trim() : "";
    const kbName =
      typeof record.kb_name === "string" ? record.kb_name.trim() : "";
    const fileName =
      typeof record.file_name === "string" ? record.file_name.trim() : "";
    const textPreview =
      typeof record.text_preview === "string"
        ? record.text_preview.trim()
        : "";
    const url = typeof record.url === "string" ? record.url.trim() : "";
    if (
      !sourceId ||
      !sourceType ||
      (sourceType === "knowledge_file" && (!fileName || (!kbId && !kbName))) ||
      (sourceType === "attachment_file" && !fileName) ||
      (sourceType === "web_note" && !textPreview && !url) ||
      seen.has(sourceId)
    ) {
      return [];
    }
    seen.add(sourceId);
    return [
      {
        source_id: sourceId,
        source_type: sourceType,
        title: title || fileName || url || sourceId,
        kb_id: kbId || undefined,
        kb_name: kbName || undefined,
        file_name: fileName || undefined,
        text_preview: textPreview || undefined,
        url: url || undefined,
      },
    ];
  });
}

export function sourceIdsToSelectedSourceRefs(
  sourceIds: string[],
): SelectedSourceRef[] {
  const seen = new Set<string>();
  return sourceIds.flatMap((rawSourceId) => {
    const sourceId = String(rawSourceId || "").trim();
    if (!sourceId || seen.has(sourceId) || !sourceId.includes(":")) return [];
    const [kbRef, fileName] = sourceId.split(":", 2);
    const nextKbRef = kbRef.trim();
    const nextFileName = fileName.trim();
    if (!nextKbRef || !nextFileName) return [];
    seen.add(sourceId);
    return [
      {
        sourceId,
        sourceType: "knowledge_file",
        title: nextFileName,
        kbId: nextKbRef,
        kbName: nextKbRef,
        fileName: nextFileName,
      },
    ];
  });
}

export function payloadsToSelectedSourceRefs(
  payloads: SourceReferencePayload[],
): SelectedSourceRef[] {
  const seen = new Set<string>();
  return payloads.flatMap((item) => {
    const sourceId = String(item.source_id || "").trim();
    if (!sourceId || seen.has(sourceId)) return [];
    seen.add(sourceId);
    return [
      {
        sourceId,
        sourceType: item.source_type,
        title: String(item.title || "").trim() || sourceId,
        kbId: item.kb_id?.trim(),
        kbName: item.kb_name?.trim(),
        fileName: item.file_name?.trim(),
        textPreview: item.text_preview?.trim(),
        url: item.url?.trim(),
      },
    ];
  });
}

export function selectedSourceRefsToSourceIds(
  refs: SelectedSourceRef[],
): string[] {
  const seen = new Set<string>();
  return refs.flatMap((ref) => {
    const sourceId = String(ref.sourceId || "").trim();
    if (!sourceId || seen.has(sourceId)) return [];
    seen.add(sourceId);
    return [sourceId];
  });
}
