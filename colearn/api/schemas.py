"""HTTP and WebSocket payload schemas for the CoLearn backend."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionCreatePayload(BaseModel):
    title: str = ""
    project_id: str
    project_title: str = ""
    turn_mode: str = "EXPLORE"
    source_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)


class SessionUpdatePayload(BaseModel):
    title: str = ""


class ProjectCreatePayload(BaseModel):
    title: str
    goal: str = ""
    slug: str = ""


class ProjectUpdatePayload(BaseModel):
    title: str | None = None
    goal: str | None = None
    status: str | None = None
    source_refs: list[str] | None = None


class ProjectSourcesPayload(BaseModel):
    source_refs: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)


class ProjectAnchorPayload(BaseModel):
    topic: str
    source_refs: list[str] = Field(default_factory=list)
    prior_knowledge: str = ""
    target_depth: str = ""
    preferred_method: str = ""


class StartTurnPayload(BaseModel):
    type: Literal["message", "start_turn"] = "start_turn"
    content: str
    tools: list[str] = Field(default_factory=list)
    knowledge_bases: list[str] = Field(default_factory=list)
    project_id: str | None = None
    project_title: str | None = None
    session_id: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    language: str = "zh"
    config: dict[str, Any] = Field(default_factory=dict)
    history_references: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    memory_references: list[str] = Field(default_factory=list)
    llm_selection: dict[str, Any] | None = None


class RegeneratePayload(BaseModel):
    type: Literal["regenerate"] = "regenerate"
    session_id: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class CancelTurnPayload(BaseModel):
    type: Literal["cancel_turn"] = "cancel_turn"
    turn_id: str


class SubscribeTurnPayload(BaseModel):
    type: Literal["subscribe_turn", "resume_from"] = "subscribe_turn"
    turn_id: str
    after_seq: int = 0


class PingPayload(BaseModel):
    type: Literal["ping"] = "ping"


class SkillPayload(BaseModel):
    name: str
    description: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)


class SkillUpdatePayload(BaseModel):
    description: str | None = None
    content: str | None = None
    rename_to: str | None = None
    tags: list[str] = Field(default_factory=list)


class SkillTagPayload(BaseModel):
    name: str
    rename_to: str | None = None


class SettingsUiPayload(BaseModel):
    theme: str | None = None
    language: str | None = None


class SettingsCatalogPayload(BaseModel):
    catalog: dict[str, Any] = Field(default_factory=dict)


class SettingsTestStartPayload(BaseModel):
    catalog: dict[str, Any] = Field(default_factory=dict)


class AuthLoginPayload(BaseModel):
    username: str
    password: str


class AuthRegisterPayload(BaseModel):
    username: str
    password: str


class MemoryUpdatePayload(BaseModel):
    file: Literal["summary", "profile"]
    content: str = ""


class MemoryRefreshPayload(BaseModel):
    pass


class MemoryFilePayload(BaseModel):
    file: Literal["summary", "profile"]
