"""LightRAG adapter seam for CoLearn retrieval."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import threading
from urllib import error as urllib_error
from urllib import request as urllib_request
from typing import Any, Mapping, Protocol, runtime_checkable


DEFAULT_TOP_K = 5
DEFAULT_BASE_URL = "http://127.0.0.1:9621"


@dataclass(frozen=True)
class LightRAGRetrievalResult:
    query: str = ""
    text: str = ""
    references: list[dict[str, Any]] | None = None
    chunks: list[dict[str, Any]] | None = None
    warnings: list[str] | None = None
    retrieval_status: str = "unavailable"
    fallback_reason: str = ""
    metadata: dict[str, Any] | None = None


@runtime_checkable
class LightRAGBackendProtocol(Protocol):
    async def initialize(self, kb_name: str, file_paths: list[str], **kwargs: Any) -> Any: ...

    async def delete(self, kb_name: str) -> Any: ...

    async def search(self, **kwargs: Any) -> dict[str, Any]: ...


@runtime_checkable
class LightRAGClientProtocol(Protocol):
    enabled: bool

    def reload(self, *, env: Mapping[str, str] | None = None) -> Any: ...

    def save(self) -> Path: ...

    def sync_project_sources(
        self,
        project_id: str,
        source_refs: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    def retrieve_project_context(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[dict[str, Any]],
        top_k: int = DEFAULT_TOP_K,
    ) -> LightRAGRetrievalResult: ...


@dataclass(slots=True)
class LightRAGConfig:
    enabled: bool = False
    provider: str = "server"
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    top_k: int = DEFAULT_TOP_K

    @classmethod
    def load(
        cls,
        path: Path | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> "LightRAGConfig":
        payload: dict[str, Any] = {}
        if path and path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        env_values = dict(env or {})
        provider_block = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
        enabled = bool(payload.get("enabled", False))
        if "LIGHTRAG_ENABLED" in env_values:
            enabled = str(env_values["LIGHTRAG_ENABLED"]).strip().lower() in {"1", "true", "yes", "on"}
        return cls(
            enabled=enabled,
            provider=str(provider_block.get("name") or payload.get("provider_name") or "server").strip() or "server",
            api_key=str(provider_block.get("api_key") or env_values.get("LIGHTRAG_API_KEY") or "").strip(),
            base_url=str(provider_block.get("base_url") or env_values.get("LIGHTRAG_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/"),
            top_k=int(payload.get("top_k") or env_values.get("LIGHTRAG_TOP_K") or DEFAULT_TOP_K),
        )

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "enabled": self.enabled,
                    "provider": {
                        "name": self.provider,
                        "api_key": self.api_key,
                        "base_url": self.base_url,
                    },
                    "top_k": self.top_k,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path


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


class HttpLightRAGBackend:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout: int = 30,
        poll_interval: float = 0.5,
        poll_attempts: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_attempts = poll_attempts

    async def initialize(self, kb_name: str, file_paths: list[str], **kwargs: Any) -> Any:
        _ = kb_name
        file_sources = list(file_paths)
        texts: list[str] = []
        valid_sources: list[str] = []
        for file_path in file_sources:
            candidate = Path(file_path)
            if not candidate.exists():
                continue
            try:
                text = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if not text.strip():
                continue
            texts.append(text)
            valid_sources.append(str(candidate))
        if not texts:
            return {"status": "skipped", "track_id": "", "indexed_paths": []}
        payload = {"texts": texts, "file_sources": valid_sources}
        response = await self._request_json("POST", "/documents/texts", payload=payload)
        track_id = str(response.get("track_id") or "").strip()
        if track_id:
            await self._wait_for_track(track_id)
        return {
            "status": str(response.get("status") or "submitted"),
            "track_id": track_id,
            "indexed_paths": valid_sources,
        }

    async def delete(self, kb_name: str) -> Any:
        _ = kb_name
        return {"status": "noop"}

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        query = str(kwargs.get("query") or "").strip()
        top_k = int(kwargs.get("top_k") or DEFAULT_TOP_K)
        file_paths = {str(item).strip() for item in (kwargs.get("file_paths") or []) if str(item).strip()}
        payload = {
            "query": query,
            "mode": "mix",
            "top_k": top_k,
            "chunk_top_k": max(top_k, 10),
            "include_references": True,
            "include_chunk_content": True,
        }
        response = await self._request_json("POST", "/query/data", payload=payload)
        data = response.get("data") if isinstance(response, dict) else {}
        references = data.get("references") if isinstance(data, dict) else []
        chunks = data.get("chunks") if isinstance(data, dict) else []
        ref_by_id = {
            str(item.get("reference_id") or ""): item
            for item in references or []
            if isinstance(item, dict)
        }
        filtered_chunks: list[dict[str, Any]] = []
        for item in chunks or []:
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("file_path") or "").strip()
            if file_paths and file_path not in file_paths:
                continue
            ref = ref_by_id.get(str(item.get("reference_id") or "").strip(), {})
            filtered_chunks.append(
                {
                    "source": file_path,
                    "source_path": file_path,
                    "text": str(item.get("content") or "").strip(),
                    "chunk_id": item.get("chunk_id"),
                    "reference_id": item.get("reference_id"),
                    "score": None,
                    "reference": ref,
                }
            )
        return {
            "chunks": filtered_chunks,
            "references": references,
            "status": str(response.get("status") or ""),
            "message": str(response.get("message") or ""),
        }

    async def _wait_for_track(self, track_id: str) -> dict[str, Any]:
        last_payload: dict[str, Any] = {}
        for _ in range(self.poll_attempts):
            payload = await self._request_json("GET", f"/documents/track_status/{track_id}")
            last_payload = payload if isinstance(payload, dict) else {}
            documents = list(last_payload.get("documents") or [])
            if documents and all(str(doc.get("status") or "").upper() == "PROCESSED" for doc in documents):
                return last_payload
            if documents and any(str(doc.get("status") or "").upper() == "FAILED" for doc in documents):
                return last_payload
            await asyncio.sleep(self.poll_interval)
        return last_payload

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_json_sync, method, path, payload)

    def _request_json_sync(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with urllib_request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"LightRAG HTTP {exc.code}: {detail or exc.reason}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"LightRAG unavailable: {exc.reason}") from exc
        if not body.strip():
            return {}
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {}


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

    def sync_project_sources(
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
            backend_result = self._run_async(self._backend.initialize(self._kb_name, indexed_paths))
        except Exception as exc:
            return {
                "project_id": project_key,
                "enabled": True,
                "synced": False,
                "source_count": len(source_refs),
                "indexed_paths": indexed_paths,
                "sync_status": "error",
                "warnings": [f"lightrag_sync_failed:{exc}"],
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

    def retrieve_project_context(
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
        sync_result = self.sync_project_sources(project_id, source_refs)
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
            result = self._run_async(
                self._backend.search(
                    query=query,
                    kb_name=self._kb_name,
                    top_k=max(int(top_k or DEFAULT_TOP_K), self.config.top_k),
                    file_paths=indexed_paths,
                )
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

    def _run_async(self, awaitable: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        result: dict[str, Any] = {}
        errors: list[BaseException] = []

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(awaitable)
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if errors:
            raise errors[0]
        return result.get("value")

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
    if resolved_backend is None and config.enabled and config.provider == "server":
        resolved_backend = HttpLightRAGBackend(
            base_url=config.base_url,
            api_key=config.api_key,
        )
    if enabled is False or not config.enabled or resolved_backend is None:
        return NoOpLightRAGClient(path=config_path)
    return LightRAGClient(
        config=config,
        path=config_path,
        workspace=workspace,
        backend=resolved_backend,
    )


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TOP_K",
    "HttpLightRAGBackend",
    "LightRAGClient",
    "LightRAGClientProtocol",
    "LightRAGConfig",
    "LightRAGRetrievalResult",
    "NoOpLightRAGClient",
    "get_lightrag_client",
]
