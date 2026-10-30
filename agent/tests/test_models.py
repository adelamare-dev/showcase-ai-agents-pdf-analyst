import asyncio
import contextlib
import json
from typing import Any

import httpx
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langchain_mistralai import ChatMistralAI

from src import dynamic_agent, pdf_tools
from src.models import (
    AGENT_MODEL,
    EXTRACTOR_MODEL,
    REQUEST_TIMEOUT_S,
    RENDER_MODEL,
    agent_chat_model,
    chat_model,
)


def test_chat_model_pins_mistral_params():
    m = chat_model(RENDER_MODEL)
    assert isinstance(m, ChatMistralAI)
    assert m.model == "ministral-8b-2512"
    assert m.temperature == 0
    assert m.max_retries == 1
    assert REQUEST_TIMEOUT_S == 45
    assert m.timeout == REQUEST_TIMEOUT_S


def test_agent_model_is_ministral_3b():
    assert AGENT_MODEL == "ministral-3b-2512"


def test_call_sites_use_expected_models():
    assert dynamic_agent._RENDER_MODEL.model == "ministral-8b-2512"
    assert pdf_tools._EXTRACTOR.model == "ministral-8b-2512"


def test_no_latest_alias():
    for model_id in (AGENT_MODEL, EXTRACTOR_MODEL, RENDER_MODEL):
        assert "latest" not in model_id


def _recording_model(factory) -> tuple[ChatMistralAI, list[dict]]:
    """A real model whose HTTP clients record each request body and never leave the process."""
    bodies: list[dict] = []
    completion = {
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

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=completion)

    model = factory()
    model.client = httpx.Client(
        base_url="https://api.mistral.ai/v1", transport=httpx.MockTransport(handler)
    )
    model.async_client = httpx.AsyncClient(
        base_url="https://api.mistral.ai/v1", transport=httpx.MockTransport(handler)
    )
    return model, bodies


@tool
def _ping_tool(question: str) -> str:
    """Answer a question."""
    return question


def test_agent_model_requests_sequential_tool_calls():
    model, bodies = _recording_model(agent_chat_model)
    bound = model.bind_tools([_ping_tool])

    bound.invoke("ping")
    asyncio.run(bound.ainvoke("ping"))

    assert len(bodies) == 2
    for body in bodies:
        assert body["parallel_tool_calls"] is False
        assert body["tools"]


def test_agent_model_requests_sequential_tool_calls_when_streaming():
    model, bodies = _recording_model(agent_chat_model)

    async def drain() -> None:
        async for _ in model.bind_tools([_ping_tool]).astream("ping"):
            pass

    with contextlib.suppress(Exception):
        asyncio.run(drain())

    assert bodies and bodies[0]["parallel_tool_calls"] is False


def test_plain_chat_model_leaves_parallel_tool_calls_alone():
    model, bodies = _recording_model(lambda: chat_model(RENDER_MODEL))

    model.invoke("ping")

    assert "parallel_tool_calls" not in bodies[0]


def test_extractor_is_not_streamed():
    assert EXTRACTOR_MODEL == "ministral-8b-2512"
    assert pdf_tools._EXTRACTOR.disable_streaming is True
    assert chat_model(RENDER_MODEL).disable_streaming is False


def _streaming_model(disable_streaming: bool) -> ChatMistralAI:
    """A real model on a mock transport that answers both plain and SSE requests."""
    completion = {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": EXTRACTOR_MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "pong"},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    chunk = {
        **completion,
        "object": "chat.completion.chunk",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "delta": {"role": "assistant", "content": "pong"},
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content).get("stream"):
            body = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"
            return httpx.Response(
                200, content=body, headers={"content-type": "text/event-stream"}
            )
        return httpx.Response(200, json=completion)

    model = chat_model(EXTRACTOR_MODEL, disable_streaming=disable_streaming)
    model.client = httpx.Client(
        base_url="https://api.mistral.ai/v1", transport=httpx.MockTransport(handler)
    )
    model.async_client = httpx.AsyncClient(
        base_url="https://api.mistral.ai/v1", transport=httpx.MockTransport(handler)
    )
    return model


def _stream_events_of_a_nested_invoke(model: ChatMistralAI) -> tuple[int, str]:
    """Count `on_chat_model_stream` events when a tool-like function calls `invoke`."""
    inner = RunnableLambda(lambda _: model.invoke("ping").text)

    async def play() -> tuple[int, str]:
        count, output = 0, ""
        async for raw_event in inner.astream_events("go", version="v2"):
            event: Any = raw_event
            if event["event"] == "on_chat_model_stream":
                count += 1
            if event["event"] == "on_chain_end" and not event["parent_ids"]:
                output = event["data"]["output"]
        return count, output

    return asyncio.run(play())


def test_invoke_inside_a_tool_streams_nothing_when_streaming_is_disabled():
    count, output = _stream_events_of_a_nested_invoke(_streaming_model(True))
    assert (count, output) == (0, "pong")


def test_invoke_inside_a_tool_leaks_stream_events_without_the_setting():
    count, _ = _stream_events_of_a_nested_invoke(_streaming_model(False))
    assert count >= 1
