"""The /fixed dashboard is filled by the extractor and checked against the document.

The tool is called with a fake runtime and a scripted extractor; its output (the
A2UI operations) is inspected, so the surface and the data model are checked
together. The checks themselves are tested in `test_dashboard_checks.py`.
"""

import copy
import json
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool

from src import fixed_agent, pdf_tools
from src.fixed_agent import _dashboard_components
from src.locale import FRENCH_OUTPUT_RULE
from tests.fakes import ScriptedModel, fake_runtime

DOCUMENT = (
    "[Document: insee.pdf]\n"
    "2025T3 | 2025T4 | 2026T1 | 2026T2 | 2025 | 2026 (acquis)\n"
    "PIB | 0,4 | 0,3 | -0,2 | 0,0 | 0,9 | 0,3\n"
    "Dép. conso. ménages | 0,1 | 0,2 | -0,3 | 0,3 | 0,5 | 0,1\n"
    "Parts | 30 | 40 | 60 | 10 | 20\n"
)

KPI = {"label": "PIB", "value": "0,4 %", "delta": "+0,3 %", "caption": "T3"}
ROW = {"name": "Conso", "category": "Demande", "value": "+0,3 %", "delta": "+0,5 %"}
TREND = [
    {"label": "2025T3", "value": 0.4},
    {"label": "2025T4", "value": 0.3},
    {"label": "2026T1", "value": -0.2},
    {"label": "2026T2", "value": 0.0},
]
SHARE = [{"label": "a", "value": 30}, {"label": "b", "value": 40}]
SCOPE = [{"label": "Tout", "value": "all"}, {"label": "Ménages", "value": "hh"}]
ANSWER = {
    "eyebrow": "INSEE",
    "title": "Note de conjoncture",
    "subtitle": "Résumé",
    "kpis": [KPI],
    "trend": TREND,
    "share": SHARE,
    "rows": [ROW],
    "scope_options": SCOPE,
    "scope_selected": "hh",
}


def _message(text: str = DOCUMENT) -> HumanMessage:
    return HumanMessage(content=[{"type": "text", "text": text}])


def _tool() -> StructuredTool:
    tool = fixed_agent.render_dashboard
    assert isinstance(tool, StructuredTool) and tool.func is not None
    return tool


def _call(messages: list, focus: str = "tout") -> str:
    assert _tool().func is not None
    return _tool().func(focus=focus, runtime=fake_runtime(messages))  # type: ignore[call-arg]


def _extractor(monkeypatch, answer: Any) -> ScriptedModel:
    content = answer if isinstance(answer, str) else json.dumps(answer)
    stub = ScriptedModel([AIMessage(content=content)])
    monkeypatch.setattr(pdf_tools, "_EXTRACTOR", stub)
    return stub


def _operations(raw: str) -> tuple[list, dict]:
    operations = json.loads(raw)["a2ui_operations"]
    components = next(o for o in operations if "updateComponents" in o)[
        "updateComponents"
    ]["components"]
    data = next(
        (o["updateDataModel"]["value"] for o in operations if "updateDataModel" in o),
        {},
    )
    return components, data


def _render(
    monkeypatch, answer: Any = ANSWER, *, document: str = DOCUMENT
) -> tuple[list, dict]:
    _extractor(monkeypatch, answer)
    return _operations(_call([_message(document)]))


def _texts(components: list[dict]) -> set:
    return {c.get("text") for c in components}


def _ids(components: list[dict]) -> set[str]:
    return {c["id"] for c in components}


def _by_id(components: list[dict], component_id: str) -> dict:
    return next(c for c in components if c["id"] == component_id)


def _paths(value: Any) -> list[str]:
    if isinstance(value, dict):
        if set(value) == {"path"}:
            return [value["path"]]
        return [p for v in value.values() for p in _paths(v)]
    if isinstance(value, list):
        return [p for v in value for p in _paths(v)]
    return []


def _resolve(data: Any, path: str) -> Any:
    for part in path.strip("/").split("/"):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def _assert_consistent(components: list[dict], data: dict) -> None:
    ids = _ids(components)
    assert len(ids) == len(components)
    for component in components:
        for child in component.get("children", []):
            assert child in ids, f"dangling child {child}"
        if "child" in component:
            assert component["child"] in ids
        for path in _paths(component):
            assert _resolve(data, path) is not None, f"unbound {path}"


# --- the tool ---------------------------------------------------------------


def test_a_clean_answer_fills_every_block_and_every_binding_resolves(monkeypatch):
    components, data = _render(monkeypatch)

    assert data["kpis"] == [KPI]
    assert data["trend"] == TREND and data["share"] == SHARE
    assert data["rows"] == [ROW]
    assert data["scope"] == {"options": SCOPE, "selected": "hh"}
    assert data["title"] == "Note de conjoncture"
    assert {"kpi-1", "trend-chart", "share-chart", "table", "scope-chips"} <= _ids(
        components
    )
    _assert_consistent(components, data)


def test_the_extractor_is_called_once_with_the_focus_and_the_document(monkeypatch):
    stub = _extractor(monkeypatch, ANSWER)
    _call([_message()], focus="Par secteur")

    assert len(stub.calls) == 1
    system, user = stub.calls[0][0][1], stub.calls[0][1][1]
    assert system == fixed_agent.DASHBOARD_EXTRACTION_PROMPT
    assert "Par secteur" in user and "2025T3 | 2025T4" in user


def test_the_extraction_prompt_carries_the_shared_rules():
    prompt = fixed_agent.DASHBOARD_EXTRACTION_PROMPT
    assert FRENCH_OUTPUT_RULE in prompt
    assert pdf_tools.READING_RULES in prompt
    assert pdf_tools.JSON_NUMBER_RULE in prompt
    assert "never 0,4" in pdf_tools.JSON_NUMBER_RULE
    for key in ("scope_selected", "scope_options", "kpis", "trend", "share", "rows"):
        assert key in prompt
    assert "Never compute" in prompt


def test_a_hallucinated_trend_is_dropped_and_the_other_blocks_stay(monkeypatch):
    observed = [{"label": "T2 2025", "value": 0.5}, {"label": "T3 2025", "value": 0.3}]
    components, data = _render(monkeypatch, {**ANSWER, "trend": observed})

    assert data["trend"] == []
    assert not {"trend-section", "trend-chart"} & _ids(components)
    assert data["kpis"] == [KPI]
    _assert_consistent(components, data)


def test_a_computed_row_delta_is_blanked_on_the_surface(monkeypatch):
    row = {**ROW, "delta": "+0,6 %"}
    _, data = _render(monkeypatch, {**ANSWER, "rows": [row]})
    assert data["rows"][0]["delta"] == ""


@pytest.mark.parametrize("answer", ["Voici le tableau de bord", "{}", "[]", "null"])
def test_an_unusable_answer_gives_the_failure_surface(monkeypatch, answer):
    stub = _extractor(monkeypatch, answer)
    components, _ = _operations(_call([_message()]))

    assert "Extraction impossible" in _texts(components)
    assert pdf_tools.EXTRACTION_FAILED["summary"] in _texts(components)
    assert len(stub.calls) == 1


def test_an_answer_where_nothing_survives_gives_the_failure_surface(monkeypatch):
    nothing = {"title": "T", "kpis": [{**KPI, "value": "7,77 %"}], "trend": TREND[:1]}
    components, _ = _render(monkeypatch, nothing)
    assert "Extraction impossible" in _texts(components)


def test_without_a_document_the_extractor_is_not_called(monkeypatch):
    stub = _extractor(monkeypatch, ANSWER)
    components, _ = _operations(_call([]))

    assert stub.calls == []
    assert "Extraction impossible" in _texts(components)


def test_a_provider_error_is_not_caught_by_the_tool(monkeypatch):
    request = httpx.Request("POST", "https://x")
    response = httpx.Response(429, request=request)
    error = httpx.HTTPStatusError("429", request=request, response=response)
    monkeypatch.setattr(pdf_tools, "_EXTRACTOR", ScriptedModel([error]))
    with pytest.raises(httpx.HTTPStatusError):
        _call([_message()])


@pytest.mark.parametrize(
    "answer",
    [
        {"kpis": "texte", "trend": ["a", "b"], "share": 3, "rows": "x"},
        {"kpis": [None, 4], "trend": [{"label": "a"}], "rows": [{"name": 1}]},
        {"title": 3, "eyebrow": [], "subtitle": None, "kpis": [KPI]},
        {"kpis": [KPI], "scope_options": "x", "scope_selected": 4},
    ],
)
def test_wrong_shapes_never_raise(monkeypatch, answer):
    components, data = _render(monkeypatch, answer)
    _assert_consistent(components, data)


def test_strings_that_are_not_strings_become_empty(monkeypatch):
    answer = {**ANSWER, "title": 3, "eyebrow": [], "subtitle": None}
    _, data = _render(monkeypatch, answer)
    assert (data["title"], data["eyebrow"], data["subtitle"]) == ("", "", "")


def test_no_valid_scope_option_removes_the_chips(monkeypatch):
    components, data = _render(monkeypatch, {**ANSWER, "scope_options": []})

    assert "scope-chips" not in _ids(components)
    assert "scope-chips" not in _by_id(components, "root")["children"]
    _assert_consistent(components, data)


def test_an_unknown_selected_scope_falls_back_to_the_first_option(monkeypatch):
    _, data = _render(monkeypatch, {**ANSWER, "scope_selected": "zz"})
    assert data["scope"]["selected"] == "all"


def test_kpis_are_cut_to_the_first_four(monkeypatch):
    kpis = [{**KPI, "label": f"k{i}"} for i in range(6)]
    components, data = _render(monkeypatch, {**ANSWER, "kpis": kpis})

    assert [k["label"] for k in data["kpis"]] == ["k0", "k1", "k2", "k3"]
    assert len(_by_id(components, "kpi-grid")["children"]) == 4


# --- template ---------------------------------------------------------------


def test_every_block_absent_leaves_only_the_header():
    components = _dashboard_components(0, False, False, False, False)

    assert _ids(components) == {
        "root",
        "header-card",
        "header-stack",
        "header-eyebrow",
        "header-heading",
        "header-text",
    }


def test_a_single_chart_takes_the_full_width():
    components = _dashboard_components(0, True, False, False, True)
    grid = _by_id(components, "charts-grid")
    assert grid["children"] == ["trend-section"]
    assert grid["columns"] == 1


def test_three_kpis_make_a_three_column_grid():
    grid = _by_id(_dashboard_components(3, False, False, False, True), "kpi-grid")
    assert grid["children"] == ["kpi-1", "kpi-2", "kpi-3"]
    assert grid["columns"] == 3


def test_no_row_hides_the_table_section():
    components = _dashboard_components(1, False, False, False, True)
    assert not {"table-section", "table-card", "table"} & _ids(components)
    assert "table-section" not in _by_id(components, "root")["children"]


def test_the_module_schema_is_not_mutated_by_a_render(monkeypatch):
    before = copy.deepcopy(fixed_agent.DASHBOARD_SCHEMA)
    _render(monkeypatch)
    _dashboard_components(0, False, False, False, False)
    assert fixed_agent.DASHBOARD_SCHEMA == before


def test_the_full_template_is_the_whole_schema():
    full = _dashboard_components(4, True, True, True, True)
    assert full == fixed_agent.DASHBOARD_SCHEMA


def test_no_stat_card_hard_codes_a_tone():
    cards = [c for c in fixed_agent.DASHBOARD_SCHEMA if c["component"] == "StatCard"]
    assert cards and all("deltaTone" not in c for c in cards)


# --- agent prompt and routing ------------------------------------------------


def test_the_agent_prompt_names_its_tool_chip_events_and_shared_rules():
    prompt = fixed_agent.SYSTEM_PROMPT
    assert "render_dashboard(focus=" in prompt
    assert "log_a2ui_event" in prompt
    assert "Dynamic" in prompt
    assert pdf_tools.READING_RULES in prompt
    assert FRENCH_OUTPUT_RULE in prompt
    assert "surfaceId" not in prompt
    assert "Joignez" not in prompt


def _tool_call(name: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": "c1"}])


def test_a_dashboard_is_imposed_until_the_thread_holds_one():
    required = fixed_agent._required_tool
    messages: list[AnyMessage] = [_message()]
    assert required(messages) == "render_dashboard"

    messages += [
        _tool_call("render_dashboard"),
        ToolMessage(content="{}", tool_call_id="c1", name="render_dashboard"),
        HumanMessage(content="Et la marge ?"),
    ]
    assert required(messages) is None


def test_another_tool_result_does_not_count_as_a_dashboard():
    messages: list[AnyMessage] = [
        _message(),
        _tool_call("log_a2ui_event"),
        ToolMessage(content="x", tool_call_id="c1", name="log_a2ui_event"),
    ]
    assert fixed_agent._required_tool(messages) == "render_dashboard"


def test_the_reply_without_a_document_is_the_exact_sentence():
    assert (
        fixed_agent.NO_DOCUMENT_REPLY
        == "Joignez un PDF et je génère le tableau de bord."
    )
