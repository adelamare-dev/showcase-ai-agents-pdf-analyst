"""Structural validation of model-generated A2UI components, and a text fallback.

Scope: the dynamic agent only (`generate_a2ui`). The fixed agent renders a
hard-coded tree, so there is nothing to validate there.

Known limit: only the shape of the surface is checked here (list of dicts,
unique ids, a single `root`, known component types, resolvable child
references). Component props are NOT validated in Python; their Zod schemas on
the client remain the only check. Component names are derived from the
`- **Name**` lines of `CATALOG_PROMPT`, so changing that line format breaks
the validation.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import ToolMessage

from src.catalog import CATALOG_PROMPT


def component_names(prompt: str) -> frozenset[str]:
    return frozenset(re.findall(r"^- \*\*(\w+)\*\*", prompt, flags=re.MULTILINE))


CATALOG_COMPONENTS: frozenset[str] = component_names(CATALOG_PROMPT)


def _references(component: dict) -> list[object]:
    refs: list[object] = []
    if "child" in component:
        refs.append(component["child"])
    children = component.get("children")
    if isinstance(children, list):
        refs.extend(children)
    elif isinstance(children, dict):
        refs.append(children.get("componentId"))
    return refs


def validate_components(components: object) -> list[str]:
    """Return validation errors (empty when valid). Messages go back to the model."""
    if not isinstance(components, list):
        return ["`components` must be a list of component objects."]

    errors: list[str] = []
    ids: set[str] = set()
    valid_items = []
    for index, item in enumerate(components):
        if not isinstance(item, dict):
            errors.append(f"Component at index {index} is not an object.")
            continue
        component_id = item.get("id")
        if not isinstance(component_id, str) or not component_id:
            errors.append(f"Component at index {index} has no non-empty string `id`.")
        elif component_id in ids:
            errors.append(f"Duplicate component id '{component_id}'.")
        else:
            ids.add(component_id)
        kind = item.get("component")
        if not isinstance(kind, str) or kind not in CATALOG_COMPONENTS:
            errors.append(
                f"Component '{component_id}' has unknown type '{kind}'; "
                "use only components from the catalog."
            )
        valid_items.append(item)

    if not any(item.get("id") == "root" for item in valid_items):
        errors.append('No component has id "root"; exactly one is required.')

    for item in valid_items:
        for ref in _references(item):
            if not isinstance(ref, str) or ref not in ids:
                errors.append(
                    f"Component '{item.get('id')}' references missing id '{ref}'."
                )
    return errors


_GENERIC_TITLE = "Réponse"
_GENERIC_SUMMARY = (
    "Je n'ai pas pu mettre en forme cette réponse. Reformulez votre question "
    "ou réessayez."
)


def _last_query_pdf_summary(messages: list) -> tuple[str, str] | None:
    for message in reversed(messages):
        if not (isinstance(message, ToolMessage) and message.name == "query_pdf"):
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            title, summary = payload.get("title"), payload.get("summary")
            if isinstance(title, str) and isinstance(summary, str):
                return title, summary
    return None


def fallback_components(messages: list) -> list[dict]:
    """Plain Stack/Heading/Text surface, built without any model call."""
    title, summary = _last_query_pdf_summary(messages) or (
        _GENERIC_TITLE,
        _GENERIC_SUMMARY,
    )
    return [
        {
            "id": "root",
            "component": "Stack",
            "children": ["fallback-title", "fallback-summary"],
        },
        {"id": "fallback-title", "component": "Heading", "text": title, "level": "2"},
        {"id": "fallback-summary", "component": "Text", "text": summary},
    ]
