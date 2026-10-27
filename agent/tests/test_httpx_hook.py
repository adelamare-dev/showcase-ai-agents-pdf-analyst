import asyncio

import httpx
from copilotkit.copilotkit_lg_middleware import _ensure_httpx_hook
from langchain_mistralai import ChatMistralAI

from src.models import AGENT_MODEL, chat_model

_BASE_URL = "https://api.mistral.ai/v1"

_COMPLETION = {
    "id": "cmpl-1",
    "object": "chat.completion",
    "created": 0,
    "model": AGENT_MODEL,
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "pong"},
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def _offline_model() -> ChatMistralAI:
    """A real `chat_model` whose HTTP clients never leave the process."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_COMPLETION)

    base = chat_model(AGENT_MODEL)
    return ChatMistralAI(
        model=base.model,
        temperature=base.temperature,
        max_retries=0,
        client=httpx.Client(base_url=_BASE_URL, transport=httpx.MockTransport(handler)),
        async_client=httpx.AsyncClient(
            base_url=_BASE_URL, transport=httpx.MockTransport(handler)
        ),
    )


def test_async_call_survives_copilotkit_header_hook():
    """CopilotKitMiddleware installs a request hook on the model's clients.

    ChatMistralAI exposes a raw `httpx.AsyncClient`, which awaits every hook:
    a synchronous hook makes each async call fail with
    "object NoneType can't be used in 'await' expression".
    """
    model = _offline_model()
    _ensure_httpx_hook(model)

    reply = asyncio.run(model.ainvoke("ping"))

    assert reply.content == "pong"
