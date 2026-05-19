"""Tests for typed API schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from colearn.api.schemas import (
    AttachmentSchema,
    LLMSelectionSchema,
    ProjectSourcesPayload,
    SourceReferenceSchema,
    StartTurnPayload,
)


def test_attachment_schema_defaults():
    a = AttachmentSchema()
    assert a.name == ""
    assert a.content_type == ""
    assert a.size == 0


def test_attachment_schema_accepts_extra_keys():
    a = AttachmentSchema(name="f.png", content_type="image/png", custom_field="x")
    assert a.name == "f.png"
    assert a.model_dump()["custom_field"] == "x"


def test_source_reference_schema_defaults_and_fields():
    sr = SourceReferenceSchema(source_ref="a.md", title="A")
    assert sr.source_ref == "a.md"
    assert sr.source_path == ""
    assert sr.title == "A"


def test_llm_selection_schema_optional_fields():
    sel = LLMSelectionSchema(profile="default", model="gpt-4")
    assert sel.profile == "default"
    assert sel.model == "gpt-4"


def test_llm_selection_schema_accepts_extra():
    sel = LLMSelectionSchema(profile="x", temperature=0.7)
    assert sel.model_dump()["temperature"] == 0.7


def test_start_turn_payload_with_typed_attachments():
    payload = StartTurnPayload(
        content="hi",
        attachments=[{"name": "f.pdf", "content_type": "application/pdf"}],
    )
    assert isinstance(payload.attachments[0], AttachmentSchema)
    assert payload.attachments[0].name == "f.pdf"


def test_start_turn_payload_with_typed_source_references():
    payload = StartTurnPayload(
        content="hi",
        source_references=[{"source_ref": "a.md", "title": "A"}],
    )
    assert isinstance(payload.source_references[0], SourceReferenceSchema)
    assert payload.source_references[0].source_ref == "a.md"


def test_start_turn_payload_llm_selection_none_default():
    payload = StartTurnPayload(content="hi")
    assert payload.llm_selection is None
    assert payload.attachments == []


def test_start_turn_payload_requires_content():
    with pytest.raises(ValidationError):
        StartTurnPayload()  # content missing


def test_project_sources_payload_with_typed_refs():
    payload = ProjectSourcesPayload(
        source_refs=["a.md", "b.md"],
        source_references=[{"source_ref": "a.md", "source_path": "/tmp/a.md", "title": "A"}],
    )
    assert payload.source_refs == ["a.md", "b.md"]
    assert isinstance(payload.source_references[0], SourceReferenceSchema)
    assert payload.source_references[0].source_path == "/tmp/a.md"


def test_source_reference_schema_extra_allowed():
    sr = SourceReferenceSchema(source_ref="a.md", custom="x")
    assert sr.model_dump()["custom"] == "x"
