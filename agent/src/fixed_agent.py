"""Fixed-schema dashboard agent.

The user attaches a PDF in the chat. The deep agent reads the PDF text
(inlined into the user message by InlineDocumentsMiddleware) and calls
`render_dashboard` with the structured data extracted in the same model
pass. The dashboard surface includes an interactive scope-chips strip
that the agent populates from the document. Clicking a chip fires a
user action back to the agent, which re-renders with the new scope.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from copilotkit import CopilotKitMiddleware, a2ui
from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from src.catalog import CATALOG_ID, CATALOG_PROMPT
from src.errors import MistralErrorMiddleware
from src.locale import FRENCH_OUTPUT_RULE
from src.models import AGENT_MODEL, agent_chat_model

SCHEMA_DIR = Path(__file__).parent / "a2ui" / "schemas"
# Read explicitly as UTF-8: a2ui.load_schema opens the file without an encoding,
# which decodes accents as cp1252 on Windows.
DASHBOARD_SCHEMA = json.loads(
    (SCHEMA_DIR / "dashboard.json").read_text(encoding="utf-8")
)
SURFACE = "pdf-dashboard"


class Kpi(TypedDict):
    label: str
    value: str
    delta: str
    caption: str


class Point(TypedDict):
    label: str
    value: float


class Row(TypedDict):
    name: str
    category: str
    value: str
    delta: str


class ScopeOption(TypedDict):
    label: str
    value: str


@tool
def render_dashboard(
    eyebrow: str,
    title: str,
    subtitle: str,
    kpis: list[Kpi],
    trend: list[Point],
    share: list[Point],
    rows: list[Row],
    scope_options: list[ScopeOption],
    scope_selected: str,
) -> str:
    """Render the interactive dashboard for the loaded PDF.

    Pass data INLINE. Call ONCE per turn.

    Required shapes:
      - kpis: EXACTLY 4 cards. Each {label, value, delta, caption}.

        STRICT FIELD RULES (very important; the badge breaks if you ignore):
          * `value`   = the headline number, formatted the French way
                        ("94 930 M€", "23,4 %", "1,2 M d'unités"). 1–8 chars
                        typically.
          * `delta`   = JUST the magnitude of change. Format: "+X%", "-X%",
                        or "" (empty string when there's no comparison).
                        Number and "%" are separated by a space; the "+" or
                        "-" sign sticks to the number.
                        MAX 8 chars. NEVER prose. NEVER "vs. last quarter"
                        or "vs 89 498 M€". The arrow and color come from
                        the renderer.
                        Examples: "+6,1 %", "-3 %", "+12 %", "+2,4 Md€", ""
                        Bad:      "↑ vs 89 498 M€ au T4 2023"
                                  "en hausse de 6 % sur un an"
                                  "en hausse par rapport à 89 498 M€"
          * `caption` = the comparison/context sentence ("vs 89 498 M€ au
                        T4 2023", "Produits 69 958 M€ ; Services 24 972 M€",
                        "Plus haut historique"). Up to ~80 chars. This is
                        where the prose goes.

      - trend: 6–12 points. {label, value:number}.
      - share: 3–5 slices. {label, value:number}.
      - rows: 5–8 table rows. Same delta rule applies: row.delta is
        SHORT ("+6 %", "-3 %", ""). Verbose comparisons belong elsewhere.
      - scope_options: 3–6 chips the user can click to re-scope. Each
        {label, value}. Example for an Apple earnings PDF:
          [{label:"T4 2024", value:"q4_fy24"},
           {label:"Exercice 2024", value:"fy24"},
           {label:"Par segment", value:"by_segment"},
           {label:"Par région",  value:"by_region"}]
        Tailor the options to what THIS document actually supports.
      - scope_selected: the `value` of the currently active option.
    """
    payload = {
        "eyebrow": eyebrow,
        "title": title,
        "subtitle": subtitle,
        "kpis": kpis,
        "trend": trend,
        "share": share,
        "rows": rows,
        "scope": {"options": scope_options, "selected": scope_selected},
    }
    return a2ui.render(
        operations=[
            a2ui.create_surface(SURFACE, catalog_id=CATALOG_ID),
            a2ui.update_components(SURFACE, DASHBOARD_SCHEMA),
            a2ui.update_data_model(SURFACE, payload),
        ]
    )


SYSTEM_PROMPT = f"""\
You build and maintain a live dashboard from the user's PDF.

## How a turn works

The user may do three things on any turn:
  A) Attach a new PDF + chat (initial render).
  B) Send a chat message ("re-render focused on energy storage",
     "what was operating margin?", "compare last quarter").
  C) Click a scope chip on the dashboard. The runtime delivers this as a
     tool result `log_a2ui_event` with content like:
        User performed action "select_chip" on surface "pdf-dashboard".
        Context: {{"value": "fy24", "label": "Scope"}}

In every case, decide whether to re-render the dashboard, answer in chat,
or both.

## The render contract

When you render, call `render_dashboard(...)` ONCE with structured data:
  - 4 KPIs, 6–12 trend points, 3–5 share slices, 5–8 rows.
  - `scope_options`: 3–6 chips tailored to THIS PDF. Examples of good
    chip sets:
      - Apple Q4 PDF → [T4 2024, Exercice 2024, Par segment, Par région,
                       Par catégorie]
      - Tesla Q3 PDF → [T3 2024, Par modèle, Par région, Automobile vs
                       Énergie, 4 derniers trimestres]
  - `scope_selected`: which chip is active. Default to the most natural
    starting scope for the document. After a chip click, set this to the
    clicked value.

When the user (or a chip click) asks to change scope:
  - Re-extract the data for the new scope from the PDF text.
  - Re-call render_dashboard with the SAME surfaceId so the canvas
    updates in place. The scope_selected reflects the new active chip.

## Hard rules

- Render the dashboard whenever the user attaches a PDF (initial), asks
  to re-render in any way, or clicks a chip.
- Call `render_dashboard` AT MOST ONCE per turn. Never twice.
- Use ONLY numbers that actually appear in the document.
- If the user asks an analytical question that does NOT require a layout
  change (e.g. "what was operating margin?"), answer in chat without
  re-rendering. 1–3 sentences max. Cite the number.
- If the user wants to invent a brand-new visualization not covered by
  the fixed schema (e.g. "show a sankey diagram"), tell them to use the
  Dynamic tab.

## Chat tone

Be helpful, brief, conversational. After the first render, you can
suggest one or two follow-ups the user might click ("Touchez *Exercice 2024*
pour la vue annuelle" or "Voulez-vous le détail par segment ?"). Don't list
more than two suggestions.

{FRENCH_OUTPUT_RULE}
{CATALOG_PROMPT}
"""


def build_fixed_agent(agent_model: str = AGENT_MODEL):
    return create_agent(
        model=agent_chat_model(agent_model),
        tools=[render_dashboard],
        # CopilotKitMiddleware forwards frontend tools + agent context (e.g.
        # useAgentContext payloads) to the LLM. MistralErrorMiddleware stays
        # after it so it sits closest to the model call.
        middleware=[CopilotKitMiddleware(), MistralErrorMiddleware()],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )


graph = build_fixed_agent()
