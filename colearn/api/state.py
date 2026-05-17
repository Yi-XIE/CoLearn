"""Resettable in-process state services for API-only settings."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import os
from pathlib import Path
import secrets
import time
from typing import Any

from colearn.storage import JsonStateStore


def _env(name: str) -> str:
    return os.environ.get(name, "")


DEFAULT_SETTINGS_STATE: dict[str, Any] = {
    "ui": {
        "theme": "dark",
        "language": "zh",
    },
    "catalog": {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "deepseek-llm-profile",
                "active_model_id": "deepseek-v4-flash",
                "profiles": [
                    {
                        "id": "deepseek-llm-profile",
                        "name": "DeepSeek LLM",
                        "binding": "openai",
                        "base_url": "https://api.deepseek.com",
                        "api_key": _env("DEEPSEEK_API_KEY"),
                        "api_version": "",
                        "extra_headers": {},
                        "proxy": "",
                        "models": [
                            {
                                "id": "deepseek-v4-flash",
                                "name": "deepseek-v4-flash",
                                "model": "deepseek-v4-flash",
                                "context_window": "64000",
                                "context_window_source": "default",
                            }
                        ],
                    },
                    {
                        "id": "siliconflow-vl-profile",
                        "name": "SiliconFlow Vision",
                        "binding": "openai",
                        "base_url": "https://api.siliconflow.cn/v1/chat/completions",
                        "api_key": os.environ.get("EMBEDDING_API_KEY", ""),
                        "api_version": "",
                        "extra_headers": {},
                        "proxy": "",
                        "models": [
                            {
                                "id": "qwen3-vl-32b-thinking",
                                "name": "Qwen/Qwen3-VL-32B-Thinking",
                                "model": "Qwen/Qwen3-VL-32B-Thinking",
                                "context_window": "64000",
                                "context_window_source": "default",
                            }
                        ],
                    }
                ],
            },
            "embedding": {
                "active_profile_id": "siliconflow-embedding-profile",
                "active_model_id": "qwen3-embedding-8b",
                "profiles": [
                    {
                        "id": "siliconflow-embedding-profile",
                        "name": "SiliconFlow Embedding",
                        "binding": "openai",
                        "base_url": "https://api.siliconflow.cn/v1/embeddings",
                        "api_key": os.environ.get("EMBEDDING_API_KEY", ""),
                        "api_version": "",
                        "extra_headers": {},
                        "proxy": "",
                        "models": [
                            {
                                "id": "qwen3-embedding-8b",
                                "name": "Qwen/Qwen3-Embedding-8B",
                                "model": "Qwen/Qwen3-Embedding-8B",
                                "dimension": "",
                                "send_dimensions": False,
                                "supported_dimensions": "",
                            }
                        ],
                    }
                ],
            },
            "search": {
                "active_profile_id": "default-search-profile",
                "profiles": [
                    {
                        "id": "default-search-profile",
                        "name": "Default Search",
                        "provider": "brave",
                        "binding": None,
                        "base_url": "",
                        "api_key": "",
                        "api_version": "",
                        "extra_headers": {},
                        "proxy": "",
                        "models": [],
                    }
                ],
            },
        },
    },
    "providers": {
        "llm": [
            {"value": "openai", "label": "DeepSeek", "base_url": "https://api.deepseek.com"},
        ],
        "embedding": [
            {
                "value": "openai",
                "label": "OpenAI",
                "base_url": "https://api.siliconflow.cn/v1/embeddings",
                "default_dim": "",
            },
        ],
        "search": [
            {"value": "brave", "label": "Brave Search"},
            {"value": "tavily", "label": "Tavily"},
            {"value": "perplexity", "label": "Perplexity"},
        ],
    },
}

SETTINGS_STATE_FILE = "settings_state.json"


@dataclass
class SettingsStateService:
    state_store: JsonStateStore = field(default_factory=JsonStateStore)
    env_path: Path = field(default_factory=lambda: Path.cwd() / ".env")
    _state: dict[str, Any] = field(default_factory=lambda: deepcopy(DEFAULT_SETTINGS_STATE))

    def __post_init__(self) -> None:
        self._load()

    def _load(self) -> None:
        raw = self.state_store.read_json(SETTINGS_STATE_FILE, DEFAULT_SETTINGS_STATE)
        if isinstance(raw, dict):
            self._state = deepcopy(raw)
        else:
            self._state = deepcopy(DEFAULT_SETTINGS_STATE)

    def _dump(self) -> None:
        self.state_store.write_json(SETTINGS_STATE_FILE, self._state)

    def reset(self) -> None:
        self._state = deepcopy(DEFAULT_SETTINGS_STATE)
        self._dump()

    def settings(self) -> dict[str, Any]:
        return deepcopy(self._state)

    def catalog(self) -> dict[str, Any]:
        return deepcopy(self._state["catalog"])

    def providers(self) -> dict[str, Any]:
        return deepcopy(self._state["providers"])

    def update_ui(self, *, theme: str | None, language: str | None) -> dict[str, Any]:
        ui = self._state["ui"]
        ui["theme"] = str(theme or ui["theme"])
        ui["language"] = str(language or ui["language"])
        self._dump()
        return deepcopy(ui)

    def update_catalog(self, catalog: dict[str, Any]) -> dict[str, Any]:
        self._state["catalog"] = deepcopy(catalog)
        self._dump()
        return self.catalog()

    def apply_catalog(self, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(catalog, dict):
            self._state["catalog"] = deepcopy(catalog)
        self._dump()
        self._write_env()
        return self.catalog()

    def _write_env(self) -> None:
        catalog = self._state.get("catalog") or {}
        services = dict(catalog.get("services") or {})
        llm_env = self._service_env_block(services.get("llm"), include_embedding=False)
        embedding_env = self._service_env_block(services.get("embedding"), include_embedding=True)
        lines = [
            f"{key}={self._quote_env_value(value)}"
            for key, value in {**llm_env, **embedding_env}.items()
            if value is not None
        ]
        payload = "\n".join(lines).rstrip() + "\n"
        self.env_path.write_text(payload, encoding="utf-8")

    def _service_env_block(
        self,
        service: dict[str, Any] | None,
        *,
        include_embedding: bool,
    ) -> dict[str, str | None]:
        active_profile, active_model = self._resolve_active_selection(service)
        block: dict[str, str | None] = {}
        if include_embedding:
            block.update(
                {
                    "EMBEDDING_API_KEY": self._string_or_none(active_profile.get("api_key")),
                    "EMBEDDING_BASE_URL": self._string_or_none(active_profile.get("base_url")),
                    "EMBEDDING_MODEL": self._string_or_none(active_model.get("model")),
                    "EMBEDDING_DIM": self._string_or_none(active_model.get("dimension")),
                    "EMBEDDING_SEND_DIMENSIONS": "true"
                    if bool(active_model.get("send_dimensions", True))
                    else "false",
                }
            )
        else:
            block.update(
                {
                    "DEEPSEEK_API_KEY": self._string_or_none(active_profile.get("api_key")),
                    "DEEPSEEK_API_BASE": self._string_or_none(active_profile.get("base_url")),
                    "DEEPSEEK_MODEL": self._string_or_none(active_model.get("model")),
                }
            )
        return block

    def _resolve_active_selection(self, service: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        profiles = list((service or {}).get("profiles") or [])
        active_profile_id = str((service or {}).get("active_profile_id") or "")
        active_model_id = str((service or {}).get("active_model_id") or "")
        profile = next((item for item in profiles if str(item.get("id")) == active_profile_id), profiles[0] if profiles else {})
        models = list((profile or {}).get("models") or [])
        model = next((item for item in models if str(item.get("id")) == active_model_id), models[0] if models else {})
        return dict(profile or {}), dict(model or {})

    def _string_or_none(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _quote_env_value(self, value: str) -> str:
        if any(ch in value for ch in (' ', '#', '"')):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return value


@dataclass
class MemoryDocStateService:
    _docs: dict[str, str] = field(default_factory=lambda: {"summary": "", "profile": ""})
    _updated_at: dict[str, str | None] = field(default_factory=lambda: {"summary": None, "profile": None})

    def reset(self) -> None:
        self._docs = {"summary": "", "profile": ""}
        self._updated_at = {"summary": None, "profile": None}

    def snapshot(self) -> dict[str, Any]:
        return {
            "summary": self._docs["summary"],
            "profile": self._docs["profile"],
            "summary_updated_at": self._updated_at["summary"],
            "profile_updated_at": self._updated_at["profile"],
        }

    def update(self, file_name: str, content: str) -> dict[str, Any]:
        self._docs[file_name] = content
        self._updated_at[file_name] = str(int(time.time()))
        return self.snapshot()

    def refresh_summary(self, summary: str) -> bool:
        if not summary or summary == self._docs["summary"]:
            return False
        self._docs["summary"] = summary
        self._updated_at["summary"] = str(int(time.time()))
        return True


@dataclass
class SkillStateService:
    _skills: dict[str, dict[str, Any]] = field(default_factory=dict)
    _tags: dict[str, str] = field(default_factory=dict)

    def reset(self) -> None:
        self._skills = {}
        self._tags = {}

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": str(record.get("description") or ""),
                "tags": list(record.get("tags") or []),
            }
            for name, record in self._skills.items()
        ]

    def get_skill(self, name: str) -> dict[str, Any]:
        return dict(self._skills.get(name) or {})

    def save_skill(self, name: str, record: dict[str, Any]) -> None:
        self._skills[name] = dict(record)

    def delete_skill(self, name: str) -> None:
        self._skills.pop(name, None)

    def list_tags(self) -> list[str]:
        return sorted(self._tags.keys())

    def save_tag(self, name: str) -> None:
        self._tags[name] = name

    def rename_tag(self, old_name: str, new_name: str) -> None:
        self._tags.pop(old_name, None)
        self._tags[new_name] = new_name

    def delete_tag(self, name: str) -> None:
        self._tags.pop(name, None)


@dataclass
class AuthStateService:
    state_store: JsonStateStore = field(default_factory=JsonStateStore)
    _users: dict[str, dict[str, Any]] = field(default_factory=dict)
    _sessions: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._users = {}
        self._sessions = {}
        self._load()

    def _load(self) -> None:
        raw = self.state_store.read_json("auth_state.json", {"users": [], "sessions": {}})
        users = raw.get("users") if isinstance(raw, dict) else []
        sessions = raw.get("sessions") if isinstance(raw, dict) else {}
        if isinstance(users, list):
            for item in users:
                if not isinstance(item, dict):
                    continue
                username = str(item.get("username") or "").strip()
                if not username:
                    continue
                self._users[username] = {
                    "user_id": str(item.get("user_id") or username),
                    "username": username,
                    "password": str(item.get("password") or ""),
                    "role": str(item.get("role") or "user"),
                    "is_admin": bool(item.get("is_admin")),
                }
        if isinstance(sessions, dict):
            self._sessions = {
                str(token): str(username)
                for token, username in sessions.items()
                if str(token).strip() and str(username).strip()
            }

    def _dump(self) -> None:
        self.state_store.write_json(
            "auth_state.json",
            {
                "users": list(self._users.values()),
                "sessions": dict(self._sessions),
            },
        )

    def reset(self) -> None:
        self._users = {}
        self._sessions = {}
        self._dump()

    def is_first_user(self) -> bool:
        return len(self._users) == 0

    def register(self, username: str, password: str) -> dict[str, Any]:
        normalized = username.strip()
        if not normalized or not password:
            raise ValueError("Username and password are required")
        if normalized in self._users:
            raise FileExistsError("Username already exists")
        is_first = self.is_first_user()
        record = {
            "user_id": normalized,
            "username": normalized,
            "password": password,
            "role": "admin" if is_first else "user",
            "is_admin": is_first,
        }
        self._users[normalized] = record
        self._dump()
        return {**record, "is_first_user": is_first}

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        record = self._users.get(username.strip())
        if not record or record.get("password") != password:
            return None
        return dict(record)

    def create_session(self, username: str) -> str:
        token = secrets.token_urlsafe(24)
        self._sessions[token] = username
        self._dump()
        return token

    def delete_session(self, token: str) -> None:
        if token in self._sessions:
            self._sessions.pop(token, None)
            self._dump()

    def user_for_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        username = self._sessions.get(token)
        if not username:
            return None
        record = self._users.get(username)
        return dict(record) if record else None


@dataclass
class KnowledgeTaskService:
    state_root: Path
    _tasks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def reset(self) -> None:
        self._tasks = {}

    def _kb_dir(self, kb_name: str) -> Path:
        return self.state_root / "knowledge" / kb_name

    def _serialize_progress(self, task: dict[str, Any]) -> dict[str, Any]:
        progress = dict(task.get("progress") or {})
        progress.setdefault("task_id", task["task_id"])
        progress.setdefault("stage", task.get("status"))
        progress.setdefault("message", task.get("message") or "")
        progress.setdefault("percent", 100 if task.get("status") == "completed" else 0)
        progress.setdefault("current", 1 if task.get("status") == "completed" else 0)
        progress.setdefault("total", 1)
        return progress

    def create_task(
        self,
        *,
        kb_name: str,
        kind: str,
        message: str,
        files: list[dict[str, Any]] | None = None,
        should_fail: bool = False,
    ) -> dict[str, Any]:
        task_id = secrets.token_hex(12)
        now = time.time()
        progress = {
            "task_id": task_id,
            "stage": "completed" if not should_fail else "error",
            "message": message,
            "current": 1,
            "total": 1,
            "percent": 100 if not should_fail else 0,
            "progress_percent": 100 if not should_fail else 0,
        }
        task = {
            "task_id": task_id,
            "kb_name": kb_name,
            "kind": kind,
            "status": "failed" if should_fail else "completed",
            "message": message,
            "detail": "Task failed" if should_fail else "",
            "created_at": now,
            "updated_at": now,
            "files": list(files or []),
            "progress": progress,
            "logs": [
                f"{kind} started for {kb_name}",
                f"{kind} {'failed' if should_fail else 'completed'} for {kb_name}",
            ],
        }
        self._tasks[task_id] = task
        return dict(task)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        return dict(task) if task else None

    def latest_for_kb(self, kb_name: str, task_id: str | None = None) -> dict[str, Any] | None:
        if task_id:
            task = self._tasks.get(task_id)
            if task and task.get("kb_name") == kb_name:
                return dict(task)
            return None
        for task in sorted(self._tasks.values(), key=lambda item: item.get("updated_at", 0), reverse=True):
            if task.get("kb_name") == kb_name:
                return dict(task)
        return None

    def save_files(self, kb_name: str, uploads: list[tuple[str, bytes, str | None]]) -> list[dict[str, Any]]:
        kb_dir = self._kb_dir(kb_name)
        kb_dir.mkdir(parents=True, exist_ok=True)
        saved: list[dict[str, Any]] = []
        for filename, content, mime_type in uploads:
            target = kb_dir / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            stat = target.stat()
            saved.append(
                {
                    "name": filename,
                    "path": str(target),
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                    "mime_type": mime_type,
                }
            )
        return saved

    def list_files(self, kb_name: str) -> list[dict[str, Any]]:
        kb_dir = self._kb_dir(kb_name)
        if not kb_dir.exists():
            return []
        files: list[dict[str, Any]] = []
        for path in kb_dir.rglob("*"):
            if not path.is_file():
                continue
            stat = path.stat()
            files.append(
                {
                    "name": path.relative_to(kb_dir).as_posix(),
                    "path": str(path),
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                    "mime_type": None,
                }
            )
        return sorted(files, key=lambda item: str(item["name"]).lower())

    def resolve_file(self, kb_name: str, filename: str) -> Path | None:
        kb_dir = self._kb_dir(kb_name).resolve()
        candidate = (kb_dir / filename).resolve()
        try:
            candidate.relative_to(kb_dir)
        except ValueError:
            return None
        return candidate if candidate.exists() and candidate.is_file() else None

    def stream_events(self, task_id: str) -> list[dict[str, Any]]:
        task = self._tasks.get(task_id)
        if not task:
            return []
        progress = self._serialize_progress(task)
        return [
            {"event": "process_log", "data": {"message": item}}
            for item in task.get("logs", [])
        ] + [
            {"event": "progress", "data": progress},
            {"event": "failed" if task.get("status") == "failed" else "complete", "data": {"detail": task.get("detail") or "Task failed"}},
        ]


@dataclass
class SettingsTestRunService:
    _runs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def reset(self) -> None:
        self._runs = {}

    def create_run(self, service: str, catalog: dict[str, Any]) -> dict[str, Any]:
        run_id = f"{service}-{secrets.token_hex(6)}"
        now = time.time()
        events = [
            {
                "type": "running",
                "message": f"{service} diagnostics started.",
                "timestamp": now,
            },
            {
                "type": "info",
                "message": f"{service} catalog accepted.",
                "timestamp": now + 0.01,
            },
            {
                "type": "completed",
                "message": f"{service} diagnostics completed.",
                "timestamp": now + 0.02,
                "catalog": deepcopy(catalog),
            },
        ]
        run = {
            "run_id": run_id,
            "service": service,
            "status": "completed",
            "accepted": True,
            "events": events,
        }
        self._runs[run_id] = run
        return dict(run)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self._runs.get(run_id)
        return dict(run) if run else None
