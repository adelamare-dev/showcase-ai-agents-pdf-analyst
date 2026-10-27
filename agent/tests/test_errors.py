import asyncio
from types import SimpleNamespace

import httpx
import pytest
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from src.errors import TOOL_ERROR_PREFIX, MistralErrorMiddleware, french_error_message

API_URL = "https://api.mistral.ai/v1/chat/completions"


def status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", API_URL)
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(
        f"Client error '{code}' for url '{API_URL}'", request=request, response=response
    )


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (status_error(429), "Quota Mistral"),
        (status_error(401), "Clé Mistral"),
        (status_error(403), "Clé Mistral"),
        (status_error(500), "erreur"),
        (httpx.ReadTimeout("slow"), "trop de temps"),
        (httpx.ConnectError("down"), "joindre"),
    ],
)
def test_french_error_message(exc, expected):
    message = french_error_message(exc)
    assert message and expected in message
    for leak in ("test-key", "Traceback", "api.mistral.ai", "http"):
        assert leak not in message


def test_unrelated_error_has_no_message():
    assert french_error_message(ValueError("x")) is None


def model_request():
    return SimpleNamespace(messages=[HumanMessage(content="hi")])


def test_model_error_becomes_french_reply():
    def handler(request):
        raise status_error(429)

    reply = MistralErrorMiddleware().wrap_model_call(model_request(), handler)
    assert isinstance(reply, AIMessage)
    assert not reply.tool_calls
    assert reply.content == french_error_message(status_error(429))


def test_async_model_error_becomes_french_reply():
    async def handler(request):
        raise status_error(429)

    reply = asyncio.run(
        MistralErrorMiddleware().awrap_model_call(model_request(), handler)
    )
    assert isinstance(reply, AIMessage)
    assert not reply.tool_calls
    assert reply.content == french_error_message(status_error(429))


def test_model_success_is_passed_through():
    ok = AIMessage(content="fine")
    assert MistralErrorMiddleware().wrap_model_call(model_request(), lambda r: ok) is ok


def test_unmapped_model_error_is_reraised():
    def handler(request):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        MistralErrorMiddleware().wrap_model_call(model_request(), handler)


def test_async_unmapped_model_error_is_reraised():
    async def handler(request):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        asyncio.run(MistralErrorMiddleware().awrap_model_call(model_request(), handler))


def tool_request():
    return SimpleNamespace(tool_call={"id": "call1", "name": "query_pdf", "args": {}})


def test_tool_error_returns_french_message_and_stops():
    def handler(request):
        raise status_error(429)

    middleware = MistralErrorMiddleware()
    tool_message = middleware.wrap_tool_call(tool_request(), handler)
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.tool_call_id == "call1"
    assert tool_message.content.startswith(TOOL_ERROR_PREFIX)

    state = {
        "messages": [
            HumanMessage(content="q"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call1", "name": "query_pdf", "args": {}}],
            ),
            tool_message,
        ]
    }
    update = middleware.before_model(state, SimpleNamespace())
    assert update["jump_to"] == "end"
    (final,) = update["messages"]
    assert isinstance(final, AIMessage)
    assert final.content == french_error_message(status_error(429))
    assert TOOL_ERROR_PREFIX not in final.content


def test_async_tool_error_returns_prefixed_message():
    async def handler(request):
        raise status_error(401)

    tool_message = asyncio.run(
        MistralErrorMiddleware().awrap_tool_call(tool_request(), handler)
    )
    assert tool_message.tool_call_id == "call1"
    assert tool_message.content.startswith(TOOL_ERROR_PREFIX)


def test_unmapped_tool_error_is_reraised():
    def handler(request):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        MistralErrorMiddleware().wrap_tool_call(tool_request(), handler)


def test_before_model_ignores_ordinary_tool_results():
    state = {
        "messages": [
            HumanMessage(content="q"),
            AIMessage(content="", tool_calls=[]),
            ToolMessage(content="{}", tool_call_id="call1"),
        ]
    }
    assert MistralErrorMiddleware().before_model(state, SimpleNamespace()) is None


def test_before_model_ignores_error_from_an_earlier_turn():
    state = {
        "messages": [
            ToolMessage(content=TOOL_ERROR_PREFIX + "x", tool_call_id="old"),
            AIMessage(content="x"),
            HumanMessage(content="new question"),
        ]
    }
    assert MistralErrorMiddleware().before_model(state, SimpleNamespace()) is None


class _ToolCallingModel(BaseChatModel):
    """Always asks for the same tool; counts how often it is consulted."""

    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "tool-calling-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        reply = AIMessage(
            content="",
            tool_calls=[{"id": "call1", "name": "failing_tool", "args": {}}],
        )
        return ChatResult(generations=[ChatGeneration(message=reply)])


@tool
def failing_tool() -> str:
    """Always fails the way a rejected provider call does."""
    raise status_error(429)


def test_tool_provider_error_ends_the_run_without_calling_the_model_again():
    model = _ToolCallingModel(calls=[])
    graph = create_agent(
        model=model, tools=[failing_tool], middleware=[MistralErrorMiddleware()]
    )
    result = asyncio.run(graph.ainvoke({"messages": [HumanMessage(content="q")]}))
    assert len(model.calls) == 1
    assert result["messages"][-1].content == french_error_message(status_error(429))
