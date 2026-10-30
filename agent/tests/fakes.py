from __future__ import annotations

from types import SimpleNamespace

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedModel:
    """Stand-in chat model that replays scripted responses in order."""

    def __init__(self, responses: list[AIMessage | Exception]):
        self.responses = list(responses)
        self.calls: list = []
        self.bind_kwargs: dict = {}

    def bind_tools(self, tools, **kwargs) -> "ScriptedModel":
        self.bind_kwargs = kwargs
        return self

    def _next(self, messages) -> AIMessage:
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("no scripted response left")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def invoke(self, messages, *args, **kwargs) -> AIMessage:
        return self._next(messages)

    async def ainvoke(self, messages, *args, **kwargs) -> AIMessage:
        return self._next(messages)


def fake_runtime(
    messages: list,
    context: list[dict] | None = None,
    tool_call_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        state={"messages": messages, "copilotkit": {"context": context or []}},
        tool_call_id=tool_call_id,
    )


class ScriptedToolCaller(BaseChatModel):
    """Agent model that requests one scripted tool call per message.

    Each reply carries a single call with a fresh id. Once the script is spent
    the model answers with an empty message, which ends the turn; with `cycle`
    it starts over instead, as a model stuck in a loop would.
    """

    script: list[tuple[str, dict]]
    cycle: bool = False
    calls: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-caller"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        index = len(self.calls)
        self.calls.append(messages)
        if self.cycle:
            index %= len(self.script)
        if index < len(self.script):
            name, args = self.script[index]
            reply = AIMessage(
                content="",
                tool_calls=[
                    {"id": f"call{len(self.calls)}", "name": name, "args": args}
                ],
            )
        else:
            reply = AIMessage(content="")
        return ChatResult(generations=[ChatGeneration(message=reply)])
