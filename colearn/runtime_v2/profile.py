"""CoLearn v0.2 runtime profile constants."""

from __future__ import annotations

from colearn.paths import colearn_slim_config


COLEARN_NANOBOT_SLIM_CONFIG = colearn_slim_config()

# First-wave tools to keep in the mainline once CoLearn starts wiring into
# nanobot v0.2 directly. The important bit is that LightRAG stays in the core
# conversation path from day one.
DEFAULT_ENABLED_TOOLS = [
    "memory",
    "lightrag",
]

# Upstream areas we intentionally keep out of the first CoLearn-v0.2 runtime
# line. They may come back later, but they are not part of the initial product
# path.
DEFAULT_UPSTREAM_DISABLED_AREAS = [
    "channels.feishu",
    "channels.matrix",
    "channels.telegram",
    "channels.wecom",
    "channels.whatsapp",
    "channels.dingtalk",
    "pairing",
    "image_generation",
    "extra_providers",
]
