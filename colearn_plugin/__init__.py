"""CoLearn Learning Plugin for nanobot.

This plugin decouples CoLearn's learning logic from nanobot's core runtime,
making it maintainable across nanobot version upgrades.

Architecture:
    - LearningPlugin: Main entry point (nanobot plugin protocol)
    - LearningHook: Lifecycle hooks for 5-stage pipeline
    - LearningStateManager: Isolated state management
    - Learning Tools: MCP-compatible tools for learning events
"""

__version__ = "0.1.0"

from .plugin import CoLearnPlugin

__all__ = ["CoLearnPlugin"]
