import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from src import pdf_tools
from src.locale import FRENCH_OUTPUT_RULE
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


def _system_prompt(stub: ScriptedModel) -> str:
    return stub.calls[0][0][1]


def test_system_prompt_carries_the_reading_and_json_rules(monkeypatch):
    stub, _ = _query(monkeypatch, [HumanMessage(content=_doc("BODY"))])
    prompt = _system_prompt(stub)
    assert pdf_tools.READING_RULES in prompt
    assert "never 0,4" in pdf_tools._JSON_RULES
    assert prompt.index(FRENCH_OUTPUT_RULE) < prompt.index(pdf_tools.READING_RULES)
    assert prompt.index(pdf_tools.READING_RULES) < prompt.index(pdf_tools._JSON_RULES)
    assert prompt.endswith(f"{pdf_tools.READING_RULES}\n{pdf_tools._JSON_RULES}")


def _query_returning(monkeypatch, raw: str) -> tuple[ScriptedModel, str]:
    stub = ScriptedModel([AIMessage(content=raw)])
    monkeypatch.setattr(pdf_tools, "_EXTRACTOR", stub)
    tool = pdf_tools.query_pdf
    assert isinstance(tool, StructuredTool) and tool.func is not None
    result = tool.func(
        question="Q?",
        runtime=fake_runtime([HumanMessage(content=_doc("BODY"))]),
    )
    return stub, result


def _answer_with(monkeypatch, raw: str) -> dict:
    stub, result = _query_returning(monkeypatch, raw)
    assert len(stub.calls) == 1  # no second attempt
    return json.loads(result)


def test_valid_json_is_returned_as_is(monkeypatch):
    _, result = _query(monkeypatch, [HumanMessage(content=_doc("BODY"))])
    assert result == ANSWER
    assert "failed" not in json.loads(result)


def test_decimal_commas_after_a_colon_are_repaired(monkeypatch):
    # Written this way by the real extractor, on a follow-up question.
    raw = (
        '{"shape_hint": "trend", "title": "Exportations, 2025", "data": [\n'
        '  { "label": "2025T3", "value": 2,8 },\n'
        '  { "label": "2026T1", "value": -3,0 }\n'
        "]}"
    )
    data = _answer_with(monkeypatch, raw)
    assert data["title"] == "Exportations, 2025"
    assert data["data"] == [
        {"label": "2025T3", "value": 2.8},
        {"label": "2026T1", "value": -3.0},
    ]


def test_valid_json_is_never_repaired(monkeypatch):
    # In a list `2,8` is two valid numbers, and text keeps its commas.
    raw = '{"shape_hint":"text","title":"note: 2,8 }","summary":"S","data":[2,8]}'
    _, result = _query_returning(monkeypatch, raw)
    assert result == raw


def test_line_breaks_inside_a_string_are_accepted(monkeypatch):
    # Written this way by the real extractor, on a narrative question.
    raw = (
        '{\n  "shape_hint": "text",\n  "title": "Résumé",\n  "summary": "S",\n'
        '  "data": "\n1. **Spécification** : a\n2. **Processus** : b\n"\n}'
    )
    _, result = _query_returning(monkeypatch, raw)
    # Downstream readers parse it strictly.
    data = json.loads(result)
    assert data["title"] == "Résumé"
    assert data["data"] == "\n1. **Spécification** : a\n2. **Processus** : b\n"
    assert "Résumé" in result


def test_a_repair_leaves_json_strings_alone(monkeypatch):
    raw = '{"title":"Marge: 2,8 }","summary":"S","data":[{"value":0,4}]}'
    data = _answer_with(monkeypatch, raw)
    assert data["title"] == "Marge: 2,8 }"
    assert data["data"] == [{"value": 0.4}]


def test_a_thousands_separator_is_a_failure_not_a_decimal(monkeypatch):
    # 94,930 means 94 930 in an English document: 94.93 would be a wrong number.
    raw = '{"shape_hint":"stat","title":"T","summary":"S","data":{"value":94,930}}'
    assert _answer_with(monkeypatch, raw)["failed"] is True


def test_a_number_with_several_commas_is_a_failure(monkeypatch):
    raw = '{"shape_hint":"stat","title":"T","summary":"S","data":{"value":1,234,567}}'
    assert _answer_with(monkeypatch, raw)["failed"] is True


def test_broken_json_is_a_failure(monkeypatch):
    data = _answer_with(monkeypatch, '{"shape_hint":"trend","title":')
    assert data == {
        "shape_hint": "text",
        "title": "Extraction impossible",
        "summary": (
            "Je n'ai pas réussi à extraire ces données du document. "
            "Reformulez la question ou réessayez."
        ),
        "data": "",
        "failed": True,
    }


def test_json_that_is_not_an_object_is_a_failure(monkeypatch):
    for raw in ("[1, 2]", "42", '"text"'):
        assert _answer_with(monkeypatch, raw)["failed"] is True


def test_fenced_json_is_still_accepted(monkeypatch):
    fenced = "```json" + chr(10) + ANSWER + chr(10) + "```"
    assert _answer_with(monkeypatch, fenced)["title"] == "T"


def _attached(body: str = "BODY") -> HumanMessage:
    return HumanMessage(
        content=[
            {"type": "text", "text": "Question?"},
            {"type": "text", "text": _doc(body)},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
        ]
    )


def test_without_document_text_removes_the_document_and_keeps_the_rest():
    original = _attached("SECRET-BODY")
    reply = AIMessage(content="ok")
    out = pdf_tools.without_document_text([original, reply])
    assert out[1] is reply
    assert out[0].content == [
        {"type": "text", "text": "Question?"},
        {"type": "text", "text": pdf_tools.DOCUMENT_OMITTED},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
    ]
    assert "SECRET-BODY" not in str(out)


def test_without_document_text_does_not_mutate_the_state():
    original = _attached("SECRET-BODY")
    before = [dict(block) for block in original.content if isinstance(block, dict)]
    pdf_tools.without_document_text([original])
    assert original.content == before
    assert pdf_tools.DOCUMENT_OMITTED == (
        "[Attached document omitted here: its content is in the query_pdf results.]"
    )


def test_without_document_text_handles_a_string_content():
    out = pdf_tools.without_document_text([HumanMessage(content=_doc("SECRET-BODY"))])
    assert out[0].content == pdf_tools.DOCUMENT_OMITTED
    plain = HumanMessage(content="just a question")
    assert pdf_tools.without_document_text([plain])[0].content == "just a question"


def test_without_document_text_leaves_non_human_messages_alone():
    messages = [AIMessage(content=_doc("x")), _answered("c1")]
    assert pdf_tools.without_document_text(messages) == messages


def _failed_result(call_id: str) -> ToolMessage:
    return ToolMessage(
        content=json.dumps({"summary": "S", "failed": True}),
        tool_call_id=call_id,
        name="query_pdf",
    )


def test_extraction_failed_reads_the_last_query_pdf_result():
    assert pdf_tools.extraction_failed([_failed_result("c1")])
    # A later successful call supersedes an earlier failed one, and vice versa.
    assert not pdf_tools.extraction_failed([_failed_result("c1"), _answered("c2")])
    assert pdf_tools.extraction_failed([_answered("c1"), _failed_result("c2")])


def test_extraction_failed_is_false_without_a_usable_result():
    assert not pdf_tools.extraction_failed([])
    assert not pdf_tools.extraction_failed([HumanMessage(content="q")])
    other = ToolMessage(content='{"failed": true}', tool_call_id="x", name="other")
    assert not pdf_tools.extraction_failed([other])
    junk = ToolMessage(content="not json", tool_call_id="c1", name="query_pdf")
    assert not pdf_tools.extraction_failed([junk])
    listing = ToolMessage(content="[1]", tool_call_id="c1", name="query_pdf")
    assert not pdf_tools.extraction_failed([listing])
    no_flag = ToolMessage(
        content='{"failed": false}', tool_call_id="c1", name="query_pdf"
    )
    assert not pdf_tools.extraction_failed([no_flag])


def test_call_ids_helper_is_public():
    messages = [HumanMessage(content="q"), _query_call("c1")]
    assert pdf_tools.query_pdf_call_ids_this_turn(messages) == ["c1"]
