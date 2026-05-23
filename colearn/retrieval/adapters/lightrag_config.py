"""LightRAG configuration dataclass."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .lightrag_protocol import DEFAULT_BASE_URL, DEFAULT_TOP_K


@dataclass(slots=True)
class LightRAGConfig:
    enabled: bool = False
    provider: str = "local"
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
            provider=str(provider_block.get("name") or payload.get("provider_name") or "local").strip() or "local",
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
