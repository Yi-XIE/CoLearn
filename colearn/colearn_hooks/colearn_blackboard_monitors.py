"""Blackboard runtime monitoring hooks for CoLearn."""
import time
from typing import Any

from colearn.colearn_context import get_current_session_id, update_blackboard
from colearn.colearn_hooks.colearn_hook_base import AgentHook, AgentHookContext


class BlackboardMonitorHook(AgentHook):
    """
    Monitors agent iteration lifecycle and updates blackboard.runtime.

    This hook silently tracks runtime status without interfering with
    the main learning logic. It updates:
    - current_task_status (RUNNING / SUCCESS / FAILED)
    - last_update_ts (Unix timestamp)
    - last_observed_ip (if available in context)
    """

    def __init__(self, reraise: bool = False) -> None:
        """
        Initialize the blackboard monitor hook.

        Args:
            reraise: If True, exceptions are re-raised instead of being caught
        """
        super().__init__(reraise=reraise)

    async def before_iteration(self, context: AgentHookContext) -> None:
        """
        Called before each agent iteration starts.

        Updates:
        - current_task_status = "RUNNING"
        - last_update_ts = current timestamp
        """
        session_id = get_current_session_id()
        if not session_id:
            return

        try:
            update_blackboard("runtime", "current_task_status", "RUNNING")
        except Exception as e:
            if self._reraise:
                raise
            # Silently log and continue - don't crash the agent loop
            print(f"[BlackboardMonitor] Failed to update before_iteration: {e}")

    async def after_iteration(self, context: AgentHookContext) -> None:
        """
        Called after each agent iteration completes.

        Updates:
        - current_task_status = "SUCCESS" if no error, else "FAILED"
        - last_update_ts = current timestamp
        - last_observed_ip (if available in context)
        """
        session_id = get_current_session_id()
        if not session_id:
            return

        try:
            # Determine task status based on error state
            if context.error:
                status = "FAILED"
            elif context.stop_reason in ("end_turn", "max_tokens"):
                status = "SUCCESS"
            else:
                status = "SUCCESS"  # Default to success if completed without error

            update_blackboard("runtime", "current_task_status", status)

            # Extract IP address if available (context extension point)
            # This is a placeholder - actual IP extraction depends on host context
            ip_address = self._extract_ip_from_context(context)
            if ip_address:
                update_blackboard("runtime", "last_observed_ip", ip_address)

        except Exception as e:
            if self._reraise:
                raise
            # Silently log and continue
            print(f"[BlackboardMonitor] Failed to update after_iteration: {e}")

    def _extract_ip_from_context(self, context: AgentHookContext) -> str | None:
        """
        Extract IP address from hook context if available.

        Args:
            context: Agent hook context

        Returns:
            IP address string or None if not available
        """
        # This is a placeholder implementation
        # Actual IP extraction would depend on how the host provides this info
        # For now, we return None and let the caller set it explicitly if needed
        return None
