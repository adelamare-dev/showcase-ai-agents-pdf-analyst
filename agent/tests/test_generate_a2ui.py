import asyncio
import json

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool

from src import dynamic_agent
from src.a2ui_validation import validate_components
from src.catalog import CATALOG_ID, CATALOG_PROMPT
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


def _generate(messages: list) -> str:
    """Call the tool body directly, bypassing LangChain's runtime injection."""
    tool = dynamic_agent.generate_a2ui
    assert isinstance(tool, StructuredTool) and tool.func is not None
    return tool.func(fake_runtime(messages))


def _run(monkeypatch, messages):
    stub = ScriptedModel([_render_call()])
    monkeypatch.setattr(dynamic_agent, "_RENDER_MODEL", stub)
    result = _generate(messages)
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
    result = _generate(messages or _history())
    return stub, json.loads(result)["a2ui_operations"]


def test_render_prompt_shows_a_valid_flat_example(monkeypatch):
    assert validate_components(dynamic_agent.RENDER_EXAMPLE) == []
    stub, _ = _run_scripted(monkeypatch, [_render_call()])
    system = stub.calls[0][0]
    assert json.dumps(dynamic_agent.RENDER_EXAMPLE) in system.content


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
        _generate(_history())
    assert len(stub.calls) == 1


def test_heading_level_written_as_h1_is_sent_as_1(monkeypatch):
    call = _render_call()
    call.tool_calls[0]["args"]["components"] = [
        {"id": "root", "component": "Heading", "text": "Titre", "level": "h1"}
    ]
    _, ops = _run_scripted(monkeypatch, [call])
    assert ops[1]["updateComponents"]["components"][0]["level"] == "1"


def test_invalid_optional_choice_is_not_sent_to_the_client(monkeypatch):
    # The client would replace the whole component with a visible alert.
    call = _render_call()
    call.tool_calls[0]["args"]["components"] = [
        {"id": "root", "component": "Text", "text": "Sous-titre", "weight": 1}
    ]
    _, ops = _run_scripted(monkeypatch, [call])
    assert ops[1]["updateComponents"]["components"] == [
        {"id": "root", "component": "Text", "text": "Sous-titre"}
    ]


def test_model_supplied_catalog_id_is_ignored(monkeypatch):
    call = _render_call()
    call.tool_calls[0]["args"]["catalogId"] = "https://example.invalid/other"
    _, ops = _run_scripted(monkeypatch, [call])
    assert ops[0]["createSurface"]["catalogId"] == CATALOG_ID


class _RenderLoopingModel(BaseChatModel):
    """Main agent that keeps asking for another surface, as small models do."""

    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "render-looping-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        reply = AIMessage(
            content="",
            tool_calls=[
                {"id": f"call{len(self.calls)}", "name": "generate_a2ui", "args": {}}
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _attached_question() -> HumanMessage:
    return HumanMessage(
        content=[
            {"type": "text", "text": "q"},
            {"type": "text", "text": "[Document: x.pdf]\nBODY"},
        ]
    )


def test_turn_ends_after_the_first_surface(monkeypatch):
    main_model = _RenderLoopingModel(calls=[])
    monkeypatch.setattr(dynamic_agent, "agent_chat_model", lambda _model: main_model)
    monkeypatch.setattr(
        dynamic_agent, "_RENDER_MODEL", ScriptedModel([_render_call()] * 5)
    )
    graph = dynamic_agent.build_dynamic_agent()
    result = asyncio.run(
        graph.ainvoke(
            {"messages": [_attached_question()]},
            config={"configurable": {"thread_id": "t1"}, "recursion_limit": 12},
        )
    )
    surfaces = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(main_model.calls) == 1
    assert len(surfaces) == 1


_FAILED = {
    "shape_hint": "text",
    "title": "Extraction impossible",
    "summary": "Je n'ai pas réussi à extraire ces données du document.",
    "data": "",
    "failed": True,
}


def _history_with_document(result: dict) -> list:
    history = _history()
    history[0] = HumanMessage(
        content=[
            {"type": "text", "text": "Show revenue"},
            {"type": "text", "text": "[Document: r.pdf] SECRET-BODY"},
        ]
    )
    history[2] = ToolMessage(
        content=json.dumps(result), tool_call_id="q1abcdefg", name="query_pdf"
    )
    return history


def test_failed_extraction_skips_the_render_model(monkeypatch):
    stub, ops = _run_scripted(
        monkeypatch, [_render_call()], _history_with_document(_FAILED)
    )
    assert stub.calls == []
    components = ops[1]["updateComponents"]["components"]
    texts = {c["component"]: c["text"] for c in components if "text" in c}
    assert texts["Heading"] == "Extraction impossible"
    assert texts["Text"] == _FAILED["summary"]


def test_render_model_sees_the_extraction_but_not_the_document(monkeypatch):
    result = {"shape_hint": "text", "title": "CA", "summary": "S", "data": ""}
    stub, _ = _run_scripted(
        monkeypatch, [_render_call()], _history_with_document(result)
    )
    sent = stub.calls[0]
    flat = str(sent)
    assert "SECRET-BODY" not in flat
    assert "Show revenue" in flat
    assert '"title": "CA"' in flat
    assert "LAST query_pdf result" in sent[0].content


def test_system_prompt_no_longer_asks_for_an_empty_reply():
    assert "empty string" not in dynamic_agent.SYSTEM_PROMPT
    assert '""' not in dynamic_agent.SYSTEM_PROMPT


def test_render_prompt_carries_the_layout_guide_after_the_catalog(monkeypatch):
    stub, _ = _run_scripted(monkeypatch, [_render_call()])
    prompt = stub.calls[0][0].content
    guide = dynamic_agent.RENDER_LAYOUT_GUIDE
    assert guide in prompt
    assert "`trend`" in guide and "Idée clé" in guide
    assert prompt.index(CATALOG_PROMPT) < prompt.index(guide)
    assert prompt.index(guide) < prompt.index(json.dumps(dynamic_agent.RENDER_EXAMPLE))


def test_agent_prompt_leaves_the_catalog_and_layout_to_the_render_model():
    prompt = dynamic_agent.SYSTEM_PROMPT
    assert CATALOG_PROMPT not in prompt
    assert dynamic_agent.RENDER_LAYOUT_GUIDE not in prompt
    assert "Idée clé" not in prompt
    assert "shape_hint" not in prompt
    assert "Joignez" not in prompt
    assert dynamic_agent.NO_DOCUMENT_REPLY == "Joignez un PDF et je génère la réponse."
