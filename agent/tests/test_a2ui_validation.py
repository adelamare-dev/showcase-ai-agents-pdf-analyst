import pytest
from langchain_core.messages import ToolMessage

from src.a2ui_validation import (
    CATALOG_COMPONENTS,
    fallback_components,
    normalize_heading_levels,
    validate_components,
)


def test_component_names_match_catalog():
    assert len(CATALOG_COMPONENTS) == 21
    assert {"Stack", "DataTable", "ChoiceChips", "Callout"} <= CATALOG_COMPONENTS


def _text(**extra):
    return {"id": "root", "component": "Text", "text": "x", **extra}


@pytest.mark.parametrize(
    ("components", "expected"),
    [
        ([_text()], None),
        ([{"id": "a", "component": "Text", "text": "x"}], "root"),
        ([{"id": "root", "component": "Sankey"}], "Sankey"),
        ([{"id": "root", "component": "Stack", "children": ["missing"]}], "missing"),
        ([{"id": "root", "component": "Card", "child": "missing"}], "missing"),
        (
            [
                {
                    "id": "root",
                    "component": "Stack",
                    "children": {"componentId": "missing", "path": "/items"},
                }
            ],
            "missing",
        ),
        ([_text(), _text()], "root"),
        ("oops", "list"),
        ([{"id": "root", "component": ["Text"]}], "type"),
        ([{"id": ["x"], "component": "Text"}], "id"),
    ],
)
def test_validate_components(components, expected):
    errors = validate_components(components)
    if expected is None:
        assert errors == []
    else:
        assert errors
        assert any(expected in error for error in errors)


def test_duplicate_id_is_reported_as_duplicate():
    errors = validate_components([_text(), {"id": "root", "component": "Text"}])
    assert any("duplicate" in error.lower() for error in errors)


@pytest.mark.parametrize(
    ("level", "expected"),
    [("h2", "2"), (3, "3"), ("1", "1"), ("h1", "1"), ("big", None), ("h4", None)],
)
def test_normalize_heading_levels(level, expected):
    components = [{"id": "t", "component": "Heading", "text": "x", "level": level}]
    normalize_heading_levels(components)
    if expected is None:
        assert "level" not in components[0]
    else:
        assert components[0]["level"] == expected


def test_normalize_heading_levels_leaves_other_components_alone():
    components = [
        {"id": "a", "component": "Text", "text": "x", "level": "h1"},
        {"id": "b", "component": "Heading", "text": "x"},
        "not a dict",
    ]
    normalize_heading_levels(components)
    assert components[0]["level"] == "h1"
    assert "level" not in components[1]


def test_fallback_uses_only_catalog_components():
    assert validate_components(fallback_components([])) == []
    query = ToolMessage(
        name="query_pdf",
        tool_call_id="q1",
        content='{"title": "T", "summary": "S"}',
    )
    assert validate_components(fallback_components([query])) == []


def test_fallback_reads_query_pdf_result_given_as_content_blocks():
    query = ToolMessage(
        name="query_pdf",
        tool_call_id="q1",
        content=[{"type": "text", "text": '{"title": "CA 2024", "summary": "S"}'}],
    )
    components = fallback_components([query])
    texts = {c["component"]: c["text"] for c in components if "text" in c}
    assert texts["Heading"] == "CA 2024"
