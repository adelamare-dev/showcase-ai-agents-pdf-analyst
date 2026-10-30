"""Turn length: the tool cap and the graph recursion limit, on the real graphs.

The agent models are scripted, the extractor and the render model are stubs:
nothing leaves the process. `build_dynamic_agent` and `build_fixed_agent` keep
their middlewares, so the step counts are those of production.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

import main
from scripts import measure
from src import dynamic_agent, fixed_agent, pdf_tools
from src.models import AGENT_RECURSION_LIMIT
from tests.fakes import ScriptedModel, ScriptedToolCaller
from tests.test_generate_a2ui import _render_call

ANSWER = '{"shape_hint":"text","title":"T","summary":"S","data":""}'
QUERY = ("query_pdf", {"question": "Q?"})
RENDER = ("generate_a2ui", {})
DASHBOARD = (
    "render_dashboard",
    {
        "eyebrow": "E",
        "title": "T",
        "subtitle": "S",
        "kpis": [{"label": "l", "value": "v", "delta": "", "caption": "c"}] * 4,
        "trend": [{"label": "a", "value": 1.0}],
        "share": [{"label": "a", "value": 1.0}],
        "rows": [{"name": "n", "category": "c", "value": "v", "delta": ""}],
        "scope_options": [{"label": "a", "value": "a"}],
        "scope_selected": "a",
    },
)


def _question() -> HumanMessage:
    return HumanMessage(
        content=[
            {"type": "text", "text": "Question"},
            {"type": "text", "text": "[Document: report.pdf]\nBODY"},
        ]
    )


def _dynamic_graph(monkeypatch, model: ScriptedToolCaller):
    extractor = ScriptedModel([AIMessage(content=ANSWER)] * 50)
    monkeypatch.setattr(dynamic_agent, "agent_chat_model", lambda _model: model)
    monkeypatch.setattr(
        dynamic_agent, "_RENDER_MODEL", ScriptedModel([_render_call()] * 5)
    )
    monkeypatch.setattr(pdf_tools, "_EXTRACTOR", extractor)
    return dynamic_agent.build_dynamic_agent(), extractor


def _play(graph, limit: int = AGENT_RECURSION_LIMIT) -> dict:
    # Outside AG-UI nobody fills the `copilotkit` key the middleware reads.
    return asyncio.run(
        graph.ainvoke(
            {"messages": [_question()], "copilotkit": {"actions": [], "context": []}},
            config={"configurable": {"thread_id": "t"}, "recursion_limit": limit},
        )
    )


def test_longest_allowed_turn_fits_under_the_limit(monkeypatch):
    model = ScriptedToolCaller(script=[QUERY, QUERY, RENDER])
    graph, extractor = _dynamic_graph(monkeypatch, model)

    result = _play(graph)

    assert len(extractor.calls) == 2
    assert isinstance(result["messages"][-1], ToolMessage)
    assert result["messages"][-1].name == "generate_a2ui"


def test_turn_that_recovers_from_refused_calls_fits_under_the_limit(monkeypatch):
    model = ScriptedToolCaller(script=[QUERY, QUERY, QUERY, QUERY, RENDER])
    graph, extractor = _dynamic_graph(monkeypatch, model)

    result = _play(graph)

    assert len(extractor.calls) == 2
    assert result["messages"][-1].name == "generate_a2ui"


def test_a_model_that_keeps_querying_never_reaches_the_render(monkeypatch):
    # Past the recovery above, one more refused call is already too many.
    model = ScriptedToolCaller(script=[QUERY, QUERY, QUERY, QUERY, QUERY, RENDER])
    graph, extractor = _dynamic_graph(monkeypatch, model)

    with pytest.raises(GraphRecursionError):
        _play(graph)

    assert len(extractor.calls) == 2


def test_endless_query_loop_runs_the_extractor_twice_then_hits_the_limit(monkeypatch):
    model = ScriptedToolCaller(script=[QUERY], cycle=True)
    graph, extractor = _dynamic_graph(monkeypatch, model)

    with pytest.raises(GraphRecursionError):
        _play(graph)

    assert len(extractor.calls) == 2


def test_fixed_turn_fits_under_the_limit(monkeypatch):
    model = ScriptedToolCaller(script=[DASHBOARD])
    monkeypatch.setattr(fixed_agent, "agent_chat_model", lambda _model: model)
    graph = fixed_agent.build_fixed_agent()

    result = _play(graph)

    assert any(
        isinstance(m, ToolMessage) and m.name == "render_dashboard"
        for m in result["messages"]
    )
    assert len(model.calls) == 2


def test_server_and_measure_script_use_the_shared_limit(monkeypatch):
    assert main._AGENT_CONFIG["recursion_limit"] == AGENT_RECURSION_LIMIT

    # `run_turn` is what the measure script plays turns with: it must stop a
    # turn that goes past the limit, not run it to a hard-coded larger one.
    model = ScriptedToolCaller(script=[QUERY, QUERY, QUERY, QUERY, QUERY, RENDER])
    graph, _ = _dynamic_graph(monkeypatch, model)
    with pytest.raises(GraphRecursionError):
        asyncio.run(measure.run_turn(graph, _question(), measure.CallTimer()))
