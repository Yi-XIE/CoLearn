import test from "node:test";
import assert from "node:assert/strict";

import {
  selectedSourcesToPayload,
  selectedSourceRefsToSourceIds,
  sourceIdsToSelectedSourceRefs,
} from "../lib/source-references";

test("sourceIdsToSelectedSourceRefs rebuilds project source selections for chat rehydration", () => {
  assert.deepEqual(sourceIdsToSelectedSourceRefs(["kb-1:file-a.md", "kb-2:file-b.pdf"]), [
    {
      sourceId: "kb-1:file-a.md",
      sourceType: "knowledge_file",
      title: "file-a.md",
      kbId: "kb-1",
      kbName: "kb-1",
      fileName: "file-a.md",
    },
    {
      sourceId: "kb-2:file-b.pdf",
      sourceType: "knowledge_file",
      title: "file-b.pdf",
      kbId: "kb-2",
      kbName: "kb-2",
      fileName: "file-b.pdf",
    },
  ]);
});

test("selectedSourceRefsToSourceIds preserves unique source ids for persistence", () => {
  assert.deepEqual(
    selectedSourceRefsToSourceIds([
      {
        sourceId: "kb-1:file-a.md",
        sourceType: "knowledge_file",
        title: "file-a.md",
        kbId: "kb-1",
        kbName: "kb-1",
        fileName: "file-a.md",
      },
      {
        sourceId: "kb-1:file-a.md",
        sourceType: "knowledge_file",
        title: "duplicate",
        kbId: "kb-1",
        kbName: "kb-1",
        fileName: "file-a.md",
      },
    ]),
    ["kb-1:file-a.md"],
  );
});

test("selectedSourcesToPayload preserves web-note references", () => {
  assert.deepEqual(
    selectedSourcesToPayload([
      {
        sourceId: "web:https://example.com/article",
        sourceType: "web_note",
        title: "https://example.com/article",
        url: "https://example.com/article",
        textPreview: "Key takeaway from the article.",
      },
    ]),
    [
      {
        source_id: "web:https://example.com/article",
        source_type: "web_note",
        title: "https://example.com/article",
        url: "https://example.com/article",
        text_preview: "Key takeaway from the article.",
        kb_id: undefined,
        kb_name: undefined,
        file_name: undefined,
      },
    ],
  );
});

test("selectedSourcesToPayload preserves attachment-file references", () => {
  assert.deepEqual(
    selectedSourcesToPayload([
      {
        sourceId: "attachment:lesson-notes.pdf",
        sourceType: "attachment_file",
        title: "lesson-notes.pdf",
        fileName: "lesson-notes.pdf",
        mimeType: "application/pdf",
        size: 1024,
      },
    ]),
    [
      {
        source_id: "attachment:lesson-notes.pdf",
        source_type: "attachment_file",
        title: "lesson-notes.pdf",
        file_name: "lesson-notes.pdf",
        kb_id: undefined,
        kb_name: undefined,
        text_preview: undefined,
        url: undefined,
      },
    ],
  );
});
