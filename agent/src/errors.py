"""Turn Mistral provider failures into a short French chat reply.

Without this, a rejected key or an exhausted quota surfaces as a stack trace in
the stream and an unhandled rejection in the browser. The middleware catches
the provider exception, answers in the chat with a one-line message, and
stops the run instead of letting the model loop on the failure.

`ChatMistralAI` raises `httpx.HTTPStatusError` on any HTTP error status, while
timeouts and connection failures surface as `httpx` transport errors. Anything
else is not ours to handle and is re-raised unchanged.

Messages never carry the exception text: it can include the request URL.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, ToolMessage

TOOL_ERROR_PREFIX = "MISTRAL_ERROR: "

_QUOTA = "Quota Mistral atteint, réessayez dans un instant."
_AUTH = "Clé Mistral invalide ou absente."
_TIMEOUT = "Mistral met trop de temps à répondre, réessayez."
_CONNECT = "Impossible de joindre Mistral."
_OTHER = "Mistral a renvoyé une erreur, réessayez."


def french_error_message(exc: BaseException) -> str | None:
    """Return a user-facing French message, or None if `exc` is not ours."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return _QUOTA
        if status in (401, 403):
            return _AUTH
        return _OTHER
    if isinstance(exc, httpx.TimeoutException):
        return _TIMEOUT
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return _CONNECT
    return None


class MistralErrorMiddleware(AgentMiddleware):
    """Answer provider failures in the chat and end the run.

    Model errors become a plain assistant reply. Errors raised by the models
    used inside tools become a prefixed tool result; `before_model` then ends
    the run with the French message so the agent model is not called again and
    does not retry the tool in a loop.
    """

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        try:
            return handler(request)
        except Exception as exc:
            message = french_error_message(exc)
            if message is None:
                raise
            return AIMessage(content=message)

    async def awrap_model_call(
        self, request: Any, handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        try:
            return await handler(request)
        except Exception as exc:
            message = french_error_message(exc)
            if message is None:
                raise
            return AIMessage(content=message)

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        try:
            return handler(request)
        except Exception as exc:
            message = french_error_message(exc)
            if message is None:
                raise
            return _tool_error(request, message)

    async def awrap_tool_call(
        self, request: Any, handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        try:
            return await handler(request)
        except Exception as exc:
            message = french_error_message(exc)
            if message is None:
                raise
            return _tool_error(request, message)

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        for message in reversed(state["messages"]):
            if not isinstance(message, ToolMessage):
                return None
            content = message.content
            if isinstance(content, str) and content.startswith(TOOL_ERROR_PREFIX):
                return {
                    "jump_to": "end",
                    "messages": [AIMessage(content=content[len(TOOL_ERROR_PREFIX) :])],
                }
        return None


def _tool_error(request: Any, message: str) -> ToolMessage:
    return ToolMessage(
        content=TOOL_ERROR_PREFIX + message,
        tool_call_id=request.tool_call["id"],
    )
