from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src import dynamic_agent, fixed_agent, pdf_tools
from src.locale import FRENCH_OUTPUT_RULE
from tests.fakes import ScriptedModel, fake_runtime


def test_fixed_agent_prompt_carries_the_french_rule():
    assert FRENCH_OUTPUT_RULE in fixed_agent.SYSTEM_PROMPT


def test_dynamic_agent_prompt_carries_the_french_rule():
    assert FRENCH_OUTPUT_RULE in dynamic_agent.SYSTEM_PROMPT


def test_dynamic_agent_asks_for_a_pdf_in_french():
    assert "Joignez un PDF" in dynamic_agent.SYSTEM_PROMPT
    assert "Attach a PDF" not in dynamic_agent.SYSTEM_PROMPT


def test_render_prompt_carries_the_french_rule(monkeypatch):
    render_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "render_a2ui",
                "id": "abc123def",
                "args": {
                    "surfaceId": "s1",
                    "components": [{"id": "root", "component": "Text", "text": "x"}],
                },
            }
        ],
    )
    stub = ScriptedModel([render_call])
    monkeypatch.setattr(dynamic_agent, "_RENDER_MODEL", stub)
    dynamic_agent.generate_a2ui.func(  # type: ignore[union-attr]
        fake_runtime([HumanMessage(content="Show revenue"), AIMessage(content="")])
    )
    system = stub.calls[0][0]
    assert isinstance(system, SystemMessage)
    assert FRENCH_OUTPUT_RULE in system.content


def test_query_pdf_system_message_carries_the_french_rule(monkeypatch):
    answer = '{"shape_hint":"text","title":"T","summary":"S","data":""}'
    stub = ScriptedModel([AIMessage(content=answer)])
    monkeypatch.setattr(pdf_tools, "_EXTRACTOR", stub)
    pdf_tools.query_pdf.func(  # type: ignore[union-attr]
        question="y",
        runtime=fake_runtime([HumanMessage(content="[Document: x.pdf]\nx")]),
    )
    assert FRENCH_OUTPUT_RULE in stub.calls[0][0][1]


def test_rule_requires_numbers_and_french_formats():
    assert "numbers" in FRENCH_OUTPUT_RULE
    assert "DD/MM/YYYY" in FRENCH_OUTPUT_RULE
