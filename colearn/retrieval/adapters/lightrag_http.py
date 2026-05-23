"""HTTP backend for LightRAG server communication."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from colearn.logging_config import get_logger

from .lightrag_protocol import DEFAULT_BASE_URL, DEFAULT_TOP_K

logger = get_logger(__name__)


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
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            logger.error("LightRAG returned invalid JSON: %s", exc)
            return {}
        return parsed if isinstance(parsed, dict) else {}