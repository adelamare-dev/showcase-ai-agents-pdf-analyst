from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage


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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def invoke(self, messages, *args, **kwargs) -> AIMessage:
        return self._next(messages)

    async def ainvoke(self, messages, *args, **kwargs) -> AIMessage:
        return self._next(messages)


def fake_runtime(messages: list, context: list[dict] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        state={"messages": messages, "copilotkit": {"context": context or []}}
    )
