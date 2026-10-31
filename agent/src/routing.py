"""Imposed tool routing shared by the agent graphs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain_core.messages import AIMessage, AnyMessage

from src.pdf_tools import latest_document_text

# Adopts the state schema of the other middleware, as `MistralErrorMiddleware`
# does, to stay in the same `middleware=[...]` list for the type checker.
StateT = TypeVar("StateT", bound=AgentState)


class PdfTurnRoutingMiddleware(AgentMiddleware[StateT]):
    """Decide the tool of each model call instead of leaving it to the model.

    `required_tool(messages)` returns the tool's name to impose as the
    `tool_choice` of the next model call, or None to leave the request
    untouched. On the dynamic graph a turn has a single valid course,
    `query_pdf` then `generate_a2ui`; on the fixed graph the first turn on a
    document always renders the dashboard. Left to choose, a small model
    sometimes answers with an empty message without calling a tool or calls
    `query_pdf` in a loop, and a booby-trapped document could push it there.

    Without a document there is nothing to read: the turn ends on
    `no_document_reply` without any model call, which also keeps the model
    from inventing a document to talk about.
    """

    def __init__(
        self,
        required_tool: Callable[[list[AnyMessage]], str | None],
        no_document_reply: str,
    ):
        super().__init__()
        self._required_tool = required_tool
        self._no_document_reply = no_document_reply

    @hook_config(can_jump_to=["end"])
    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        if latest_document_text(state["messages"]) is not None:
            return None
        return {
            "jump_to": "end",
            "messages": [AIMessage(content=self._no_document_reply)],
        }

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return handler(self._routed(request))

    async def awrap_model_call(
        self, request: Any, handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        return await handler(self._routed(request))

    def _routed(self, request: Any) -> Any:
        choice = self._required_tool(request.state["messages"])
        return request if choice is None else request.override(tool_choice=choice)
