import json

import pytest
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


def _bad_call() -> AIMessage:
    call = _render_call()
    call.tool_calls[0]["args"]["components"] = [{"id": "root", "component": "Sankey"}]
    return call


def _run_scripted(monkeypatch, responses, messages=None):
    stub = ScriptedModel(responses)
    monkeypatch.setattr(dynamic_agent, "_RENDER_MODEL", stub)
    result = dynamic_agent.generate_a2ui.func(fake_runtime(messages or _history()))
    return stub, json.loads(result)["a2ui_operations"]


def test_valid_first_try_calls_model_once(monkeypatch):
    stub, _ = _run_scripted(monkeypatch, [_render_call()])
    assert len(stub.calls) == 1


def test_invalid_then_valid_calls_model_twice(monkeypatch):
    stub, ops = _run_scripted(monkeypatch, [_bad_call(), _render_call()])
    assert len(stub.calls) == 2
    assert "Sankey" in stub.calls[1][0].content
    assert "previous render_a2ui call was rejected" in stub.calls[1][0].content
    assert ops[1]["updateComponents"]["components"][0]["text"] == "Bonjour"


def test_invalid_twice_falls_back_to_query_pdf_summary(monkeypatch):
    history = _history()
    history[2] = ToolMessage(
        name="query_pdf",
        tool_call_id="q1abcdefg",
        content='{"shape_hint":"text","title":"CA 2024","summary":"Hausse de 6 %","data":""}',
    )
    stub, ops = _run_scripted(monkeypatch, [_bad_call(), _bad_call()], history)
    assert len(stub.calls) == 2
    components = ops[1]["updateComponents"]["components"]
    texts = {c["component"]: c["text"] for c in components if "text" in c}
    assert texts["Heading"] == "CA 2024"
    assert texts["Text"] == "Hausse de 6 %"


def test_no_tool_call_retries_then_falls_back(monkeypatch):
    stub, ops = _run_scripted(
        monkeypatch, [AIMessage(content="oops"), AIMessage(content="oops")]
    )
    assert len(stub.calls) == 2
    components = ops[1]["updateComponents"]["components"]
    assert any(c["component"] == "Heading" for c in components)


def test_render_model_exception_propagates_without_retry(monkeypatch):
    stub = ScriptedModel([RuntimeError("429")])
    monkeypatch.setattr(dynamic_agent, "_RENDER_MODEL", stub)
    with pytest.raises(RuntimeError, match="429"):
        dynamic_agent.generate_a2ui.func(fake_runtime(_history()))
    assert len(stub.calls) == 1


def test_model_supplied_catalog_id_is_ignored(monkeypatch):
    call = _render_call()
    call.tool_calls[0]["args"]["catalogId"] = "https://example.invalid/other"
    _, ops = _run_scripted(monkeypatch, [call])
    assert ops[0]["createSurface"]["catalogId"] == CATALOG_ID
