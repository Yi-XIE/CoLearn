"""Retrieval adapters."""

from .lightrag_protocol import (
    DEFAULT_BASE_URL,
    DEFAULT_TOP_K,
    LightRAGBackendProtocol,
    LightRAGClientProtocol,
    LightRAGConfigurationError,
    LightRAGRetrievalResult,
)
from .lightrag_config import LightRAGConfig
from .lightrag_http import HttpLightRAGBackend
from .lightrag_client import (
    LightRAGClient,
    NoOpLightRAGClient,
    get_lightrag_client,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TOP_K",
    "HttpLightRAGBackend",
    "LightRAGClient",
    "LightRAGClientProtocol",
    "LightRAGConfig",
    "LightRAGConfigurationError",
    "LightRAGRetrievalResult",
    "get_lightrag_client",
]
