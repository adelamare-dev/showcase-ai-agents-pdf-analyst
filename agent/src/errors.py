"""Turn Mistral provider failures into a short French chat reply.

Without this, a rejected key or an exhausted quota surfaces as a stack trace in
the stream and an unhandled rejection in the browser. The middleware catches
the provider exception, answers in the chat with a one-line message, and
stops the run instead of letting the model loop on the failure.

`ChatMistralAI` raises `httpx.HTTPStatusError` on any HTTP error status, while
timeouts and connection failures surface as `httpx` transport errors. Anything
else is not ours to handle and is re-raised unchanged.

Messages never carry the exception text: it can include the request URL.
Each mapped error is logged once as a warning for the operator. The log line
holds the exception class, the HTTP status and the Mistral error type and code;
it never holds request headers, the API key or a traceback.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx
from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain_core.messages import AIMessage, ToolMessage

TOOL_ERROR_PREFIX = "MISTRAL_ERROR: "

# The middleware reads only `messages`, so it adopts whatever state schema the
# other middleware of the agent declare. Bound to a fixed state instead, it
# would clash with CopilotKitMiddleware's own schema in the type checker.
StateT = TypeVar("StateT", bound=AgentState)

logger = logging.getLogger(__name__)

_QUOTA = "Quota Mistral atteint, réessayez dans un instant."
_AUTH = "Clé Mistral invalide ou absente."
_FORBIDDEN = (
    "Ce modèle Mistral n'est pas accessible avec cette clé (offre insuffisante)."
)
_TIMEOUT = "Mistral met trop de temps à répondre, réessayez."
_CONNECT = "Impossible de joindre Mistral."
_OTHER = "Mistral a renvoyé une erreur, réessayez."

_BODY_EXCERPT_CHARS = 200


def french_error_message(exc: BaseException) -> str | None:
    """Return a user-facing French message, or None if `exc` is not ours."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return _QUOTA
        if status == 401:
            return _AUTH
        if status == 403:
            return _FORBIDDEN
        return _OTHER
    if isinstance(exc, httpx.TimeoutException):
        return _TIMEOUT
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return _CONNECT
    return None


class MistralErrorMiddleware(AgentMiddleware[StateT]):
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
            message = _mapped_message(exc)
            if message is None:
                raise
            return AIMessage(content=message)

    async def awrap_model_call(
        self, request: Any, handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        try:
            return await handler(request)
        except Exception as exc:
            message = _mapped_message(exc)
            if message is None:
                raise
            return AIMessage(content=message)

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        try:
            return handler(request)
        except Exception as exc:
            message = _mapped_message(exc)
            if message is None:
                raise
            return _tool_error(request, message)

    async def awrap_tool_call(
        self, request: Any, handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        try:
            return await handler(request)
        except Exception as exc:
            message = _mapped_message(exc)
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


def _mapped_message(exc: Exception) -> str | None:
    """Map `exc` to a French reply and log it once; None if it is not ours."""
    message = french_error_message(exc)
    if message is not None:
        _log_mapped_error(exc)
    return message


def _log_mapped_error(exc: BaseException) -> None:
    status = None
    detail = ""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = _provider_detail(exc.response)
    logger.warning(
        "Mapped Mistral error: %s status=%s%s",
        type(exc).__name__,
        status,
        f" {detail}" if detail else "",
    )


def _provider_detail(response: httpx.Response) -> str:
    """Mistral error type and code from the JSON body, else a body excerpt."""
    try:
        text = response.text
    except Exception:  # unread streamed body: logging must never fail the run
        return ""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and ("type" in payload or "code" in payload):
        return f"type={payload.get('type')!r} code={payload.get('code')!r}"
    return f"body={text[:_BODY_EXCERPT_CHARS]!r}"
