"""Fixed-schema dashboard agent.

The user attaches a PDF in the chat. The agent model only routes: it calls
`render_dashboard`, and the 8B extractor reads the document (inlined into the
user message by `src/multimodal_middleware.py`) and fills the dashboard. The surface
includes an interactive scope-chips strip tailored to the document. Clicking a
chip fires a user action back to the agent, which re-renders with that focus.

The extractor fills the dashboard, but the code decides what reaches the screen
(`src/dashboard_checks.py`): a number the document does not write is dropped,
and a block with no data is removed from the surface instead of being padded.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from copilotkit import CopilotKitMiddleware, a2ui
from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AnyMessage, ToolMessage

from src.catalog import CATALOG_ID
from src.checkpoints import BoundedMemorySaver
from src.dashboard_checks import (
    MAX_KPIS,
    checked_kpis,
    checked_rows,
    checked_scope,
    checked_share,
    checked_trend,
    text_or_empty,
)
from src.errors import MistralErrorMiddleware
from src.locale import FRENCH_OUTPUT_RULE
from src.models import AGENT_MODEL, agent_chat_model
from src.pdf_tools import (
    EXTRACTION_FAILED,
    JSON_NUMBER_RULE,
    READING_RULES,
    extract_json,
    latest_document_text,
)
from src.routing import PdfTurnRoutingMiddleware

SCHEMA_DIR = Path(__file__).parent / "a2ui" / "schemas"
# Read explicitly as UTF-8: a2ui.load_schema opens the file without an encoding,
# which decodes accents as cp1252 on Windows.
DASHBOARD_SCHEMA = json.loads(
    (SCHEMA_DIR / "dashboard.json").read_text(encoding="utf-8")
)
SURFACE = "pdf-dashboard"
NO_DOCUMENT_REPLY = "Joignez un PDF et je génère le tableau de bord."


def _dashboard_components(
    kpi_count: int,
    has_trend: bool,
    has_share: bool,
    has_rows: bool,
    has_scope: bool,
) -> list[dict]:
    """The dashboard template without the blocks that have no data.

    Returns a copy of `DASHBOARD_SCHEMA`. A grid is as wide as it has children,
    so a lone chart takes the full width, and only the components reachable from
    the root are kept.
    """
    components = {c["id"]: copy.deepcopy(c) for c in DASHBOARD_SCHEMA}
    absent = {f"kpi-{n}" for n in range(kpi_count + 1, MAX_KPIS + 1)}
    if not has_trend:
        absent.add("trend-section")
    if not has_share:
        absent.add("share-section")
    if not has_trend and not has_share:
        absent.add("charts-grid")
    if kpi_count == 0:
        absent.add("kpi-grid")
    if not has_rows:
        absent.add("table-section")
    if not has_scope:
        absent.add("scope-chips")

    for component in components.values():
        if "children" not in component:
            continue
        component["children"] = [c for c in component["children"] if c not in absent]
        if component["component"] == "Grid" and component["children"]:
            component["columns"] = len(component["children"])

    reachable: set[str] = set()
    pending = ["root"]
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        node = components[current]
        pending.extend(node.get("children", []))
        if "child" in node:
            pending.append(node["child"])
    return [c for c in components.values() if c["id"] in reachable]


DASHBOARD_EXTRACTION_PROMPT = f"""\
You are a careful data extractor. Read the PDF text and fill a dashboard about
it. Return ONLY one JSON object, no prose, no markdown fences, with these keys:

- "eyebrow": short ALL-CAPS context, e.g. "T3 2025 · NOTE DE CONJONCTURE".
- "title": short headline, 8 words at most.
- "subtitle": one sentence summarizing the document.
- "kpis": up to 4 cards {{"label", "value", "delta", "caption"}}.
  * "value" is the headline number formatted the French way ("94 930 M€",
    "23,4 %"), copied from the document.
  * "delta" is only a variation the document writes for that value, short
    ("+6,1 %", "-3 %", at most 12 characters), otherwise "". Never compute a
    difference. Never put prose in it.
  * "caption" is where the comparison or context sentence goes (about 80
    characters at most).
- "trend": a list of {{"label", "value"}} points. Only one row of a table, with
  its periods copied exactly from the header, at least 2 points.
  "value" is a JSON number, not a string. Otherwise [].
- "share": a list of {{"label", "value"}} slices. Only if the document itself
  gives the parts of one whole. Contributions to growth, variations and rates
  are not parts. Never compute a share.
  "value" is a JSON number, not a string. Otherwise [].
- "rows": up to 8 table rows {{"name", "category", "value", "delta"}}, only if
  the document has such a list. The "delta" rule above applies. Otherwise [].
- "scope_options": 2 to 6 chips {{"label", "value"}} the user can click to
  change the focus, tailored to what THIS document supports (for a quarterly
  report: a period, a breakdown by segment, by region...).
- "scope_selected": the "value" of the active chip. If the focus names a chip,
  it is that chip's value.

An empty list or an empty string is a good answer: a length is never a reason to
add a value.

{FRENCH_OUTPUT_RULE}
{READING_RULES}
{JSON_NUMBER_RULE}"""


def _extraction_user_prompt(focus: str, document: str) -> str:
    return f"""\
Focus: {focus}

PDF text:
\"\"\"
{document}
\"\"\"
"""


def _failure_components() -> list[dict]:
    return [
        {
            "id": "root",
            "component": "Stack",
            "children": ["failure-title", "failure-summary"],
        },
        {
            "id": "failure-title",
            "component": "Heading",
            "text": EXTRACTION_FAILED["title"],
            "level": "2",
        },
        {
            "id": "failure-summary",
            "component": "Text",
            "text": EXTRACTION_FAILED["summary"],
        },
    ]


def _failure_surface() -> str:
    return a2ui.render(
        operations=[
            a2ui.create_surface(SURFACE, catalog_id=CATALOG_ID),
            a2ui.update_components(SURFACE, _failure_components()),
        ]
    )


# return_direct ends the turn with the surface: the agent model has nothing to
# add after it, and a small model would otherwise echo or re-render it.
@tool(return_direct=True)
def render_dashboard(focus: str, runtime: ToolRuntime[Any]) -> str:
    """Render the interactive dashboard for the loaded PDF.

    `focus` is what to center the dashboard on: the user's request, or the
    value of the chip they clicked. The tool reads the document itself, so
    never copy the document text into the call. Call it once per turn.
    """
    document = latest_document_text(runtime.state["messages"])
    if document is None:
        return _failure_surface()
    raw = extract_json(
        DASHBOARD_EXTRACTION_PROMPT,
        _extraction_user_prompt(focus, document),
        json_mode=True,
    )
    if raw is None:
        return _failure_surface()
    answer = json.loads(raw)

    kpis = checked_kpis(answer.get("kpis"), document)
    trend = checked_trend(answer.get("trend"), document)
    share = checked_share(answer.get("share"), document)
    rows = checked_rows(answer.get("rows"), document)
    if not (kpis or trend or share or rows):
        return _failure_surface()
    scope = checked_scope(answer.get("scope_options"), answer.get("scope_selected"))

    payload: dict[str, Any] = {
        "eyebrow": text_or_empty(answer.get("eyebrow")),
        "title": text_or_empty(answer.get("title")),
        "subtitle": text_or_empty(answer.get("subtitle")),
        "kpis": kpis,
        "trend": trend,
        "share": share,
        "rows": rows,
    }
    if scope is not None:
        payload["scope"] = scope
    components = _dashboard_components(
        len(kpis), bool(trend), bool(share), bool(rows), scope is not None
    )
    return a2ui.render(
        operations=[
            a2ui.create_surface(SURFACE, catalog_id=CATALOG_ID),
            a2ui.update_components(SURFACE, components),
            a2ui.update_data_model(SURFACE, payload),
        ]
    )


SYSTEM_PROMPT = f"""\
You answer questions about the user's attached PDF. You own one tool,
`render_dashboard`, which builds the dashboard from the document: it reads the
document itself, so pass it only a focus.

- The first dashboard is rendered by calling `render_dashboard(focus=...)` with
  what to center it on: the user's request.
- A chip click is the only thing that re-renders after the first dashboard. You
  recognize it by a tool result starting with `User performed action
  "select_chip"`, whose context holds the chip's value: call `render_dashboard`
  with that value as the focus. A message with no such result is a question:
  answer it in chat, and do not call the tool.
- To answer an analytical question ("what was operating margin?"), reply in
  the chat in 1-3 sentences, using only the document.
- If the user wants a brand-new visualization the dashboard does not cover
  (a sankey diagram, say), tell them to use the Dynamic tab.

Never type a tool result or any part of the document in your reply.

{READING_RULES}
{FRENCH_OUTPUT_RULE}
"""


def _required_tool(messages: list[AnyMessage]) -> str | None:
    """Impose the dashboard until the thread holds one, then leave the model free.

    The first turn on a document always renders, which is what the page is for.
    After that, a question is answered in chat and a chip click re-renders, both
    of the model's choosing.
    """
    has_dashboard = any(
        isinstance(m, ToolMessage) and m.name == "render_dashboard" for m in messages
    )
    return None if has_dashboard else "render_dashboard"


def build_fixed_agent(agent_model: str = AGENT_MODEL):
    return create_agent(
        model=agent_chat_model(agent_model),
        tools=[render_dashboard],
        # CopilotKitMiddleware forwards frontend tools + agent context (e.g.
        # useAgentContext payloads) to the LLM. MistralErrorMiddleware stays
        # after it so it sits closest to the model call.
        middleware=[
            CopilotKitMiddleware(),
            PdfTurnRoutingMiddleware(_required_tool, NO_DOCUMENT_REPLY),
            MistralErrorMiddleware(),
        ],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=BoundedMemorySaver(),
    )


graph = build_fixed_agent()
