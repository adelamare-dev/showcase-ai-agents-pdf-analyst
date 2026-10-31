"""Shared agent tools: PDF text → structured data for the catalog."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

from src.locale import FRENCH_OUTPUT_RULE
from src.models import EXTRACTOR_MODEL, chat_model

# Not streamed: with streaming on, the raw JSON the extractor writes would be
# relayed to the chat as assistant text while it is being produced.
_EXTRACTOR = chat_model(EXTRACTOR_MODEL, disable_streaming=True)

# Every `query_pdf` call sends the whole document to the extractor. A crafted
# document can tell the agent to keep calling it, so a turn is capped.
MAX_QUERY_PDF_CALLS_PER_TURN = 2

DOCUMENT_OMITTED = (
    "[Attached document omitted here: its content is in the query_pdf results.]"
)

# Returned (and shown to the user as is) when the extractor's answer is unusable.
# Another attempt at temperature 0 would give the same output, so there is none.
EXTRACTION_FAILED = {
    "shape_hint": "text",
    "title": "Extraction impossible",
    "summary": (
        "Je n'ai pas réussi à extraire ces données du document. "
        "Reformulez la question ou réessayez."
    ),
    "data": "",
    "failed": True,
}

# Also reused by the /fixed agent, whose prompts read the document too.
READING_RULES = """\
## Reading the document

The text was extracted from a PDF. Each line is one row of the page and " | "
separates the cells of a row.
- Prefer a table to a chart. A table is a header row followed by rows of cells:
  the Nth value of a row belongs to the Nth cell of the header above it.
- Copy each label exactly as it is written in that header. Never rename,
  renumber or complete a period.
- Report only the columns the question asks for.
- Lines of evenly spaced numbers (1,0 then 0,8 then 0,6...) and lines of many
  periods (T1-22 T2-22 T3-22...) are chart axes, not data: never report them.
- Report only values written in the document. Never estimate or fill a gap.
"""

# Shared by every prompt that asks the extractor for JSON.
JSON_NUMBER_RULE = """\
A JSON number uses a dot and
nothing else: write 0.4, never 0,4. French formatting applies to strings only.
"""

_JSON_RULES = f"""\
## JSON rules

Keep the JSON keys exactly as shown, in English. `data` is exactly the payload
of the chosen shape, with no wrapper object. {JSON_NUMBER_RULE}"""


def _strip_to_json(text: str) -> str:
    """LLM output may be wrapped in ```json fences. Strip them."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


# Even when told not to, the extractor writes numbers the French way, with the
# right values: `"value": 2,8`. After a colon that is never valid JSON, so it is
# safe to repair. Left alone: strings (matched first, to be skipped), lists,
# where `2,8` is two valid numbers, and three digits after the comma, which can
# be a thousands separator (94,930): a failure is better than a wrong number.
_DECIMAL_COMMA = re.compile(
    r'"(?:[^"\\]|\\.)*"|(:\s*-?\d+),(\d{1,2}|\d{4,})(?=\s*[,}\]])'
)


def _repair_decimal_commas(raw: str) -> str:
    return _DECIMAL_COMMA.sub(
        lambda match: f"{match[1]}.{match[2]}" if match[1] else match[0], raw
    )


def _extraction_json(raw: str) -> str | None:
    """`raw` as the text of a JSON object, repaired if needed, or None if unusable.

    On narrative answers the extractor also writes real line breaks inside
    strings, which `strict=False` accepts. A repaired answer is written back as
    standard JSON because the readers of the tool result parse it strictly.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            parsed = json.loads(_repair_decimal_commas(raw), strict=False)
        except json.JSONDecodeError:
            return None
        raw = json.dumps(parsed, ensure_ascii=False)
    return raw if isinstance(parsed, dict) else None


def _block_texts(content: Any) -> list[str]:
    """Text of each block of a message `content` (a string or a list of blocks)."""
    if isinstance(content, str):
        return [content]
    texts: list[str] = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, str):
            texts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            texts.append(block["text"])
    return texts


def latest_document_text(messages: list[AnyMessage]) -> str | None:
    """Text of the document attached to the most recent human message that has one.

    The multimodal middleware writes each document as a text block starting with
    a `[Document: <filename>]` (or `[Document attached]`) header; that header is
    how a document is told apart from the user's own words. Several documents in
    one message are joined with a blank line.
    """
    for message in reversed(messages):
        if not isinstance(message, HumanMessage):
            continue
        documents = [
            text
            for text in _block_texts(message.content)
            if text.startswith("[Document")
        ]
        if documents:
            return "\n\n".join(documents)
    return None


def query_pdf_call_ids_this_turn(messages: list[AnyMessage]) -> list[str]:
    """IDs of the `query_pdf` calls made since the last human message, in order."""
    start = 0
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            start = index + 1
    return [
        call["id"]
        for message in messages[start:]
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if call["name"] == "query_pdf" and call["id"]
    ]


def without_document_text(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Copy of `messages` with every attached document replaced by a placeholder.

    The render model gets the `query_pdf` results; the full text would only
    tempt it to read values the extractor did not report. The state is not
    modified.
    """
    out: list[AnyMessage] = []
    for message in messages:
        if not isinstance(message, HumanMessage):
            out.append(message)
        elif isinstance(message.content, str):
            content = message.content
            out.append(
                message.model_copy(update={"content": DOCUMENT_OMITTED})
                if content.startswith("[Document")
                else message
            )
        else:
            blocks = [_omit_document(block) for block in message.content]
            out.append(message.model_copy(update={"content": blocks}))
    return out


def _omit_document(block: Any) -> Any:
    """A content block, with its text swapped for the placeholder if it is a document."""
    if isinstance(block, str):
        return DOCUMENT_OMITTED if block.startswith("[Document") else block
    if isinstance(block, dict):
        text = block.get("text")
        if isinstance(text, str) and text.startswith("[Document"):
            return {**block, "text": DOCUMENT_OMITTED}
    return block


def extraction_failed(messages: list[AnyMessage]) -> bool:
    """Whether the latest `query_pdf` result reports a failed extraction."""
    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.name == "query_pdf":
            try:
                payload = json.loads(message.text)
            except json.JSONDecodeError:
                return False
            return isinstance(payload, dict) and payload.get("failed") is True
    return False


def extract_json(system: str, user: str, *, json_mode: bool = False) -> str | None:
    """Ask the extractor and return its answer as JSON object text, or None.

    None means the answer is unusable (not JSON, or not an object). Provider
    exceptions are not caught: they reach `MistralErrorMiddleware`. `json_mode`
    has the provider enforce a JSON object: the 8B leaves out commas between
    keys, which the repair in `_extraction_json` cannot restore.
    """
    model = (
        _EXTRACTOR.bind(response_format={"type": "json_object"})
        if json_mode
        else _EXTRACTOR
    )
    out = model.invoke([("system", system), ("user", user)])
    raw = _strip_to_json(
        out.content if isinstance(out.content, str) else str(out.content)
    )
    return _extraction_json(raw)


@tool
def query_pdf(question: str, runtime: ToolRuntime[Any]) -> str:
    """Answer a user question about the attached PDF and return ONLY structured
    data that the dynamic agent can then render as a UI surface.

    Pass only the question. The tool reads the most recent attached document
    itself, so never copy or paste the document text into the call.

    Returns a JSON object: { "shape_hint": "stat|trend|share|table|text",
                             "title": "...", "summary": "...",
                             "data": <shape-appropriate payload> }
    The shape_hint is advice. The agent makes the final layout decision.
    """
    pdf_text = latest_document_text(runtime.state["messages"])
    if pdf_text is None:
        return json.dumps(
            {
                "shape_hint": "text",
                "title": "No document",
                "summary": "No document was found in the conversation. Ask the user to attach a PDF.",
                "data": "",
            }
        )
    over_limit = query_pdf_call_ids_this_turn(runtime.state["messages"])[
        MAX_QUERY_PDF_CALLS_PER_TURN:
    ]
    if runtime.tool_call_id in over_limit:
        return json.dumps(
            {
                "shape_hint": "text",
                "title": "Limit reached",
                "summary": (
                    "The limit of query_pdf calls for this turn is reached. "
                    "Call generate_a2ui now to render the answer."
                ),
                "data": "",
            }
        )
    sys = (
        "You are an analyst answering a question about a PDF. Return ONLY a "
        "JSON object describing the answer as structured data. No prose, no "
        "markdown fences. Pick the most natural shape for the answer:\n"
        "- 'stat'  → { value, delta?, caption? }  for single-metric answers\n"
        "- 'trend' → [{label, value}, ...]        for time-series\n"
        "- 'share' → [{label, value}, ...]        for breakdowns / shares\n"
        "- 'table' → { columns:[{key,label}], rows:[{...}] }  for lists\n"
        "- 'text'  → string                       for narrative answers\n\n"
        f"{FRENCH_OUTPUT_RULE}\n\n"
        f"{READING_RULES}\n{_JSON_RULES}"
    )
    user = f"""Question: {question}

PDF text:
\"\"\"
{pdf_text}
\"\"\"

Return JSON shaped like:
{{
  "shape_hint": "stat|trend|share|table|text",
  "title": "...",
  "summary": "...",
  "data": <payload above>
}}
"""
    return extract_json(sys, user) or json.dumps(EXTRACTION_FAILED)
