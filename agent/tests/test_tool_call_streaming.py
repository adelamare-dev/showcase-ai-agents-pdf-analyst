import asyncio
import json

import httpx
from langchain_core.messages import AIMessageChunk
from langchain_mistralai import ChatMistralAI

from src import dynamic_agent, fixed_agent, pdf_tools
from src.models import AGENT_MODEL, agent_chat_model, chat_model

_BASE_URL = "https://api.mistral.ai/v1"


def _event(delta: dict, finish_reason=None, usage=None) -> str:
    body = {
        "id": "cmpl-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": AGENT_MODEL,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage:
        body["usage"] = usage
    return f"data: {json.dumps(body)}\n\n"


# Mistral sends a tool call whole, in one chunk that also carries finish_reason.
_SSE = (
    _event({"role": "assistant", "content": ""})
    + _event(
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "bfUxBacgy",
                    "index": 0,
                    "type": "function",
                    "function": {"name": "query_pdf", "arguments": '{"question": "q"}'},
                }
            ],
        },
        finish_reason="tool_calls",
        usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    )
    + "data: [DONE]\n\n"
)


def _clients() -> dict:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_SSE, headers={"content-type": "text/event-stream"}
        )

    return {
        "client": httpx.Client(
            base_url=_BASE_URL, transport=httpx.MockTransport(handler)
        ),
        "async_client": httpx.AsyncClient(
            base_url=_BASE_URL, transport=httpx.MockTransport(handler)
        ),
    }


def _offline(cls=ChatMistralAI):
    return cls(model_name=AGENT_MODEL, temperature=0, max_retries=0, **_clients())


def _adapted_class():
    return type(agent_chat_model())


async def _collect(model) -> list[AIMessageChunk]:
    return [c async for c in model.astream("ping")]


def _merge(chunks):
    merged = chunks[0]
    for c in chunks[1:]:
        merged = merged + c
    return merged


def test_tool_call_is_split_into_start_args_end_then_finish():
    chunks = asyncio.run(_collect(_offline(_adapted_class())))

    with_tool = [c for c in chunks if c.tool_call_chunks]
    assert len(with_tool) == 2
    start, args = with_tool
    assert start.tool_call_chunks[0]["name"] == "query_pdf"
    assert start.tool_call_chunks[0]["id"] == "bfUxBacgy"
    assert start.tool_call_chunks[0]["args"] == ""
    assert args.tool_call_chunks[0]["name"] is None
    assert args.tool_call_chunks[0]["id"] is None
    assert args.tool_call_chunks[0]["index"] == start.tool_call_chunks[0]["index"]
    assert args.tool_call_chunks[0]["args"] == '{"question": "q"}'

    # An empty chunk without tool data closes the call before the finish chunk.
    after_args = chunks[chunks.index(args) + 1 :]
    assert after_args[0].tool_call_chunks == [] and not after_args[0].content
    assert "finish_reason" not in after_args[0].response_metadata

    # finish_reason appears once, after the args chunk (the framework may
    # append one more empty chunk behind it).
    carrying = [c for c in chunks if "finish_reason" in c.response_metadata]
    assert len(carrying) == 1
    assert carrying[0].response_metadata["finish_reason"] == "tool_calls"
    assert chunks.index(args) < chunks.index(carrying[0])
    assert carrying[0].tool_call_chunks == []


def test_merged_message_matches_the_unadapted_one():
    plain = _merge(asyncio.run(_collect(_offline())))
    adapted = _merge(asyncio.run(_collect(_offline(_adapted_class()))))

    assert adapted.tool_calls == plain.tool_calls
    assert adapted.tool_calls[0]["name"] == "query_pdf"
    assert adapted.response_metadata["finish_reason"] == "tool_calls"
    assert adapted.usage_metadata == plain.usage_metadata
    assert adapted.usage_metadata is not None
    assert adapted.usage_metadata["total_tokens"] == 7


def test_only_the_agent_model_is_adapted():
    adapted = _adapted_class()
    assert adapted is not ChatMistralAI and issubclass(adapted, ChatMistralAI)
    assert type(chat_model(AGENT_MODEL)) is ChatMistralAI
    assert type(dynamic_agent._RENDER_MODEL) is ChatMistralAI
    assert type(pdf_tools._EXTRACTOR) is ChatMistralAI


def test_agent_graphs_use_the_adapted_model(monkeypatch):
    for module, build in (
        (fixed_agent, fixed_agent.build_fixed_agent),
        (dynamic_agent, dynamic_agent.build_dynamic_agent),
    ):
        seen = {}

        def fake_create_agent(**kwargs):
            seen.update(kwargs)

        monkeypatch.setattr(module, "create_agent", fake_create_agent)
        build()
        assert type(seen["model"]) is _adapted_class()
