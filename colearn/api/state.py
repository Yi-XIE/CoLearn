"""Resettable in-process state services for API-only settings."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any

from colearn.nanobot_bootstrap import ensure_nanobot_on_path
from colearn.storage import JsonStateStore
from colearn.paths import colearn_slim_config


def _env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if value:
        return value
    if name == "DEEPSEEK_API_KEY":
        return str(os.environ.get("OPENAI_API_KEY") or "").strip()
    return ""


def _provider_env_key(name: str) -> str | None:
    provider = str(name or "").strip().lower()
    if not provider:
        return None
    try:
        ensure_nanobot_on_path()
        from nanobot.providers.registry import find_by_name

        spec = find_by_name(provider)
        if spec and spec.env_key:
            return str(spec.env_key).strip() or None
    except (ImportError, ModuleNotFoundError):
        pass
    fallback = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "siliconflow": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    return fallback.get(provider)


DEFAULT_SETTINGS_STATE: dict[str, Any] = {
    "ui": {
        "theme": "dark",
        "language": "zh",
    },
    "memory": {
        "enabled": True,
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
                        "binding": "deepseek",
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
                        "binding": "siliconflow",
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
                        "binding": "siliconflow",
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
            {"value": "deepseek", "label": "DeepSeek", "base_url": "https://api.deepseek.com"},
        ],
        "embedding": [
            {
                "value": "siliconflow",
                "label": "SiliconFlow",
                "base_url": "https://api.siliconflow.cn/v1/embeddings",
                "default_dim": "",
            },
        ],
        "search": [
            {"value": "duckduckgo", "label": "DuckDuckGo", "credential": "none"},
            {"value": "brave", "label": "Brave Search", "credential": "api_key"},
            {"value": "tavily", "label": "Tavily", "credential": "api_key"},
            {"value": "searxng", "label": "SearXNG", "credential": "base_url"},
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
        self._migrate_provider_bindings()

    def _migrate_provider_bindings(self) -> None:
        services = dict((self._state.get("catalog") or {}).get("services") or {})
        llm = dict(services.get("llm") or {})
        for profile in list(llm.get("profiles") or []):
            if (
                str(profile.get("id") or "") == "deepseek-llm-profile"
                and str(profile.get("binding") or "") == "openai"
            ):
                profile["binding"] = "deepseek"
            if str(profile.get("binding") or "") == "deepseek" and not str(profile.get("api_key") or "").strip():
                profile["api_key"] = _env("DEEPSEEK_API_KEY")
        providers = self._state.get("providers") or {}
        for item in list((providers.get("llm") or [])):
            if str(item.get("label") or "").lower() == "deepseek" and str(item.get("value") or "") == "openai":
                item["value"] = "deepseek"
        for service_name in ("llm", "embedding"):
            service = dict(services.get(service_name) or {})
            for profile in list(service.get("profiles") or []):
                if str(profile.get("id") or "").startswith("siliconflow-") and str(profile.get("binding") or "") == "openai":
                    profile["binding"] = "siliconflow"
        for item in list((providers.get("embedding") or [])):
            if str(item.get("label") or "").lower() in {"openai", "siliconflow"} and str(item.get("value") or "") == "openai":
                item["value"] = "siliconflow"
                item["label"] = "SiliconFlow"

    def _dump(self) -> None:
        self.state_store.write_json(SETTINGS_STATE_FILE, self._state)

    def reset(self) -> None:
        self._state = deepcopy(DEFAULT_SETTINGS_STATE)
        self._dump()
        self._write_env()
        self._write_slim_config()

    def settings(self) -> dict[str, Any]:
        payload = deepcopy(self._state)
        payload.setdefault("memory", {"enabled": True})
        payload.setdefault("runtime", {})
        payload["runtime"]["config_path"] = str(colearn_slim_config())
        return payload

    def catalog(self) -> dict[str, Any]:
        return deepcopy(self._state["catalog"])

    def providers(self) -> dict[str, Any]:
        return deepcopy(self._state["providers"])

    def memory_settings(self) -> dict[str, Any]:
        memory = dict(self._state.get("memory") or {})
        return {
            "enabled": bool(memory.get("enabled", True)),
        }

    def update_ui(self, *, theme: str | None, language: str | None) -> dict[str, Any]:
        ui = self._state["ui"]
        ui["theme"] = str(theme or ui["theme"])
        ui["language"] = str(language or ui["language"])
        self._dump()
        return deepcopy(ui)

    def update_memory_settings(self, *, enabled: bool | None = None) -> dict[str, Any]:
        memory = self._state.setdefault("memory", {"enabled": True})
        if enabled is not None:
            memory["enabled"] = bool(enabled)
        self._dump()
        return self.memory_settings()

    def update_catalog(self, catalog: dict[str, Any]) -> dict[str, Any]:
        self._state["catalog"] = deepcopy(catalog)
        self._dump()
        return self.catalog()

    def apply_catalog(self, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(catalog, dict):
            self._state["catalog"] = deepcopy(catalog)
        self._dump()
        self._write_env()
        self._write_slim_config()
        return self.catalog()

    def _write_env(self) -> None:
        catalog = self._state.get("catalog") or {}
        services = dict(catalog.get("services") or {})
        llm_env = self._service_env_block(services.get("llm"), include_embedding=False)
        embedding_env = self._service_env_block(services.get("embedding"), include_embedding=True)
        search_env = self._search_env_block(services.get("search"))
        lines = [
            f"{key}={self._quote_env_value(value)}"
            for key, value in {**llm_env, **embedding_env, **search_env}.items()
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
            provider_name = self._provider_name(active_profile)
            api_key = self._provider_api_key(active_profile)
            api_base = self._string_or_none(active_profile.get("base_url"))
            model = self._string_or_none(active_model.get("model"))
            provider_env_key = _provider_env_key(provider_name)
            block.update(
                {
                    "DEEPSEEK_API_KEY": api_key if provider_name == "deepseek" else None,
                    "DEEPSEEK_API_BASE": api_base if provider_name == "deepseek" else None,
                    "DEEPSEEK_MODEL": model if provider_name == "deepseek" else None,
                }
            )
            if provider_env_key:
                block[provider_env_key] = api_key
        return block

    def _write_slim_config(self) -> None:
        catalog = self._state.get("catalog") or {}
        services = dict(catalog.get("services") or {})
        active_profile, active_model = self._resolve_active_selection(services.get("llm"))
        provider_name = self._provider_name(active_profile)
        model_name = self._string_or_none(active_model.get("model")) or self._string_or_none(active_model.get("name"))
        if not provider_name or not model_name:
            return

        config_path = colearn_slim_config()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {}
        if config_path.exists():
            try:
                raw = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    payload = raw
            except json.JSONDecodeError:
                payload = {}

        agents = dict(payload.get("agents") or {})
        defaults = dict(agents.get("defaults") or {})
        defaults["provider"] = provider_name
        defaults["model"] = model_name
        agents["defaults"] = defaults
        payload["agents"] = agents

        provider_block: dict[str, Any] = {}
        provider_env_key = _provider_env_key(provider_name)
        if provider_env_key:
            provider_block["apiKey"] = f"${{{provider_env_key}}}"
        else:
            api_key = self._string_or_none(active_profile.get("api_key"))
            if api_key:
                provider_block["apiKey"] = api_key
        api_base = self._string_or_none(active_profile.get("base_url"))
        if api_base:
            provider_block["apiBase"] = api_base
        payload["providers"] = {provider_name: provider_block}

        config_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _provider_name(self, profile: dict[str, Any]) -> str:
        return str(profile.get("binding") or profile.get("provider") or "openai").strip().lower()

    def _provider_api_key(self, profile: dict[str, Any]) -> str | None:
        explicit = self._string_or_none(profile.get("api_key"))
        if explicit:
            return explicit
        provider_name = self._provider_name(profile)
        if provider_name == "deepseek":
            return _env("DEEPSEEK_API_KEY") or None
        provider_env_key = _provider_env_key(provider_name)
        if provider_env_key:
            return self._string_or_none(os.environ.get(provider_env_key))
        return None

    def _resolve_active_selection(self, service: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        profiles = list((service or {}).get("profiles") or [])
        active_profile_id = str((service or {}).get("active_profile_id") or "")
        active_model_id = str((service or {}).get("active_model_id") or "")
        profile = next((item for item in profiles if str(item.get("id")) == active_profile_id), profiles[0] if profiles else {})
        models = list((profile or {}).get("models") or [])
        model = next((item for item in models if str(item.get("id")) == active_model_id), models[0] if models else {})
        return dict(profile or {}), dict(model or {})

    def _search_env_block(self, service: dict[str, Any] | None) -> dict[str, str | None]:
        active_profile, _ = self._resolve_active_selection(service)
        provider = str(active_profile.get("provider") or "").strip().lower()
        block: dict[str, str | None] = {
            "BRAVE_API_KEY": None,
            "TAVILY_API_KEY": None,
            "SEARXNG_BASE_URL": None,
        }
        if provider == "brave":
            block["BRAVE_API_KEY"] = self._string_or_none(active_profile.get("api_key"))
        elif provider == "tavily":
            block["TAVILY_API_KEY"] = self._string_or_none(active_profile.get("api_key"))
        elif provider == "searxng":
            block["SEARXNG_BASE_URL"] = self._string_or_none(active_profile.get("base_url"))
        return block

    def _string_or_none(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _quote_env_value(self, value: str) -> str:
        if any(ch in value for ch in (' ', '#', '"')):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return value


MEMORY_DOCS_FILE = "memory_docs.json"
_MEMORY_AUTO_SECTION_HEADER = "## 自动沉淀"


def _normalize_doc_payload(raw: Any) -> dict[str, Any]:
    payload = dict(raw or {}) if isinstance(raw, dict) else {}
    docs = dict(payload.get("docs") or {})
    updated_at = dict(payload.get("updated_at") or {})
    sources = dict(payload.get("auto_sources") or {})
    normalized: dict[str, Any] = {
        "docs": {
            "summary": str(docs.get("summary") or ""),
            "profile": str(docs.get("profile") or ""),
        },
        "updated_at": {
            "summary": str(updated_at.get("summary") or "").strip() or None,
            "profile": str(updated_at.get("profile") or "").strip() or None,
        },
        "auto_sources": {
            "summary": list(sources.get("summary") or []),
            "profile": list(sources.get("profile") or []),
        },
    }
    return normalized


def _split_manual_and_auto_sections(content: str) -> tuple[str, str]:
    text = str(content or "")
    marker = f"\n\n{_MEMORY_AUTO_SECTION_HEADER}\n"
    if marker in text:
        manual, auto = text.split(marker, 1)
        return manual.rstrip(), auto.strip()
    if text.startswith(f"{_MEMORY_AUTO_SECTION_HEADER}\n"):
        return "", text[len(_MEMORY_AUTO_SECTION_HEADER) + 1 :].strip()
    return text.rstrip(), ""


def _compose_doc_text(manual_text: str, auto_section: str) -> str:
    manual = str(manual_text or "").strip()
    auto = str(auto_section or "").strip()
    if manual and auto:
        return f"{manual}\n\n{_MEMORY_AUTO_SECTION_HEADER}\n{auto}"
    if auto:
        return f"{_MEMORY_AUTO_SECTION_HEADER}\n{auto}"
    return manual


def _render_auto_entry(*, title: str, body: str) -> str:
    clean_title = str(title or "").strip()
    clean_body = str(body or "").strip()
    if not clean_body:
        return ""
    if clean_title:
        return f"### {clean_title}\n{clean_body}"
    return clean_body


@dataclass
class MemoryDocStateService:
    state_store: JsonStateStore = field(default_factory=JsonStateStore)
    _docs: dict[str, str] = field(default_factory=lambda: {"summary": "", "profile": ""})
    _updated_at: dict[str, str | None] = field(default_factory=lambda: {"summary": None, "profile": None})
    _auto_sources: dict[str, list[str]] = field(default_factory=lambda: {"summary": [], "profile": []})

    def __post_init__(self) -> None:
        self._load()

    def _load(self) -> None:
        raw = self.state_store.read_json(MEMORY_DOCS_FILE, {})
        payload = _normalize_doc_payload(raw)
        self._docs = dict(payload["docs"])
        self._updated_at = dict(payload["updated_at"])
        self._auto_sources = {
            "summary": [str(item).strip() for item in payload["auto_sources"]["summary"] if str(item).strip()],
            "profile": [str(item).strip() for item in payload["auto_sources"]["profile"] if str(item).strip()],
        }

    def _dump(self) -> None:
        self.state_store.write_json(
            MEMORY_DOCS_FILE,
            {
                "docs": dict(self._docs),
                "updated_at": dict(self._updated_at),
                "auto_sources": {
                    "summary": list(self._auto_sources["summary"]),
                    "profile": list(self._auto_sources["profile"]),
                },
            },
        )

    def reset(self) -> None:
        self._docs = {"summary": "", "profile": ""}
        self._updated_at = {"summary": None, "profile": None}
        self._auto_sources = {"summary": [], "profile": []}
        self._dump()

    def snapshot(self) -> dict[str, Any]:
        return {
            "summary": self._docs["summary"],
            "profile": self._docs["profile"],
            "summary_updated_at": self._updated_at["summary"],
            "profile_updated_at": self._updated_at["profile"],
        }

    def update(self, file_name: str, content: str) -> dict[str, Any]:
        self._docs[file_name] = str(content or "").strip()
        self._updated_at[file_name] = str(int(time.time()))
        self._dump()
        return self.snapshot()

    def append_auto_entry(
        self,
        file_name: str,
        *,
        source_key: str,
        title: str,
        body: str,
    ) -> bool:
        normalized_key = str(source_key or "").strip()
        entry = _render_auto_entry(title=title, body=body)
        if not normalized_key or not entry:
            return False
        existing = list(self._auto_sources.get(file_name, []) or [])
        if normalized_key in existing:
            return False
        manual_text, auto_text = _split_manual_and_auto_sections(self._docs.get(file_name, ""))
        auto_entries = [item.strip() for item in auto_text.split("\n\n") if item.strip()]
        auto_entries.append(entry)
        self._docs[file_name] = _compose_doc_text(manual_text, "\n\n".join(auto_entries))
        existing.append(normalized_key)
        self._auto_sources[file_name] = existing
        self._updated_at[file_name] = str(int(time.time()))
        self._dump()
        return True

    def refresh_summary(self, summary: str) -> bool:
        clean_summary = str(summary or "").strip()
        if not clean_summary:
            return False
        source_key = f"review:{clean_summary}"
        return self.append_auto_entry(
            "summary",
            source_key=source_key,
            title="学习回顾",
            body=clean_summary,
        )


@dataclass
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
