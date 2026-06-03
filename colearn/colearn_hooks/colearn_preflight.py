"""Preflight hook for mode decisions and learning context injection."""
from __future__ import annotations

from colearn.colearn_adapters.colearn_messages import append_system_context
from colearn.colearn_board.colearn_context_builder import ContextBuilder
from colearn.colearn_hooks.colearn_hook_base import AgentHook, AgentHookContext
from colearn.colearn_context import get_session
from colearn.colearn_learning_logic.colearn_mode_router import ModeRouter
from colearn.colearn_learning_logic.colearn_session_mode import SessionMode


class CoLearnPreflightHook(AgentHook):
    """Decide CHAT/LEARNING mode before a turn and prepare context payload."""

    def __init__(self, context_builder: ContextBuilder | None = None, reraise: bool = False) -> None:
        super().__init__(reraise=reraise)
        self.context_builder = context_builder or ContextBuilder()

    async def before_iteration(self, context: AgentHookContext) -> None:
        try:
            session = get_session()
            if session is None:
                return
            router = ModeRouter(session.to_dict())
            mode = router.decide_session_mode()
            setattr(context, "colearn_session_mode", mode.value)
            turn_mode = router.decide_turn_mode()
            setattr(context, "colearn_turn_mode", turn_mode.value if turn_mode else None)
            if mode == SessionMode.LEARNING:
                payload = self.context_builder.build_learning_context(session)
                if payload:
                    setattr(context, "colearn_learning_context", payload)
                    append_system_context(context, payload)
        except Exception:
            if self._reraise:
                raise
