import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from src import pdf_tools
from tests.fakes import ScriptedModel, fake_runtime

ANSWER = '{"shape_hint":"text","title":"T","summary":"S","data":""}'


def _doc(body: str, name: str = "report.pdf") -> str:
    return f"[Document: {name}]\n{body}"


def _query(
    monkeypatch,
    messages: list,
    question: str = "What is it?",
    tool_call_id: str | None = None,
):
    stub = ScriptedModel([AIMessage(content=ANSWER)])
    monkeypatch.setattr(pdf_tools, "_EXTRACTOR", stub)
    tool = pdf_tools.query_pdf
    assert isinstance(tool, StructuredTool) and tool.func is not None
    result = tool.func(
        question=question, runtime=fake_runtime(messages, tool_call_id=tool_call_id)
    )
    return stub, result


def _user_prompt(stub: ScriptedModel) -> str:
    return stub.calls[0][1][1]


def test_model_facing_args_are_the_question_only():
    schema = convert_to_openai_tool(pdf_tools.query_pdf)
    assert set(schema["function"]["parameters"]["properties"]) == {"question"}


def test_extractor_receives_the_whole_document(monkeypatch):
    body = "a" * 44_990 + "THE-END"
    stub, _ = _query(monkeypatch, [HumanMessage(content=_doc(body))])
    assert "THE-END" in _user_prompt(stub)
    assert body in _user_prompt(stub)


def test_most_recent_document_wins(monkeypatch):
    messages = [
        HumanMessage(content=_doc("OLD-BODY", "old.pdf")),
        AIMessage(content="ok"),
        HumanMessage(content=_doc("NEW-BODY", "new.pdf")),
        AIMessage(content="ok"),
        HumanMessage(content="a follow-up without a document"),
    ]
    stub, _ = _query(monkeypatch, messages)
    assert "NEW-BODY" in _user_prompt(stub)
    assert "OLD-BODY" not in _user_prompt(stub)


def test_document_is_found_in_content_blocks(monkeypatch):
    message = HumanMessage(
        content=[
            {"type": "text", "text": "Summarise this"},
            {"type": "text", "text": _doc("BLOCK-BODY")},
        ]
    )
    stub, _ = _query(monkeypatch, [message])
    assert "BLOCK-BODY" in _user_prompt(stub)
    assert "Summarise this" not in _user_prompt(stub).split("PDF text")[1]


def test_document_given_as_plain_string_is_found(monkeypatch):
    stub, _ = _query(monkeypatch, [HumanMessage(content=_doc("STRING-BODY"))])
    assert "STRING-BODY" in _user_prompt(stub)


def test_header_without_filename_is_recognised(monkeypatch):
    message = HumanMessage(content="[Document attached]\nANON-BODY")
    stub, _ = _query(monkeypatch, [message])
    assert "ANON-BODY" in _user_prompt(stub)


def test_several_documents_in_one_message_are_joined(monkeypatch):
    message = HumanMessage(
        content=[
            {"type": "text", "text": _doc("FIRST-BODY", "a.pdf")},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
            {"type": "text", "text": _doc("SECOND-BODY", "b.pdf")},
        ]
    )
    assert pdf_tools.latest_document_text([message]) == (
        f"{_doc('FIRST-BODY', 'a.pdf')}\n\n{_doc('SECOND-BODY', 'b.pdf')}"
    )


def test_no_document_returns_fallback_without_calling_the_extractor(monkeypatch):
    stub, result = _query(monkeypatch, [HumanMessage(content="Hello")])
    assert stub.calls == []
    data = json.loads(result)
    assert data["shape_hint"] == "text"
    assert "no document" in data["summary"].lower()


def test_latest_document_text_is_none_without_a_document():
    assert pdf_tools.latest_document_text([]) is None
    assert pdf_tools.latest_document_text([AIMessage(content=_doc("x"))]) is None


def test_tool_node_injects_the_runtime_with_the_graph_state(monkeypatch):
    stub = ScriptedModel([AIMessage(content=ANSWER)])
    monkeypatch.setattr(pdf_tools, "_EXTRACTOR", stub)
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode([pdf_tools.query_pdf]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    call = AIMessage(
        content="",
        tool_calls=[{"name": "query_pdf", "args": {"question": "Q?"}, "id": "call1"}],
    )
    result = graph.compile().invoke(
        {"messages": [HumanMessage(content=_doc("GRAPH-BODY")), call]}
    )
    tool_message = result["messages"][-1]
    assert isinstance(tool_message, ToolMessage)
    assert json.loads(str(tool_message.content))["shape_hint"] == "text"
    assert "GRAPH-BODY" in _user_prompt(stub)


def _query_call(*ids: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "query_pdf", "args": {"question": "Q?"}, "id": call_id}
            for call_id in ids
        ],
    )


def _answered(call_id: str) -> ToolMessage:
    return ToolMessage(content=ANSWER, tool_call_id=call_id, name="query_pdf")


def test_third_sequential_call_in_a_turn_is_refused(monkeypatch):
    messages = [
        HumanMessage(content=_doc("BODY")),
        _query_call("c1"),
        _answered("c1"),
        _query_call("c2"),
        _answered("c2"),
        _query_call("c3"),
    ]
    stub, result = _query(monkeypatch, messages, tool_call_id="c3")
    assert stub.calls == []
    data = json.loads(result)
    assert data["shape_hint"] == "text"
    assert "generate_a2ui" in data["summary"]
    assert "limit" in data["summary"].lower()


def test_first_two_sequential_calls_in_a_turn_run(monkeypatch):
    messages = [
        HumanMessage(content=_doc("BODY")),
        _query_call("c1"),
        _answered("c1"),
        _query_call("c2"),
    ]
    for call_id in ("c1", "c2"):
        stub, result = _query(monkeypatch, messages, tool_call_id=call_id)
        assert len(stub.calls) == 1
        assert result == ANSWER


def test_parallel_calls_in_one_message_are_capped_by_call_id(monkeypatch):
    messages = [HumanMessage(content=_doc("BODY")), _query_call("c1", "c2", "c3")]
    outcomes = {}
    for call_id in ("c1", "c2", "c3"):
        stub, result = _query(monkeypatch, messages, tool_call_id=call_id)
        outcomes[call_id] = (len(stub.calls), result)
    assert outcomes["c1"] == (1, ANSWER)
    assert outcomes["c2"] == (1, ANSWER)
    assert outcomes["c3"][0] == 0
    assert json.loads(outcomes["c3"][1])["shape_hint"] == "text"


def test_a_newer_human_message_resets_the_count(monkeypatch):
    messages = [
        HumanMessage(content=_doc("BODY")),
        _query_call("c1", "c2"),
        _answered("c1"),
        _answered("c2"),
        AIMessage(content=""),
        HumanMessage(content="And the margin?"),
        _query_call("c3"),
    ]
    stub, result = _query(monkeypatch, messages, tool_call_id="c3")
    assert len(stub.calls) == 1
    assert result == ANSWER


def test_other_tools_do_not_count_toward_the_cap(monkeypatch):
    other = AIMessage(
        content="", tool_calls=[{"name": "generate_a2ui", "args": {}, "id": "g1"}]
    )
    messages = [
        HumanMessage(content=_doc("BODY")),
        other,
        _query_call("c1", "c2"),
    ]
    stub, _ = _query(monkeypatch, messages, tool_call_id="c2")
    assert len(stub.calls) == 1
