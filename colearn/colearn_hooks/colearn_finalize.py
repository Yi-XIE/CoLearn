"""Finalize hook for light CoLearn response cleanup."""
from __future__ import annotations

from colearn.colearn_board.colearn_writeback import BlackboardWriter
from colearn.colearn_context import get_session, save_session
from colearn.colearn_hooks.colearn_hook_base import AgentHook, AgentHookContext


class CoLearnFinalizeHook(AgentHook):
    """A light hook reserved for final content normalization.

    Learning truth is written through blackboard writeback, not this content hook.
    """

    def __init__(
        self,
        writer: BlackboardWriter | None = None,
        reraise: bool = False,
    ) -> None:
        super().__init__(reraise=reraise)
        self.writer = writer or BlackboardWriter()

    def finalize_content(self, context: AgentHookContext, content: str | None) -> str | None:
        return content

    async def after_iteration(self, context: AgentHookContext) -> None:
        try:
            session = get_session()
            if session is None or not session.blackboard.learning.goal:
                return

            final_text = (context.final_content or "").strip()
            turn_result = {
                "continuation": final_text[:280] if final_text else "继续当前学习路径。",
            }
            if context.stop_reason == "end_turn":
                turn_result["current_progress"] = "本轮已完成一次学习响应。"
            self.writer.update_learning_state(session, turn_result)
            save_session(session)
        except Exception:
            if self._reraise:
                raise
