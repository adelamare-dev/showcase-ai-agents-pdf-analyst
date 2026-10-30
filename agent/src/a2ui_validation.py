"""Structural validation of model-generated A2UI components, and a text fallback.

Scope: the dynamic agent only (`generate_a2ui`). The fixed agent renders a
hard-coded tree, so there is nothing to validate there.

Known limit: only the shape of the surface is checked here (list of dicts,
unique ids, a single `root`, known component types, resolvable child
references), plus the optional props restricted to a list of values. Other props
are NOT validated in Python; their Zod schemas on the client remain the only
check. Component names and those lists are derived from the `- **Name**` lines
of `CATALOG_PROMPT`, so changing that line format breaks the validation.
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


_HEADING_LEVELS = frozenset({"1", "2", "3"})


def normalize_heading_levels(components: list) -> None:
    """Rewrite `Heading` levels in place to the values the client schema accepts.

    Models often write `h1` or an integer instead of "1". A level that cannot be
    mapped to "1", "2" or "3" is dropped: it is optional on the client.
    """
    for item in components:
        if not (
            isinstance(item, dict)
            and item.get("component") == "Heading"
            and "level" in item
        ):
            continue
        level = str(item["level"]).removeprefix("h")
        if level in _HEADING_LEVELS:
            item["level"] = level
        else:
            del item["level"]


def optional_choices(prompt: str) -> dict[str, dict[str, frozenset[str]]]:
    """Optional props limited to a list of values (`weight?: regular|medium`), by
    component. Free text (`string|{path}`), ranges and booleans do not match."""
    choices: dict[str, dict[str, frozenset[str]]] = {}
    for name, summary in re.findall(r"^- \*\*(\w+)\*\*(.*)$", prompt, flags=re.M):
        props = re.findall(r'(\w+)\?:\s*("?\w+"?(?:\|"?\w+"?)+)(?![|\w{])', summary)
        if props:
            choices[name] = {
                prop: frozenset(values.replace('"', "").split("|"))
                for prop, values in props
            }
    return choices


CATALOG_CHOICES = optional_choices(CATALOG_PROMPT)


def drop_invalid_choices(components: list) -> None:
    """Remove, in place, optional props whose value is not one of the allowed ones.

    The client replaces a whole component with a visible alert when one prop is
    invalid, and the model writes such values now and then (`weight: 1`). The
    props are optional, so the component still renders without them.
    """
    for item in components:
        choices = CATALOG_CHOICES.get(item.get("component"), {})
        for prop, allowed in choices.items():
            value = item.get(prop)
            if prop in item and not (isinstance(value, str) and value in allowed):
                del item[prop]


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
            # `.text` covers both a plain string and a list of content blocks.
            payload = json.loads(message.text)
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
