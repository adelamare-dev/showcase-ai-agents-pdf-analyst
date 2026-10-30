from ag_ui.core import DocumentInputContent, InputContentDataSource
from langchain_core.messages import HumanMessage

from scripts.measure import read_text_cap
from src.multimodal_middleware import DOCUMENT_MAX_CHARS, _patched
from src.pdf_tools import latest_document_text

NOTE = "[Document tronqué : limite du serveur atteinte]"


def _document(value: str, filename: str | None = "report.pdf") -> DocumentInputContent:
    return DocumentInputContent(
        type="document",
        source=InputContentDataSource(type="data", value=value, mime_type="text/plain"),
        metadata={"filename": filename} if filename else None,
    )


def _text_of(blocks: list[dict]) -> str:
    assert len(blocks) == 1
    return blocks[0]["text"]


def test_document_under_the_cap_is_passed_through_byte_for_byte():
    body = "é" * DOCUMENT_MAX_CHARS
    assert _text_of(_patched([_document(body)])) == f"[Document: report.pdf]\n{body}"


def test_document_over_the_cap_is_cut_with_a_note_after_the_header():
    body = "a" * (DOCUMENT_MAX_CHARS + 500)
    text = _text_of(_patched([_document(body)]))
    assert text == f"[Document: report.pdf]\n{NOTE}\n{'a' * DOCUMENT_MAX_CHARS}"


def test_header_without_a_filename_stays_in_front_when_cut():
    text = _text_of(_patched([_document("a" * (DOCUMENT_MAX_CHARS + 1), None)]))
    assert text.startswith(f"[Document attached]\n{NOTE}\n")


def test_cut_document_is_still_found_by_the_pdf_tools():
    text = _text_of(_patched([_document("b" * (DOCUMENT_MAX_CHARS + 1))]))
    message = HumanMessage(content=[{"type": "text", "text": text}])
    found = latest_document_text([message])
    assert found == text
    assert found is not None
    assert found.startswith("[Document: report.pdf]\n")


def test_browser_truncation_note_does_not_trigger_the_server_cap():
    # The browser prefixes its own note to a body already at its cap.
    body = "[Document tronqué : pages 1 à 12 sur 40]\n" + "c" * read_text_cap()
    assert _text_of(_patched([_document(body)])) == f"[Document: report.pdf]\n{body}"


def test_server_cap_is_above_the_browser_cap():
    # A raise of the browser cap must fail here instead of being cut silently.
    assert DOCUMENT_MAX_CHARS > read_text_cap()


def test_cap_applies_to_each_document_separately():
    blocks = _patched(
        [
            _document("a" * (DOCUMENT_MAX_CHARS + 1), "a.pdf"),
            _document("b" * DOCUMENT_MAX_CHARS, "b.pdf"),
        ]
    )
    assert NOTE in blocks[0]["text"]
    assert NOTE not in blocks[1]["text"]
