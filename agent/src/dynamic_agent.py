"""Dynamic-schema Q&A agent.

The agent answers any question about the most-recently-uploaded PDF by
inventing the UI for the answer using our custom catalog.

## Why this looks the way it does

The first cut wired things up to use the JS-runtime-injected `render_a2ui`
frontend tool. That works on turn 1 but leaves an orphan
tool call in agent state (CopilotKitMiddleware strips frontend
tool calls in `after_model` and restores them in `after_agent`. between
those two phases ToolNode never sees the call, so no `ToolMessage` is
ever produced). The result is turn 2 hitting the model API with an
unanswered tool call → INCOMPLETE_STREAM / "terminated".

The CopilotKit reference example in
`CopilotKit/examples/integrations/langgraph-python` solves this by
NOT injecting `render_a2ui` as a frontend tool at all. Instead, the
agent has a real Python tool (`generate_a2ui` here) that:

  1. Runs server-side as a normal LangChain tool.
  2. Spawns a secondary LLM bound to a no-op `render_a2ui` tool to
     force structured output.
  3. Wraps the LLM's tool_call args into A2UI `create_surface` +
     `update_components` + `update_data_model` operations.
  4. Returns the rendered ops as a JSON string. a normal tool result.

The JS-side a2ui middleware detects `a2ui_operations` in the
TOOL_CALL_RESULT and emits the ACTIVITY_SNAPSHOT events the canvas
listens for. No frontend tool stripping. No orphan. No turn-2 crash.

`src/app/api/copilotkit/route.ts` sets `injectA2UITool: false` to
match.

The generated components are validated structurally (`src/a2ui_validation.py`).
An invalid or missing render call is retried once with the rejection reason in
the system prompt; after two failures a plain text surface is built in Python
without any model call.

A turn on this graph has one valid course, which the code imposes instead of
asking the model for it (`PdfTurnRoutingMiddleware`): `query_pdf`, then
`generate_a2ui`. The render model never sees the document text, only the
`query_pdf` results, so it cannot read values the extractor did not report.
"""

from __future__ import annotations

import json
from typing import Any

from copilotkit import CopilotKitMiddleware, a2ui
from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.tools import tool as lc_tool

from src.a2ui_validation import (
    drop_invalid_choices,
    fallback_components,
    normalize_heading_levels,
    validate_components,
)
from src.catalog import CATALOG_ID, CATALOG_PROMPT
from src.checkpoints import BoundedMemorySaver
from src.errors import MistralErrorMiddleware
from src.locale import FRENCH_OUTPUT_RULE
from src.models import AGENT_MODEL, RENDER_MODEL, agent_chat_model, chat_model
from src.pdf_tools import (
    extraction_failed,
    query_pdf,
    query_pdf_call_ids_this_turn,
    without_document_text,
)
from src.routing import PdfTurnRoutingMiddleware


NO_DOCUMENT_REPLY = "Joignez un PDF et je génère la réponse."


def _required_tool(messages: list[AnyMessage]) -> str:
    """The tool the next model call must make, once a document is attached."""
    if not query_pdf_call_ids_this_turn(messages):
        return "query_pdf"
    return "generate_a2ui"


# No-op shim. The secondary LLM is forced to call this tool so its output
# is a structured tool_call (surfaceId / catalogId / components / data)
# instead of free-form prose we'd have to JSON-parse and validate.
@lc_tool
def render_a2ui(
    surfaceId: str,
    catalogId: str,
    components: list[dict],
    data: dict | None = None,
) -> str:
    """Render a dynamic A2UI v0.9 surface.

    Args:
        surfaceId: Unique surface identifier (kebab-case).
        catalogId: The catalog ID. Use the one provided in context.
        components: A2UI v0.9 flat component array; root component MUST
            have id="root".
        data: Optional initial data model for the surface.
    """
    return "rendered"


_RENDER_MODEL = chat_model(RENDER_MODEL)

# Shown verbatim to the render model. Small models otherwise guess the shape
# (a `type` key, nested component objects) and every attempt is rejected.
RENDER_EXAMPLE = [
    {"id": "root", "component": "Stack", "children": ["title", "trend"]},
    {"id": "title", "component": "Heading", "text": "Chiffre d'affaires par trimestre"},
    {
        "id": "trend",
        "component": "LineChart",
        "data": [{"label": "T1", "value": 41.2}, {"label": "T2", "value": 43.0}],
    },
]


# Addressed to the render model, the only one that designs the surface. The
# agent model never sees it: its tools are imposed and it has no layout to pick.
RENDER_LAYOUT_GUIDE = """\
## Layout guidance

When the user is specific ("three line charts stacked", "side-by-side cards"),
honor it. Otherwise follow the `shape_hint` of the LAST query_pdf result:

- `stat`  -> Stack(Overline, StatCard)
- `trend` -> Stack(Section -> Card -> LineChart)
- `share` -> Stack(Section -> Card -> DonutChart)
- `table` -> Stack(Section -> Card -> DataTable)
- `text`  -> Rich explainer. Compose multiple components, not just one Card:
              Stack(
                Overline(topic),
                Heading(title),
                Text(intro paragraph, 2-4 sentences),
                Callout(tone=info, title="Idée clé", body=core insight),
                Section(title="Pourquoi c'est important", child=Card(Text(...))),
                BulletList(items=[3 key points]),
              )
              Use Callout for the "headline takeaway", BulletList for
              enumerations, and Text for paragraphs. Mix with one chart
              ONLY if the question genuinely benefits from data viz.

Heuristic for research-paper questions: prefer the rich `text` layout above.
Skip charts unless the user explicitly asked for data viz.
"""


# return_direct ends the turn as soon as the surface is produced. The prompt
# also says to stop, but small models ignore it and keep re-rendering until
# the recursion limit, so the stop cannot be left to the model.
@tool(return_direct=True)
def generate_a2ui(runtime: ToolRuntime[Any]) -> str:
    """Render the answer to the user's question as an A2UI surface.

    Call this AFTER `query_pdf`. It reads the conversation (including the
    query_pdf result) and the available A2UI catalog from context, then
    designs the surface and returns the operations for the client to
    render. You do NOT pass any arguments. It picks up everything from
    state.
    """
    messages = runtime.state["messages"][:-1]

    def _fallback_surface() -> str:
        surface_id = "dynamic-surface"
        return a2ui.render(
            operations=[
                a2ui.create_surface(surface_id, catalog_id=CATALOG_ID),
                a2ui.update_components(surface_id, fallback_components(messages)),
            ]
        )

    # Nothing to render from: the extractor already gave up, and the render
    # model would only invent the data.
    if extraction_failed(messages):
        return _fallback_surface()
    context_entries = runtime.state.get("copilotkit", {}).get("context", [])
    context_text = "\n\n".join(
        entry.get("value", "")
        for entry in context_entries
        if isinstance(entry, dict) and entry.get("value")
    )

    # The runtime context only carries the basic catalog. Append our
    # custom catalog spec so the secondary LLM picks our components, not
    # the generic A2UI primitives.
    custom_catalog_note = (
        f"\n\n## Use THIS catalog (NOT the basic one above):\n"
        f"catalogId: {CATALOG_ID}\n\n"
        f"{CATALOG_PROMPT}\n"
    )

    prompt = (
        f"{context_text}\n{custom_catalog_note}\n"
        f"{RENDER_LAYOUT_GUIDE}\n"
        f"{FRENCH_OUTPUT_RULE}\n"
        "Design the surface using ONLY components from the catalog above. "
        "Every number, label and fact on the surface comes from the LAST "
        "query_pdf result in this conversation. Copy the values exactly and "
        "never estimate, complete or invent one: a short series stays short. "
        "Inline all data (use plain values, not {{path}} bindings, unless a "
        "property explicitly accepts a path). The user's request is in the "
        "most recent messages. Honor the words they used (chart type, "
        "comparison, etc.).\n\n"
        "`components` is a FLAT list. Each item is one object with a string "
        "`id`, a string `component` naming a catalog type, and that type's "
        "props at the same level. Parents reference children by id, never by "
        "nesting objects. Example:\n"
        f"{json.dumps(RENDER_EXAMPLE)}"
    )

    render_messages = without_document_text(messages)
    model_with_tool = _RENDER_MODEL.bind_tools([render_a2ui], tool_choice="render_a2ui")

    # At most two attempts: a malformed or missing render_a2ui call is retried
    # once with the rejection reason in the system prompt. Provider errors are
    # not caught here; they propagate to the error middleware.
    args: dict = {}
    for attempt in range(2):
        response = model_with_tool.invoke(
            [SystemMessage(content=prompt), *render_messages]
        )
        if response.tool_calls:
            args = response.tool_calls[0]["args"]
            errors = validate_components(args.get("components", []))
        else:
            errors = ["The model did not call render_a2ui."]
        if not errors:
            break
        prompt += (
            "\n\nYour previous render_a2ui call was rejected: "
            f"{' '.join(errors)} Call render_a2ui again with a corrected surface."
        )
    else:
        return _fallback_surface()

    surface_id = args.get("surfaceId", "dynamic-surface")
    # Only one catalog exists; a model-supplied catalogId is ignored.
    components = args["components"]
    # The renderer replaces a component whose props are invalid with a visible
    # alert, and the model sometimes writes a Heading level as "h1".
    normalize_heading_levels(components)
    drop_invalid_choices(components)
    data = args.get("data", {})

    ops = [
        a2ui.create_surface(surface_id, catalog_id=CATALOG_ID),
        a2ui.update_components(surface_id, components),
    ]
    if data:
        ops.append(a2ui.update_data_model(surface_id, data))

    return a2ui.render(operations=ops)


SYSTEM_PROMPT = f"""\
You answer questions about a user's attached PDF. Two tools do the work: one
reads the document, the other renders the answer as a surface the user sees.

The frontend extracts the PDF text and inlines it into the user's message under
a `[Document: <filename>]` header. The PDF may have been attached on this turn
or on any earlier one.

## How a turn goes

Call `query_pdf(question=<the user's question on THIS turn>)` with only the
question: the tool reads the document itself. Then call `generate_a2ui()` with
no argument.

Never type a tool result, any part of the document text, or a description of
the surface in your reply: the surface is the answer.

{FRENCH_OUTPUT_RULE}
"""


def build_dynamic_agent(agent_model: str = AGENT_MODEL):
    return create_agent(
        model=agent_chat_model(agent_model),
        tools=[query_pdf, generate_a2ui],
        middleware=[
            CopilotKitMiddleware(),
            PdfTurnRoutingMiddleware(_required_tool, NO_DOCUMENT_REPLY),
            MistralErrorMiddleware(),
        ],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=BoundedMemorySaver(),
    )


graph = build_dynamic_agent()
