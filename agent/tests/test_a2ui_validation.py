import re
from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage

from src.a2ui_validation import (
    CATALOG_CHOICES,
    CATALOG_COMPONENTS,
    drop_invalid_choices,
    fallback_components,
    normalize_heading_levels,
    validate_components,
)


def test_component_names_match_catalog():
    assert len(CATALOG_COMPONENTS) == 21
    assert {"Stack", "DataTable", "ChoiceChips", "Callout"} <= CATALOG_COMPONENTS


def test_choices_are_read_from_the_catalog_prompt():
    assert CATALOG_CHOICES["Text"]["weight"] == {"regular", "medium", "semibold"}
    assert CATALOG_CHOICES["Heading"]["level"] == {"1", "2", "3"}
    assert CATALOG_CHOICES["Card"]["tone"] == {"default", "lilac", "mint", "warning"}
    # Free text, ranges and booleans are not choices.
    assert "title" not in CATALOG_CHOICES["Callout"]
    assert "BarChart" not in CATALOG_CHOICES
    assert "columns" not in CATALOG_CHOICES["Grid"]
    assert "ChoiceChips" not in CATALOG_CHOICES


def _zod_optional_enums() -> dict[str, dict[str, set[str]]]:
    source = (Path(__file__).parents[2] / "src/a2ui/catalog/definitions.ts").read_text(
        encoding="utf-8"
    )
    enums: dict[str, dict[str, set[str]]] = {}
    for block in re.split(r"(?m)^  (?=\w+: \{$)", source)[1:]:
        name = block.split(":", 1)[0]
        for prop, values in re.findall(
            r"(\w+): z\s*\.enum\(\[([^\]]*)\]\)\s*\.optional\(\)", block
        ):
            enums.setdefault(name, {})[prop] = set(re.findall(r'"([^"]+)"', values))
    return enums


def test_choices_stay_in_sync_with_the_client_schemas():
    # Keeps only the top-level props: nested ones (a column's `align`) are not in
    # the summary line of the prompt.
    zod = _zod_optional_enums()
    assert zod, "the Zod definitions could not be parsed"
    for component, props in CATALOG_CHOICES.items():
        for prop, allowed in props.items():
            assert zod[component][prop] == allowed, f"{component}.{prop}"


def test_drop_invalid_choices_removes_only_values_outside_the_list():
    components = [
        {"id": "a", "component": "Text", "text": "x", "weight": 1, "size": "lg"},
        {"id": "b", "component": "Stack", "children": [], "gap": "huge"},
        {"id": "c", "component": "Card", "child": "a", "tone": {"path": "/t"}},
        {"id": "d", "component": "Heading", "text": "x", "variant": "h2"},
    ]
    drop_invalid_choices(components)
    assert components == [
        {"id": "a", "component": "Text", "text": "x", "size": "lg"},
        {"id": "b", "component": "Stack", "children": []},
        {"id": "c", "component": "Card", "child": "a"},
        {"id": "d", "component": "Heading", "text": "x", "variant": "h2"},
    ]


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
