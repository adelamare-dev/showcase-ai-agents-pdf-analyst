"""Single home for model identifiers and client parameters.

Every Mistral client in the agent is built here so IDs and limits are changed
in one place instead of being scattered across the call sites.

Model IDs are dated snapshots, never a `-latest` alias: an alias can move to a
new model under our feet and change tool-calling behaviour without any code
change on our side.

The demo runs on Mistral's free tier, so each role uses the cheapest dated
model that supports function calling: Ministral 3 3B (`ministral-3b-2512`,
$0.10/M tokens in and out, 1.3M tokens/min on the free tier). If a role proves
unreliable in a live run, escalate only that role one step: `ministral-8b-2512`
($0.15/M), then `ministral-14b-2512` ($0.20/M). `mistral-small-2603` and
`mistral-large-2512` are not usable on this account (0 requests/min, respectively
not in the plan).

The render role has been escalated once: on 3B, follow-up questions came back
as nested component trees that failed validation twice in a row, so the user
only got the text fallback. 8B returns the flat component list.

Each call makes one attempt. LangChain's `max_retries` counts attempts
(`stop_after_attempt`), so `MAX_RETRIES = 1` means no retry, and only transport
errors are retried at all: HTTP status errors such as 429 or 5xx are never
retried. A call that is going to fail should fail fast so the user is told,
instead of watching a spinner behind silent retries. The timeout is 1.5 times
the slowest call measured with `scripts/measure.py` (30.5 s, rendering on
ministral-8b-2512, which timed out at 30 s), capped at 45 s.

Two kinds of client exist. `chat_model` builds a plain `ChatMistralAI`, used by
the render model and the extractor. `agent_chat_model` builds the client of the
two agent graphs, which re-chunks streamed tool calls so the chat can show a
step while the tool runs (see `_StreamingToolCallMistral`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_mistralai import ChatMistralAI

AGENT_MODEL = "ministral-3b-2512"
EXTRACTOR_MODEL = "ministral-3b-2512"
RENDER_MODEL = "ministral-8b-2512"

REQUEST_TIMEOUT_S = 45
MAX_RETRIES = 1

# LangGraph supersteps allowed per turn. Measured on the real dynamic graph
# (middlewares included) with scripted models: 11 for a normal turn (one
# `query_pdf` then `generate_a2ui`), 15 with two `query_pdf`, 19 with three, 23
# with four; each extra model-and-tool round costs 4 supersteps. A live run on
# an ordinary question made the model call `query_pdf` three times (its
# extractor had failed on invalid JSON), which is 19 of a former limit of 20:
# one more refusal would have cut the stream mid-turn with no message for the
# user. 24 is the 23 of the four-call turn plus one step of slack. A `/fixed`
# turn needs 10. Raise it only with a new measurement (see
# tests/test_turn_limits.py).
AGENT_RECURSION_LIMIT = 24


def chat_model(model: str) -> ChatMistralAI:
    """Build a deterministic Mistral chat client with the shared limits."""
    return ChatMistralAI(
        model_name=model,
        temperature=0,
        max_retries=MAX_RETRIES,
        timeout=REQUEST_TIMEOUT_S,
    )


class _StreamingToolCallMistral(ChatMistralAI):
    """`ChatMistralAI` that streams a tool call as start, args, end.

    Mistral delivers a tool call whole, in a single streamed chunk that also
    carries `finish_reason`. `ag_ui_langgraph` drops any chunk with a
    finish_reason and, even without that, only emits the tool-call start on
    the first chunk and the arguments on a later one. Nothing is streamed, so
    the client receives the whole call only after the tool has finished and
    the chat step appears too late.

    Each such chunk is re-yielded as: a chunk with name, id and empty args
    (call start), a chunk with the arguments only, an empty chunk (call end),
    then the original chunk minus its tool calls, keeping `finish_reason` and
    `usage_metadata`. Merged, the chunks give the same message as before.
    """

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        async for gen in super()._astream(
            messages, stop, run_manager=run_manager, **kwargs
        ):
            msg = gen.message
            if not (
                isinstance(msg, AIMessageChunk)
                and any(c.get("name") for c in msg.tool_call_chunks)
            ):
                yield gen
                continue
            for call in msg.tool_call_chunks:
                yield _chunk(
                    tool_call_chunk(
                        name=call.get("name"),
                        args="",
                        id=call.get("id"),
                        index=call.get("index"),
                    )
                )
                if call.get("args"):
                    yield _chunk(
                        tool_call_chunk(
                            name=None,
                            args=call["args"],
                            id=None,
                            index=call.get("index"),
                        )
                    )
                yield _chunk()
            rest = msg.model_copy(update={"tool_call_chunks": [], "tool_calls": []})
            yield ChatGenerationChunk(message=rest, generation_info=gen.generation_info)


def _chunk(*calls: Any) -> ChatGenerationChunk:
    return ChatGenerationChunk(
        message=AIMessageChunk(content="", tool_call_chunks=list(calls))
    )


def agent_chat_model(model: str = AGENT_MODEL) -> ChatMistralAI:
    """Build the agent graphs' client: `chat_model` with tool calls re-chunked.

    Use it for the model passed to `create_agent` only. The render model must
    stay a plain `chat_model`: its inner tool call would otherwise stream to
    the client as a tool call of its own.

    Tool calls are requested one at a time (`parallel_tool_calls: false`, a
    documented Mistral chat-completions parameter). A single model message once
    carried two `generate_a2ui` calls, which rendered two surfaces and two chat
    steps for one turn, and `return_direct` only stops the graph after the whole
    batch of calls has run.
    """
    return _StreamingToolCallMistral(
        model_name=model,
        temperature=0,
        max_retries=MAX_RETRIES,
        timeout=REQUEST_TIMEOUT_S,
        model_kwargs={"parallel_tool_calls": False},
    )
