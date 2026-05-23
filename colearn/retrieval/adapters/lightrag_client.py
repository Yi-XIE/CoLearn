"""LightRAG client implementations and factory function."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Mapping
from urllib import error as urllib_error

from colearn.logging_config import get_logger

from .lightrag_protocol import (
    DEFAULT_TOP_K,
    LightRAGBackendProtocol,
    LightRAGClientProtocol,
    LightRAGConfigurationError,
    LightRAGRetrievalResult,
)
from .lightrag_config import LightRAGConfig
from .lightrag_http import HttpLightRAGBackend

logger = get_logger(__name__)


class NoOpLightRAGClient:
    enabled = False

    def __init__(self, *, path: Path | None = None) -> None:
        self.path = path or Path.cwd() / ".colearn" / "lightrag.json"

    def reload(self, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
        _ = env
        return {"enabled": False}

    def save(self) -> Path:
        return self.path

    def sync_project_sources(
        self,
        project_id: str,
        source_refs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "enabled": False,
            "synced": False,
            "source_count": len(source_refs),
            "indexed_paths": [],
            "sync_status": "disabled",
            "warnings": ["lightrag_disabled"],
        }

    async def async_sync_project_sources(
        self,
        project_id: str,
        source_refs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self.sync_project_sources(project_id, source_refs)

    def retrieve_project_context(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[dict[str, Any]],
        top_k: int = DEFAULT_TOP_K,
    ) -> LightRAGRetrievalResult:
        _ = (project_id, source_refs, top_k)
        return LightRAGRetrievalResult(
            query=query,
            warnings=["lightrag_disabled"],
            references=[],
            chunks=[],
            retrieval_status="unavailable",
            fallback_reason="lightrag_disabled",
        )

    async def async_retrieve_project_context(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[dict[str, Any]],
        top_k: int = DEFAULT_TOP_K,
    ) -> LightRAGRetrievalResult:
        return self.retrieve_project_context(
            project_id=project_id,
            query=query,
            source_refs=source_refs,
            top_k=top_k,
        )


class LightRAGClient:
    def __init__(
        self,
        *,
        config: LightRAGConfig,
        path: Path,
        workspace: Path,
        backend: LightRAGBackendProtocol,
    ) -> None:
        self.config = config
        self.path = path
        self.workspace = workspace
        self.enabled = config.enabled
        self._backend = backend
        self._registry_path = workspace / ".colearn" / "lightrag" / "project_sources.json"
        self._kb_name = "colearn-global"

    def reload(self, *, env: Mapping[str, str] | None = None) -> LightRAGConfig:
        self.config = LightRAGConfig.load(self.path, env=env)
        self.enabled = self.config.enabled
        return self.config

    def save(self) -> Path:
        return self.config.save(self.path)

    async def async_sync_project_sources(
        self,
        project_id: str,
        source_refs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        project_key = str(project_id or "").strip()
        registry = self._load_registry()
        indexed_paths = sorted(
            {
                str(item.get("source_path") or item.get("path") or item.get("file_path") or "").strip()
                for item in source_refs
                if str(item.get("source_path") or item.get("path") or item.get("file_path") or "").strip()
            }
        )
        registry[project_key] = {
            "project_id": project_key,
            "indexed_paths": indexed_paths,
            "source_count": len(source_refs),
            "source_refs": source_refs,
        }
        self._save_registry(registry)
        if not self.enabled:
            return {
                "project_id": project_key,
                "enabled": False,
                "synced": False,
                "source_count": len(source_refs),
                "indexed_paths": indexed_paths,
                "sync_status": "disabled",
                "warnings": ["lightrag_disabled"],
            }
        if not indexed_paths:
            return {
                "project_id": project_key,
                "enabled": True,
                "synced": False,
                "source_count": 0,
                "indexed_paths": [],
                "sync_status": "skipped",
                "warnings": [],
            }
        try:
            backend_result = await self._backend.initialize(self._kb_name, indexed_paths)
        except (TimeoutError, OSError, urllib_error.URLError) as exc:
            logger.warning("lightrag sync transient failure (will not retry): %s", exc)
            return {
                "project_id": project_key,
                "enabled": True,
                "synced": False,
                "source_count": len(source_refs),
                "indexed_paths": indexed_paths,
                "sync_status": "error",
                "warnings": [f"lightrag_sync_transient:{type(exc).__name__}:{exc}"],
            }
        except Exception as exc:
            logger.error("lightrag sync permanent failure: %s", exc)
            return {
                "project_id": project_key,
                "enabled": True,
                "synced": False,
                "source_count": len(source_refs),
                "indexed_paths": indexed_paths,
                "sync_status": "error",
                "warnings": [f"lightrag_sync_permanent:{type(exc).__name__}:{exc}"],
            }
        if not isinstance(backend_result, dict):
            backend_result = {"status": "synced" if backend_result else "submitted", "track_id": ""}
        return {
            "project_id": project_key,
            "enabled": True,
            "synced": True,
            "source_count": len(source_refs),
            "indexed_paths": indexed_paths,
            "sync_status": str((backend_result or {}).get("status") or "synced"),
            "warnings": [],
            "track_id": str((backend_result or {}).get("track_id") or ""),
        }

    async def async_retrieve_project_context(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[dict[str, Any]],
        top_k: int = DEFAULT_TOP_K,
    ) -> LightRAGRetrievalResult:
        if not self.enabled:
            return LightRAGRetrievalResult(
                query=query,
                warnings=["lightrag_disabled"],
                references=[],
                chunks=[],
                retrieval_status="unavailable",
                fallback_reason="lightrag_disabled",
            )
        sync_result = await self.async_sync_project_sources(project_id, source_refs)
        indexed_paths = list(sync_result.get("indexed_paths") or [])
        if not indexed_paths:
            return LightRAGRetrievalResult(
                query=query,
                warnings=["project_index_empty"],
                references=source_refs,
                chunks=[],
                retrieval_status="empty",
                fallback_reason="project_index_empty",
            )
        try:
            result = await self._backend.search(
                query=query,
                kb_name=self._kb_name,
                top_k=max(int(top_k or DEFAULT_TOP_K), self.config.top_k),
                file_paths=indexed_paths,
            )
        except Exception as exc:
            return LightRAGRetrievalResult(
                query=query,
                warnings=[f"lightrag_search_failed:{exc}"],
                references=source_refs,
                chunks=[],
                retrieval_status="unavailable",
                fallback_reason="lightrag_search_failed",
                metadata={"indexed_paths": indexed_paths},
            )
        if not isinstance(result, dict):
            return LightRAGRetrievalResult(
                query=query,
                warnings=["lightrag_result_invalid"],
                references=source_refs,
                chunks=[],
                retrieval_status="error",
                fallback_reason="lightrag_result_invalid",
            )
        file_to_ref = {
            str(item.get("source_path") or item.get("path") or item.get("file_path") or "").strip(): item
            for item in source_refs
            if str(item.get("source_path") or item.get("path") or item.get("file_path") or "").strip()
        }
        filtered_chunks: list[dict[str, Any]] = []
        references: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in result.get("chunks") or []:
            if not isinstance(item, dict):
                continue
            source_path = str(item.get("source") or item.get("source_path") or "").strip()
            ref = file_to_ref.get(source_path)
            if ref is None:
                continue
            chunk = dict(item)
            chunk["reference"] = ref
            filtered_chunks.append(chunk)
            source_id = str(ref.get("source_ref") or ref.get("source_id") or source_path)
            if source_id not in seen:
                references.append(ref)
                seen.add(source_id)
        warnings: list[str] = []
        warning = str(result.get("warning") or "").strip()
        if warning:
            warnings.append(warning)
        if result.get("needs_reindex"):
            warnings.append("project_index_needs_reindex")
        retrieval_status = "ready" if filtered_chunks else "empty"
        fallback_reason = "" if filtered_chunks else "project_subset_miss"
        if not filtered_chunks:
            warnings.append("project_subset_miss")
        text = "\n\n".join(
            str(item.get("text") or "").strip()
            for item in filtered_chunks
            if str(item.get("text") or "").strip()
        )
        return LightRAGRetrievalResult(
            query=query,
            text=text,
            references=references,
            chunks=filtered_chunks,
            warnings=warnings,
            retrieval_status=retrieval_status,
            fallback_reason=fallback_reason,
            metadata={"indexed_paths": indexed_paths},
        )

    def _load_registry(self) -> dict[str, Any]:
        if not self._registry_path.exists():
            return {}
        try:
            payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_registry(self, payload: dict[str, Any]) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._registry_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def get_lightrag_client(
    *,
    workspace: Path,
    enabled: bool | None = None,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
    backend: LightRAGBackendProtocol | None = None,
) -> LightRAGClientProtocol:
    config_path = path or (workspace / ".colearn" / "lightrag.json")
    config = LightRAGConfig.load(config_path, env=env)
    resolved_backend = backend
    if not config.enabled:
        raise LightRAGConfigurationError(
            f"LightRAG is required for the mainline but disabled in {config_path}."
        )
    if resolved_backend is None and config.provider == "server":
        resolved_backend = HttpLightRAGBackend(
            base_url=config.base_url,
            api_key=config.api_key,
        )
    if resolved_backend is None and config.provider == "local":
        from .local_backend import LocalLightRAGBackend
        resolved_backend = LocalLightRAGBackend()
    if resolved_backend is None and config.provider == "lightrag_hku":
        from .lightrag_hku_backend import LightRAGHKUBackend
        resolved_backend = LightRAGHKUBackend(working_root=workspace / ".colearn" / "lightrag-store")
    if enabled is False:
        raise LightRAGConfigurationError("LightRAG was explicitly disabled by the caller.")
    if resolved_backend is None:
        raise LightRAGConfigurationError(
            f"LightRAG provider '{config.provider}' is not available for {config_path}."
        )
    return LightRAGClient(
        config=config,
        path=config_path,
        workspace=workspace,
        backend=resolved_backend,
    )