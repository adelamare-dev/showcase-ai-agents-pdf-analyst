import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src import dynamic_agent
from src.catalog import CATALOG_ID
from tests.fakes import ScriptedModel, fake_runtime


def _render_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "render_a2ui",
                "id": "abc123def",
                "args": {
                    "surfaceId": "s1",
                    "catalogId": CATALOG_ID,
                    "components": [
                        {"id": "root", "component": "Text", "text": "Bonjour"}
                    ],
                    "data": {"k": 1},
                },
            }
        ],
    )


def _history() -> list:
    return [
        HumanMessage(content="Show revenue"),
        AIMessage(
            content="",
            tool_calls=[{"name": "query_pdf", "id": "q1abcdefg", "args": {}}],
        ),
        ToolMessage(content="{}", tool_call_id="q1abcdefg", name="query_pdf"),
        AIMessage(
            content="",
            tool_calls=[{"name": "generate_a2ui", "id": "g1abcdefg", "args": {}}],
        ),
    ]


def _run(monkeypatch, messages):
    stub = ScriptedModel([_render_call()])
    monkeypatch.setattr(dynamic_agent, "_RENDER_MODEL", stub)
    result = dynamic_agent.generate_a2ui.func(fake_runtime(messages))
    return stub, result


def test_generate_a2ui_wraps_tool_args_into_operations(monkeypatch):
    _, result = _run(monkeypatch, _history())
    ops = json.loads(result)["a2ui_operations"]
    assert len(ops) == 3
    assert "createSurface" in ops[0]
    assert ops[0]["createSurface"]["surfaceId"] == "s1"
    assert "updateComponents" in ops[1]
    assert ops[1]["updateComponents"]["components"] == [
        {"id": "root", "component": "Text", "text": "Bonjour"}
    ]
    assert "updateDataModel" in ops[2]


def test_generate_a2ui_forces_render_tool(monkeypatch):
    stub, _ = _run(monkeypatch, _history())
    assert stub.bind_kwargs["tool_choice"] == "render_a2ui"


def test_generate_a2ui_sends_history_without_trailing_call(monkeypatch):
    history = _history()
    stub, _ = _run(monkeypatch, history)
    sent = stub.calls[0]
    assert isinstance(sent[0], SystemMessage)
    assert sent[1:] == history[:-1]
