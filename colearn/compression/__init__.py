"""Compression bridges for runtime and product layers."""

from .product import ProductCompressionBridge, ProductCompressionResult
from .runtime import RuntimeCompressionBridge, RuntimeCompressionResult

__all__ = [
    "ProductCompressionBridge",
    "ProductCompressionResult",
    "RuntimeCompressionBridge",
    "RuntimeCompressionResult",
]
